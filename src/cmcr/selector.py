from __future__ import annotations

import time
from typing import Callable
import chess

PIECE_VALUES: dict[chess.PieceType, int] = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 100,
}

CENTER_SQUARES: set[chess.Square] = {chess.D4, chess.E4, chess.D5, chess.E5}
EXTENDED_CENTER: set[chess.Square] = CENTER_SQUARES | {
    chess.C3, chess.D3, chess.E3, chess.F3,
    chess.C6, chess.D6, chess.E6, chess.F6,
}


class CMCRDeadlineExceeded(Exception):
    pass


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.perf_counter() >= deadline:
        raise CMCRDeadlineExceeded()


def _king_shield_score(board: chess.Board, color: chess.Color) -> int:
    king_sq = board.king(color)
    if king_sq is None:
        return 0
    k_file = chess.square_file(king_sq)
    k_rank = chess.square_rank(king_sq)
    pawn_dir = 1 if color == chess.WHITE else -1

    shield = 0
    for df in (-1, 0, 1):
        f = k_file + df
        r = k_rank + pawn_dir
        if 0 <= f <= 7 and 0 <= r <= 7:
            sq = chess.square(f, r)
            piece = board.piece_at(sq)
            if piece is not None and piece.piece_type == chess.PAWN and piece.color == color:
                shield += 1
    return shield


def _defensive_score(
    board: chess.Board,
    move: chess.Move,
    attacked_squares: set[chess.Square],
    threat_attackers: set[chess.Square],
) -> int | None:
    us = board.turn
    them = not us
    score = 0

    # 1. Moving a friendly piece currently under attack
    if move.from_square in attacked_squares:
        piece = board.piece_at(move.from_square)
        if piece is not None:
            score += PIECE_VALUES.get(piece.piece_type, 1) * 10
            if not board.is_attacked_by(them, move.to_square):
                score += 25

    # 2. Capturing a piece that is actually attacking one of our pieces
    if board.is_capture(move) and move.to_square in threat_attackers:
        victim = board.piece_at(move.to_square)
        victim_val = PIECE_VALUES.get(victim.piece_type, 1) if victim else 1
        score += victim_val * 12

    # 3. Reinforcing or defending an attacked friendly piece
    board.push(move)
    try:
        for sq in attacked_squares:
            piece = board.piece_at(sq)
            if piece is not None and piece.color == us:
                if board.is_attacked_by(us, sq) and not board.is_attacked_by(them, sq):
                    score += PIECE_VALUES.get(piece.piece_type, 1) * 8
                elif board.is_attacked_by(us, sq):
                    score += PIECE_VALUES.get(piece.piece_type, 1) * 4
    finally:
        board.pop()

    return score if score > 0 else None


def _aggressive_score(board: chess.Board, move: chess.Move) -> int | None:
    us = board.turn
    them = not us
    score = 0

    if board.is_capture(move):
        victim = board.piece_type_at(move.to_square)
        score += PIECE_VALUES.get(victim, 1) * 12

    if move.promotion is not None:
        score += PIECE_VALUES.get(move.promotion, 9) * 10

    to_rank = chess.square_rank(move.to_square)
    if move.to_square in CENTER_SQUARES:
        score += 12
    elif move.to_square in EXTENDED_CENTER:
        score += 6

    board.push(move)
    try:
        if board.is_check():
            score += 25

        enemy_king = board.king(them)
        for sq in board.attacks(move.to_square):
            target = board.piece_at(sq)
            if target is not None and target.color == them:
                score += PIECE_VALUES.get(target.piece_type, 1) * 3
                if enemy_king is not None:
                    dist = max(
                        abs(chess.square_file(sq) - chess.square_file(enemy_king)),
                        abs(chess.square_rank(sq) - chess.square_rank(enemy_king)),
                    )
                    if dist <= 2:
                        score += 10
    finally:
        board.pop()

    moving_piece = board.piece_at(move.from_square)
    if moving_piece is not None and moving_piece.piece_type == chess.PAWN:
        adv = to_rank if us == chess.WHITE else (7 - to_rank)
        score += adv * 2

    return score if score > 0 else None


def _king_safety_score(board: chess.Board, move: chess.Move) -> int | None:
    us = board.turn
    them = not us
    moving_piece = board.piece_at(move.from_square)
    if moving_piece is None:
        return None

    is_castling = board.is_castling(move)
    old_shield = _king_shield_score(board, us)
    was_in_check = board.is_check()

    board.push(move)
    try:
        new_king_sq = board.king(us)
        king_square_attacked = (
            new_king_sq is not None and board.is_attacked_by(them, new_king_sq)
        )
        new_shield = _king_shield_score(board, us)
        now_in_check = board.is_check()
    finally:
        board.pop()

    # Never reward moving the king onto an attacked square
    if moving_piece.piece_type == chess.KING and king_square_attacked:
        return None

    score = 0
    if is_castling and not king_square_attacked:
        score += 100

    if was_in_check and not now_in_check and not king_square_attacked:
        score += 80

    if moving_piece.piece_type == chess.KING and not is_castling:
        if was_in_check:
            score += 40
        elif new_shield >= old_shield:
            score += 10
    elif moving_piece.piece_type == chess.PAWN and new_shield > old_shield:
        score += (new_shield - old_shield) * 20

    return score if score > 0 else None


def _utility_activity_score(board: chess.Board, move: chess.Move) -> int:
    """Utility #1: piece development, central/file activity, and tactical tension."""
    us = board.turn
    piece = board.piece_at(move.from_square)
    if piece is None:
        return 0

    from_rank = chess.square_rank(move.from_square)
    to_rank = chess.square_rank(move.to_square)
    to_file = chess.square_file(move.to_square)
    back_rank = 0 if us == chess.WHITE else 7

    score = 0
    if piece.piece_type in (chess.KNIGHT, chess.BISHOP):
        if from_rank == back_rank and to_rank != back_rank:
            score += 35
        if move.to_square in EXTENDED_CENTER:
            score += 12
    elif piece.piece_type == chess.ROOK:
        if to_file in (3, 4):
            score += 14
        if from_rank == back_rank and to_rank != back_rank:
            score += 10
    elif piece.piece_type == chess.QUEEN:
        if from_rank != back_rank and move.to_square in EXTENDED_CENTER:
            score += 6

    if board.is_capture(move):
        score += 5

    return score


def _utility_structure_score(board: chess.Board, move: chess.Move) -> int:
    """Utility #2: pawn advance, center/flank structure, and safe positional progress."""
    us = board.turn
    them = not us
    piece = board.piece_at(move.from_square)
    if piece is None:
        return 0

    to_rank = chess.square_rank(move.to_square)
    to_file = chess.square_file(move.to_square)
    score = 0

    if piece.piece_type == chess.PAWN:
        adv = to_rank if us == chess.WHITE else (7 - to_rank)
        score += 12 + adv * 5
        if to_file in (2, 3, 4, 5):
            score += 10
    else:
        if move.to_square in CENTER_SQUARES:
            score += 10
        elif move.to_square in EXTENDED_CENTER:
            score += 6

    if not board.is_attacked_by(them, move.to_square):
        score += 4

    return score


def _immediate_reply_penalty(board: chess.Board, move: chess.Move, deadline: float | None) -> int:
    """Lightweight 1-ply sanity check on a selected candidate."""
    _check_deadline(deadline)
    moved_piece = board.piece_at(move.from_square)
    moved_val = PIECE_VALUES.get(moved_piece.piece_type, 1) if moved_piece else 1

    board.push(move)
    try:
        worst_loss = 0
        for reply in board.legal_moves:
            _check_deadline(deadline)
            if board.is_capture(reply):
                victim = board.piece_type_at(reply.to_square)
                victim_val = PIECE_VALUES.get(victim, 1) if victim else 1
                if reply.to_square == move.to_square and victim_val >= moved_val:
                    worst_loss = max(worst_loss, victim_val * 10)
        return worst_loss
    finally:
        board.pop()


def cmcr(
    fen: str,
    max_depth: int = 1,
    time_limit: float | None = 0.05,
) -> list[chess.Move]:
    """
    Chess Move Calculation Return:
    Selects up to 5 diverse, verified legal candidate moves for an external engine:
      1. Defensive move
      2. Aggressive move
      3. King safety move
      4. Utility #1 (piece development / activity)
      5. Utility #2 (pawn advance / positional structure)
    Backfills remaining slots with unused legal moves when fewer roles apply.
    """
    board = chess.Board(fen)
    legal_moves = list(board.legal_moves)
    legal_set = set(legal_moves)
    if not legal_moves:
        return []

    deadline = (time.perf_counter() + time_limit) if time_limit is not None else None
    us = board.turn
    them = not us

    attacked_squares: set[chess.Square] = set()
    threat_attackers: set[chess.Square] = set()
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is not None and piece.color == us:
            attackers = board.attackers(them, sq)
            if attackers:
                attacked_squares.add(sq)
                threat_attackers.update(attackers)

    chosen: list[chess.Move] = []
    used: set[chess.Move] = set()

    def select_for_role(scorer: Callable[[chess.Move], int | None]) -> None:
        if len(chosen) >= 5:
            return
        try:
            _check_deadline(deadline)
            best_move: chess.Move | None = None
            best_score = -(10**9)

            for move in legal_moves:
                _check_deadline(deadline)
                if move in used or move not in legal_set:
                    continue
                val = scorer(move)
                if val is not None and val > best_score:
                    best_score = val
                    best_move = move

            if best_move is not None and best_move in legal_set and best_move not in used:
                chosen.append(best_move)
                used.add(best_move)
        except CMCRDeadlineExceeded:
            pass

    select_for_role(lambda m: _defensive_score(board, m, attacked_squares, threat_attackers))
    select_for_role(lambda m: _aggressive_score(board, m))
    select_for_role(lambda m: _king_safety_score(board, m))
    select_for_role(lambda m: _utility_activity_score(board, m))
    select_for_role(lambda m: _utility_structure_score(board, m))

    for move in legal_moves:
        if len(chosen) >= 5:
            break
        if deadline is not None and time.perf_counter() >= deadline:
            break
        if move in legal_set and move not in used:
            chosen.append(move)
            used.add(move)

    candidates = [m for m in chosen[:5] if m in legal_set]

    if max_depth > 1 and len(candidates) > 1:
        try:
            candidates.sort(key=lambda m: _immediate_reply_penalty(board, m, deadline))
        except CMCRDeadlineExceeded:
            pass

    return [m for m in candidates if m in legal_set]


__all__ = ["cmcr", "PIECE_VALUES"]
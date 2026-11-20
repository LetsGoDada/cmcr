import chess
from cmcr import cmcr

fens = [
    chess.STARTING_FEN,
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
    "8/8/8/4k3/4P3/4K3/8/8 w - - 0 1",
]

for fen in fens:
    board = chess.Board(fen)
    legal = set(board.legal_moves)
    moves = cmcr(fen, max_depth=2, time_limit=0.05)
    assert all(m in legal for m in moves), "Illegal move leaked!"
    print(fen, "->", [m.uci() for m in moves])
# cmcr

**Chess Move Calculation Return** — a lightweight Python candidate-move selector built on [`python-chess`](https://github.com/niklasf/python-chess) that returns up to five diverse, verified legal moves for external chess engines.

## Overview

`cmcr` separates **candidate generation** from **deep search/evaluation**:

1. **Defensive** — responds to attacked pieces, captures threatening attackers, or reinforces threatened squares.
2. **Aggressive** — looks at captures, promotions, checks, and attacks near the opponent's king.
3. **King Safety** — evaluates castling, escaping check, and pawn-shield/king-square safety.
4. **Utility #1 (Activity)** — favors piece development, central/file influence, and tactical tension.
5. **Utility #2 (Structure)** — favors pawn advancement, positional structure, and safer squares.

If fewer than five distinct role moves apply, `cmcr` automatically backfills remaining slots from unused legal moves while respecting a strict `time_limit`.

## Installation

### Local Editable Install (Development)

```bash
pip install -e .
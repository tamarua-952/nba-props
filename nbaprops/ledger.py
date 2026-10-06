"""Paper ledger: every pick is logged whether or not it is bet.

The user fills `betcha_line` and `betcha_price` (and nothing else). The next
day's run fills the closing line, the result and profit/loss.

Grading uses the user's Betcha line when given, otherwise the brief's line.
A player who does not play is VOID (props are refunded).
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

COLUMNS = [
    "date", "game_id", "tip_nzt", "player_id", "player", "team", "opp", "market", "side", "line",
    "projection", "model_prob", "fair_odds", "threshold", "flags", "consensus_line",
    # filled by the user
    "betcha_line", "betcha_price",
    # filled by later runs
    "closing_line", "closing_over_price", "closing_under_price",
    "actual", "result", "pl_units", "paper_pl_units", "clv_pct", "clv_line",
]


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})


def key(r: dict) -> tuple:
    return (str(r["date"]), str(r["game_id"]), str(r["player_id"]), r["market"])


def append(path: Path, picks: list[dict]) -> int:
    """Add picks not already in the ledger; returns how many were added."""
    rows = read(path)
    have = {key(r) for r in rows}
    new = [p for p in picks if key(p) not in have]
    write(path, rows + new)
    return len(new)


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def grade(side: str, line: float, actual: float | None, played: bool) -> str:
    if not played or actual is None:
        return "VOID"
    if actual == line:
        return "PUSH"
    won = actual > line if side == "over" else actual < line
    return "WIN" if won else "LOSS"


def profit(result: str, price: float | None) -> float | None:
    if price is None:
        return None
    return {"WIN": price - 1.0, "LOSS": -1.0, "PUSH": 0.0, "VOID": 0.0}.get(result)


def devig(over_price: float, under_price: float) -> tuple[float, float]:
    """Two-way no-vig probabilities from decimal prices."""
    io, iu = 1 / over_price, 1 / under_price
    return io / (io + iu), iu / (io + iu)


def settle(row: dict, actual: float | None, played: bool) -> dict:
    """Fill result, P/L and CLV for one ledger row (closing fields must already be set if known)."""
    side = row["side"]
    bet_line = _num(row.get("betcha_line")) or _num(row["line"])
    price = _num(row.get("betcha_price"))
    row["actual"] = "" if actual is None else actual
    row["result"] = grade(side, bet_line, actual, played)
    pl = profit(row["result"], price)
    row["pl_units"] = "" if pl is None else round(pl, 3)
    paper = profit(grade(side, _num(row["line"]), actual, played), _num(row["threshold"]))
    row["paper_pl_units"] = "" if paper is None else round(paper, 3)

    cl, co, cu = _num(row.get("closing_line")), _num(row.get("closing_over_price")), _num(row.get("closing_under_price"))
    if cl is not None:
        # Line CLV: points of line movement in our favour (over: closing line rose).
        row["clv_line"] = round((cl - bet_line) if side == "over" else (bet_line - cl), 2)
        taken = price if price is not None else _num(row["threshold"])
        if co and cu and taken and cl == bet_line:
            fair_over, fair_under = devig(co, cu)
            fair = fair_over if side == "over" else fair_under
            row["clv_pct"] = round(taken * fair - 1.0, 4)
    return row

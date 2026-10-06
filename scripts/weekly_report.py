"""Weekly report from the ledger: calibration, CLV and profit/loss.

    python scripts/weekly_report.py [--ledger ledger.csv] [--out output]

Writes output/weekly_<NZ date>.md covering the last 7 days and all time.
Paper P/L assumes 1 unit on every pick at its bet threshold; actual P/L uses
only picks with a Betcha price filled in.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BINS = [0.5, 0.55, 0.6, 0.65, 0.7, 1.0001]


def section(df: pd.DataFrame, title: str) -> list[str]:
    L = [f"## {title}", ""]
    s = df[df["result"].isin(["WIN", "LOSS"])]
    if s.empty:
        return L + ["No settled picks.", ""]
    L += [f"Settled picks: {len(s)} (plus {int(df['result'].isin(['PUSH', 'VOID']).sum())} push/void). "
          f"Hit rate {s['win'].mean():.1%} vs model {s['model_prob'].mean():.1%}.", "",
          "| Model prob | n | Mean model | Hit rate |", "|---|---|---|---|"]
    for b, g in s.groupby(pd.cut(s["model_prob"], BINS, right=False), observed=True):
        L.append(f"| {b.left:.0%}–{min(b.right, 1):.0%} | {len(g)} | {g['model_prob'].mean():.1%} | {g['win'].mean():.1%} |")
    bet = df[pd.to_numeric(df["pl_units"], errors="coerce").notna() & df["betcha_price"].astype(str).str.len().gt(0)]
    clv = pd.to_numeric(df["clv_pct"], errors="coerce").dropna()
    clv_line = pd.to_numeric(df["clv_line"], errors="coerce").dropna()
    L += ["", f"- Paper P/L (1 unit at threshold, every pick): {pd.to_numeric(df['paper_pl_units'], errors='coerce').sum():+.2f} units "
              f"over {pd.to_numeric(df['paper_pl_units'], errors='coerce').notna().sum()} picks.",
          f"- Actual P/L (Betcha bets): {pd.to_numeric(bet['pl_units'], errors='coerce').sum():+.2f} units over {len(bet)} bets.",
          "- CLV (price, same line): " + (f"{clv.mean():+.1%} average over {len(clv)} picks." if len(clv) else "no data."),
          "- CLV (line points in our favour): " + (f"{clv_line.mean():+.2f} average over {len(clv_line)} picks."
                                                    if len(clv_line) else "no data."),
          ""]
    return L


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=str(ROOT / "ledger.csv"))
    ap.add_argument("--out", default=str(ROOT / "output"))
    args = ap.parse_args()
    today = dt.datetime.now(ZoneInfo("Pacific/Auckland")).date()
    p = Path(args.ledger)
    df = pd.read_csv(p, dtype=str).fillna("") if p.exists() else pd.DataFrame()
    L = [f"# Weekly report — {today}", ""]
    if df.empty:
        L.append("Ledger is empty.")
    else:
        df["model_prob"] = pd.to_numeric(df["model_prob"])
        df["win"] = (df["result"] == "WIN").astype(int)
        df["date_d"] = pd.to_datetime(df["date"]).dt.date
        L += section(df[df["date_d"] > today - dt.timedelta(days=7)], "Last 7 days")
        L += section(df, "All time")
        L += ["Multis stay off until 300+ settled picks show positive average CLV.", ""]
    out = Path(args.out) / f"weekly_{today}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

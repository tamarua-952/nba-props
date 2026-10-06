"""Proxy closing line: one Odds API call per top pick game, shortly before tip-off.

    python scripts/closing_lines.py

Run every 30 minutes through the NZ afternoon (GitHub Action). Reads today's
plan (data/picks/<NZ date>.json, written by the daily brief), and for each
planned game tipping within `brief.closing_lookahead_min` minutes that has no
closing snapshot yet, calls the Odds API once and writes the consensus line
and prices into the ledger rows for that game. The raw response is cached.
The closing call has priority over the morning call: the brief skips its
morning call when the budget can't cover both.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nbaprops import config, ledger  # noqa: E402
from nbaprops.odds_api import BudgetExceeded, OddsAPI, consensus, match_event, norm_name  # noqa: E402

NZ = ZoneInfo("Pacific/Auckland")


def main() -> None:
    cfg = config.load()
    now = dt.datetime.now(dt.timezone.utc)
    plan_path = ROOT / "data" / "picks" / f"{now.astimezone(NZ).date()}.json"
    if not plan_path.exists():
        print("No closing-line plan for today.")
        return
    plan = json.loads(plan_path.read_text())
    look = dt.timedelta(minutes=cfg["brief"]["closing_lookahead_min"])
    due = [g for g in plan["games"] if not g["closing_done"]
           and now - dt.timedelta(minutes=5) <= dt.datetime.fromisoformat(g["tip_utc"].replace("Z", "+00:00")) <= now + look]
    if not due:
        print("No pick game due for a closing line.")
        return
    try:
        odds = OddsAPI()
    except BudgetExceeded as e:
        print(f"Odds API unavailable: {e}")
        return
    led_path = ROOT / "ledger.csv"
    rows = ledger.read(led_path)
    events = None
    for g in due:
        if not odds.can_afford("event_odds", 1):
            print("Budget guard: no closing call.")
            break
        if not g.get("event_id"):
            events = events if events is not None else odds.events()
            ev = match_event(events, g["home_name"], g["away_name"], g["tip_utc"])
            if not ev:
                print(f"No Odds API event for {g['away_name']} @ {g['home_name']}")
                g["closing_done"] = True
                continue
            g["event_id"] = ev["id"]
        try:
            data = odds.event_props(g["event_id"])
        except BudgetExceeded as e:
            print(e)
            break
        snap = ROOT / "data" / "odds" / "closing" / f"{plan['brief_date_nzt']}_{g['game_id']}.json"
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps({"fetched_at": now.isoformat(timespec="seconds"), "data": data}))
        cons = consensus(data)
        n = 0
        for r in rows:
            if r["date"] == plan["brief_date_nzt"] and str(r["game_id"]) == str(g["game_id"]):
                c = cons.get((norm_name(r["player"]), r["market"]))
                if c:
                    r["closing_line"], r["closing_over_price"], r["closing_under_price"] = (
                        c["line"], c["over_price"] or "", c["under_price"] or "")
                    n += 1
        g["closing_done"] = True
        print(f"Closing line for {g['away_name']} @ {g['home_name']}: {n} ledger rows updated")
    ledger.write(led_path, rows)
    plan_path.write_text(json.dumps(plan, indent=1))


if __name__ == "__main__":
    main()

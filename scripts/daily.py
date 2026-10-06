"""Daily brief.

Live (GitHub Action, ~09:00 NZT):
    python scripts/daily.py
Replay a past slate from cached box scores (no injuries, no Odds API):
    python scripts/daily.py --replay 2026-03-10
    python scripts/daily.py --replay 2026-03-10 --settle   # the "next day" fill-in

Live order: settle yesterday's ledger rows -> top up the current season ->
fetch today's slate, rosters and injuries -> build the brief -> morning Odds
API call for the top pick games -> write brief, ledger rows and the closing-
line plan. Any ESPN failure publishes "Data source down, no picks".
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nbaprops import brief, config, ledger  # noqa: E402
from nbaprops.http import SourceDown  # noqa: E402
from nbaprops.odds_api import BudgetExceeded, OddsAPI  # noqa: E402
from nbaprops.replay import load  # noqa: E402

NZ = ZoneInfo("Pacific/Auckland")
ET = ZoneInfo("America/New_York")


def write_brief(b: dict, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"brief_{b['brief_date_nzt']}"
    stem.with_suffix(".json").write_text(json.dumps(b, indent=1, default=str))
    stem.with_suffix(".md").write_text(brief.to_markdown(b))
    return stem.with_suffix(".md")


def settle_ledger(path: Path, players: pd.DataFrame, games: pd.DataFrame) -> int:
    """Fill result and P/L for rows whose game is in the processed box scores."""
    rows = ledger.read(path)
    done = set(games["game_id"].astype(str))
    look = brief.results_lookup(players)
    n = 0
    for r in rows:
        if r.get("result") or str(r["game_id"]) not in done:
            continue
        a = look.get((str(r["game_id"]), str(r["player_id"])))
        played = bool(a) and a["min"] > 0
        ledger.settle(r, a[r["market"]] if played else None, played)
        n += 1
    if n:
        ledger.write(path, rows)
    return n


def closing_plan(b: dict, slate: list[brief.SlateGame]) -> dict:
    by_id = {g.game_id: g for g in slate}
    oa = b.get("odds_api") or {}
    return {"brief_date_nzt": b["brief_date_nzt"],
            "games": [{"game_id": gid, "tip_utc": by_id[gid].start_utc, "home_name": by_id[gid].home_name,
                       "away_name": by_id[gid].away_name, "event_id": (oa.get("events") or {}).get(gid),
                       "closing_done": False} for gid in oa.get("top_games", []) if gid in by_id]}


def replay_slate(day: dt.date, games: pd.DataFrame, teams: pd.DataFrame,
                 players: pd.DataFrame) -> list[brief.SlateGame]:
    """A past slate from cached box scores: players listed in the box score count as available."""
    abbr = dict(zip(teams["team_id"], teams["team"]))
    out = []
    for g in games[games["date"] == day].itertuples():
        sg = brief.SlateGame(
            game_id=g.game_id, start_utc=g.start_utc, home_id=g.home_id, away_id=g.away_id,
            home=abbr.get(g.home_id, g.home_id), away=abbr.get(g.away_id, g.away_id),
            home_name=abbr.get(g.home_id, g.home_id), away_name=abbr.get(g.away_id, g.away_id),
            home_spread=None if pd.isna(g.home_spread) else float(g.home_spread))
        for tid, grp in players[players.game_id == g.game_id].groupby("team_id"):
            sg.available[tid] = set(grp["player_id"])
        out.append(sg)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", help="ET slate date to replay from cached box scores (YYYY-MM-DD)")
    ap.add_argument("--settle", action="store_true", help="with --replay: fill results for that slate")
    ap.add_argument("--force", action="store_true", help="live: run outside the 08:00-10:59 NZT window")
    ap.add_argument("--test", action="store_true",
                    help="live pipeline end to end, preseason games allowed, written to output/test/ only")
    args = ap.parse_args()
    cfg = config.load()

    if args.replay:
        run_replay(cfg, dt.date.fromisoformat(args.replay), args.settle)
        return

    now = dt.datetime.now(dt.timezone.utc)
    nz, slate_date = now.astimezone(NZ), now.astimezone(ET).date()
    if args.test:
        run_live(cfg, now, slate_date, ROOT / "output" / "test", test=True)
        return
    out = ROOT / "output"
    if not args.force and (nz.hour not in (8, 9, 10) or (out / f"brief_{nz.date()}.md").exists()):
        print(f"Nothing to do at {nz:%Y-%m-%d %H:%M} NZT (outside window or brief exists).")
        return
    run_live(cfg, now, slate_date, out)


def run_live(cfg: dict, now: dt.datetime, slate_date: dt.date, out: Path, test: bool = False) -> None:
    from nbaprops import live

    led = out / "ledger.csv" if test else ROOT / "ledger.csv"
    try:
        report = live.update_current_season(slate_date)
        slate = live.slate(slate_date, include_preseason=test)
    except SourceDown as e:
        path = write_brief(brief.down_brief(slate_date, now, str(e)), out)
        print(f"ESPN down: wrote {path}")
        return
    hist = load(live.history_seasons(slate_date))
    settled = settle_ledger(led, hist[2], hist[0])
    try:
        odds = OddsAPI()
    except BudgetExceeded:
        odds = None
    b = brief.build(slate_date, slate, hist, cfg, now, season=live.season_for(slate_date), odds=odds)
    b["data"] = {"current_season_games": report.get("games", 0), "ledger_rows_settled": settled}
    path = write_brief(b, out)
    added = ledger.append(led, brief.ledger_rows(b))
    plan = closing_plan(b, slate)
    if plan["games"] and not test:
        p = ROOT / "data" / "picks" / f"{b['brief_date_nzt']}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(plan, indent=1))
    print(f"wrote {path}; {len(b['picks'])} picks, {added} ledger rows added, {settled} settled")


def run_replay(cfg: dict, day: dt.date, settle: bool) -> None:
    out = ROOT / "output" / "replay"
    led = out / "ledger.csv"
    seasons = [s["season"] for s in cfg["backtest"]["seasons"]]
    games, teams, players = load(seasons)
    if settle:
        n = settle_ledger(led, players, games[games["date"] <= day])
        print(f"settled {n} ledger rows for slates up to {day}")
        return
    slate = replay_slate(day, games, teams, players)
    # Brief "generated" at 16:00 ET on the slate date (~09:00-10:00 NZT next morning).
    now = dt.datetime.combine(day, dt.time(16, 0), tzinfo=ET)
    b = brief.build(day, slate, (games, teams, players), cfg, now, season=int(games[games.date == day].season.iat[0]))
    b["mode"] = "replay: injuries and Odds API not available for past dates"
    path = write_brief(b, out)
    added = ledger.append(led, brief.ledger_rows(b))
    print(f"wrote {path}; {len(b['picks'])} picks, {added} ledger rows added to {led}")


if __name__ == "__main__":
    main()

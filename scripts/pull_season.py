"""Pull and cache a full regular season of ESPN box scores for the backtest.

    python scripts/pull_season.py            # season from config.yaml

Every raw response is cached under data/raw/, so reruns only fetch what is
missing. Writes data/processed/{games,team_games,player_games}_<season>.csv.gz
and data/processed/pull_report_<season>.json.

ESPN is the source. A completed game whose ESPN box score is missing or
unusable is filled from Basketball-Reference (rate-limited); players there are
matched to ESPN ids by name within the team.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nbaprops import bbref, config, espn  # noqa: E402
from nbaprops.http import SourceDown  # noqa: E402


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    return re.sub(r"[^a-z]", "", s)


def short_games(teams: list[dict], players: list[dict]) -> list[dict]:
    """Team-games where player points don't add up to the team score (ESPN data holes)."""
    pts = {}
    for p in players:
        pts[(p["game_id"], p["team_id"])] = pts.get((p["game_id"], p["team_id"]), 0) + p["pts"]
    return [{"game_id": t["game_id"], "team": t["team"], "missing_pts": t["pts"] - pts.get((t["game_id"], t["team_id"]), 0)}
            for t in teams if t["pts"] != pts.get((t["game_id"], t["team_id"]), 0)]


def main() -> None:
    cfg = config.load()["backtest"]
    season = cfg["season"]
    start, end = dt.date.fromisoformat(str(cfg["start"])), dt.date.fromisoformat(str(cfg["end"]))
    ef = espn.fetcher()
    bf = None

    # 1. Schedule: one scoreboard per date.
    sched = []
    day = start
    while day <= end:
        sched += espn.parse_scoreboard(espn.scoreboard(ef, day))
        day += dt.timedelta(days=1)
    # ESPN tags All-Star weekend games as regular season; NBA franchises have ids 1-30.
    sched = [g for g in sched if g["season_type"] == espn.REGULAR_SEASON and g["completed"]
             and espn.is_franchise(g["home_id"]) and espn.is_franchise(g["away_id"])]
    sched = list({g["game_id"]: g for g in sched}.values())
    print(f"{len(sched)} completed regular-season games, {ef.network_calls} network calls so far", flush=True)

    # 2. Box scores.
    games, teams, players, gaps, failures = [], [], [], [], []
    for i, g in enumerate(sched):
        try:
            game, t_rows, p_rows = espn.parse_summary(espn.summary(ef, g["game_id"]))
            ok = len(t_rows) == 2 and len({p["team_id"] for p in p_rows if not p["dnp"]}) == 2
        except SourceDown:
            raise  # ESPN down: stop; cached responses let a rerun resume.
        except (KeyError, ValueError, TypeError) as e:
            ok, game, t_rows, p_rows = False, None, [], []
            failures.append({"game_id": g["game_id"], "error": repr(e)[:200]})
        if not ok:
            gaps.append(g)
            continue
        games.append(game)
        teams += t_rows
        players += p_rows
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(sched)} box scores, {ef.network_calls} network calls", flush=True)

    # 3. Basketball-Reference gap fill.
    ids = {(p["team_id"], norm(p["player"])): p["player_id"] for p in players}
    filled = []
    for g in gaps:
        bf = bf or bbref.fetcher()
        try:
            html = bf.get(bbref.boxscore_url(g["start_utc"], g["home"])).decode("utf-8", "replace")
            for side in ("home", "away"):
                tid, opp = (g["home_id"], g["away_id"]) if side == "home" else (g["away_id"], g["home_id"])
                for r in bbref.parse_boxscore(html, g[side]):
                    players.append({
                        "game_id": g["game_id"], "team_id": tid, "opp_id": opp, "home": side == "home",
                        "player_id": ids.get((tid, norm(r["player"])), f"bbref:{r['slug']}"),
                        "player": r["player"], "pos": "", "starter": False, "dnp": r["dnp"],
                        "min": r["min"], "pts": r["pts"], "reb": r["reb"],
                        "fga": r["fga"], "fta": r["fta"], "tov": r["tov"], "source": "bbref",
                    })
            games.append({"game_id": g["game_id"], "start_utc": g["start_utc"], "season": season,
                          "season_type": 2, "completed": True, "neutral": False,
                          "home_id": g["home_id"], "away_id": g["away_id"],
                          "home_spread": None, "total": None})
            filled.append(g["game_id"])
        except Exception as e:  # noqa: BLE001
            failures.append({"game_id": g["game_id"], "error": f"bbref: {e!r}"[:200]})

    out = ROOT / "data" / "processed"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(games).to_csv(out / f"games_{season}.csv.gz", index=False)
    pd.DataFrame(teams).to_csv(out / f"team_games_{season}.csv.gz", index=False)
    pd.DataFrame(players).to_csv(out / f"player_games_{season}.csv.gz", index=False)
    report = {
        "season": season, "scheduled_completed": len(sched), "games": len(games),
        "player_rows": len(players), "espn_gaps": len(gaps), "bbref_filled": filled,
        "failures": failures, "espn_network_calls": ef.network_calls,
        "bbref_network_calls": bf.network_calls if bf else 0,
        "games_with_spread": sum(1 for g in games if g["home_spread"] is not None),
        "box_points_short_of_team_score": short_games(teams, players),
    }
    (out / f"pull_report_{season}.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k not in ("bbref_filled",)}, indent=1))


if __name__ == "__main__":
    main()

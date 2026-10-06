"""Live inputs for the daily brief: current-season history, today's slate, rosters, injuries.

Any ESPN failure raises http.SourceDown; the caller then publishes
"Data source down, no picks".
"""

from __future__ import annotations

import datetime as dt

from . import config, espn
from .brief import SlateGame
from .pull import pull


def season_for(day: dt.date) -> int:
    """ESPN season year for a US date: Oct 2026 - Jun 2027 is season 2027."""
    return day.year + 1 if day.month >= 8 else day.year


def history_seasons(day: dt.date) -> list[int]:
    hist = [s["season"] for s in config.load()["backtest"]["seasons"]]
    cur = season_for(day)
    return sorted(set(s for s in hist if s < cur) | {cur})


def update_current_season(day: dt.date) -> dict:
    """Cache and process the current season's completed games through yesterday (ET)."""
    season = season_for(day)
    start = dt.date(season - 1, 10, 1)
    end = day - dt.timedelta(days=1)
    if end < start:
        return {"season": season, "games": 0}
    return pull(season, start, end, verbose=False)


def slate(day: dt.date, include_preseason: bool = False) -> list[SlateGame]:
    f = espn.fetcher()
    sb = espn.scoreboard(f, day, refresh=True)
    inj_rows = espn.parse_injuries(espn.injuries(f))
    by_team: dict[str, list] = {}
    for r in inj_rows:
        c = espn.injury_class(r)
        if c != "active" and r["player_id"]:
            by_team.setdefault(r["team_id"], []).append({**r, "cls": c})
    games = []
    for e in sb.get("events", []):
        stype = e.get("season", {}).get("type")
        if stype != espn.REGULAR_SEASON and not (include_preseason and stype == 1):
            continue
        comp = e["competitions"][0]
        if comp["status"]["type"]["state"] != "pre":
            continue
        teams = {c["homeAway"]: c["team"] for c in comp["competitors"]}
        if not (espn.is_franchise(teams["home"]["id"]) and espn.is_franchise(teams["away"]["id"])):
            continue  # exhibition sides (international clubs, All-Star teams)
        g = SlateGame(game_id=e["id"], start_utc=comp["date"],
                      home_id=teams["home"]["id"], away_id=teams["away"]["id"],
                      home=teams["home"]["abbreviation"], away=teams["away"]["abbreviation"],
                      home_name=teams["home"]["displayName"], away_name=teams["away"]["displayName"],
                      home_spread=espn.scoreboard_spread(e))
        for tid in (g.home_id, g.away_id):
            roster = {p["player_id"] for p in espn.parse_roster(espn.roster(f, tid, day))}
            out = {i["player_id"] for i in by_team.get(tid, []) if i["cls"] in ("out", "doubtful")}
            g.available[tid] = roster - out
            g.injuries[tid] = by_team.get(tid, [])
        games.append(g)
    return games

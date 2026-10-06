"""ESPN public JSON: URLs, fetching through the raw cache, and parsers."""

from __future__ import annotations

import datetime as dt

from . import config
from .http import Fetcher

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
REGULAR_SEASON = 2


def is_franchise(team_id: str) -> bool:
    """ESPN ids 1-30 are NBA franchises; All-Star and exhibition sides use other ids."""
    return str(team_id).isdigit() and 1 <= int(team_id) <= 30


def fetcher(cache_dir=None) -> Fetcher:
    cfg = config.load()["sources"]["espn"]
    return Fetcher("espn", cfg["min_interval_s"], cache_dir=cache_dir)


def scoreboard(f: Fetcher, day: dt.date, refresh: bool = False) -> dict:
    return f.get_json(f"{SITE}/scoreboard", {"dates": day.strftime("%Y%m%d")},
                      name=f"scoreboard/{day:%Y%m%d}", refresh=refresh)


def summary(f: Fetcher, event_id: str, refresh: bool = False) -> dict:
    return f.get_json(f"{SITE}/summary", {"event": event_id}, name=f"summary/{event_id}", refresh=refresh)


def injuries(f: Fetcher) -> dict:
    return f.get_json(f"{SITE}/injuries", name=f"injuries/{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M}", refresh=True)


# ---------------------------------------------------------------- parsers


def parse_scoreboard(sb: dict) -> list[dict]:
    """One row per game on a scoreboard."""
    out = []
    for e in sb.get("events", []):
        comp = e["competitions"][0]
        teams = {c["homeAway"]: c for c in comp["competitors"]}
        out.append({
            "game_id": e["id"],
            "start_utc": comp["date"],
            "season_type": e.get("season", {}).get("type"),
            "completed": comp["status"]["type"]["completed"],
            "home_id": teams["home"]["team"]["id"],
            "home": teams["home"]["team"]["abbreviation"],
            "away_id": teams["away"]["team"]["id"],
            "away": teams["away"]["team"]["abbreviation"],
        })
    return out


def _minutes(s: str) -> float:
    if not s or s == "--":
        return 0.0
    if ":" in s:
        m, sec = s.split(":")
        return int(m) + int(sec) / 60
    return float(s)


def _made_att(s: str) -> tuple[int, int]:
    m, a = s.split("-")
    return int(m), int(a)


def parse_summary(s: dict) -> tuple[dict, list[dict], list[dict]]:
    """Return (game, team_rows, player_rows) from an ESPN game summary.

    Player rows include DNP entries (dnp=True). Players who were inactive or
    injured do not appear in ESPN box scores at all.
    """
    comp = s["header"]["competitions"][0]
    teams = {c["homeAway"]: c for c in comp["competitors"]}
    home_id, away_id = teams["home"]["team"]["id"], teams["away"]["team"]["id"]

    spread = total = None
    for pc in s.get("pickcenter") or []:
        if pc.get("spread") is not None:
            spread, total = pc.get("spread"), pc.get("overUnder")
            break
    game = {
        "game_id": comp["id"],
        "start_utc": comp["date"],
        "season": s["header"]["season"]["year"],
        "season_type": s["header"]["season"]["type"],
        "completed": comp["status"]["type"]["completed"],
        "neutral": comp.get("neutralSite", False),
        "home_id": home_id,
        "away_id": away_id,
        "home_spread": spread,  # negative = home favoured
        "total": total,
    }

    team_rows = []
    for bt in s.get("boxscore", {}).get("teams", []):
        tid = bt["team"]["id"]
        st = {x["name"]: x["displayValue"] for x in bt["statistics"]}
        fgm, fga = _made_att(st["fieldGoalsMade-fieldGoalsAttempted"])
        ftm, fta = _made_att(st["freeThrowsMade-freeThrowsAttempted"])
        oreb = int(st["offensiveRebounds"])
        tov = int(st.get("totalTurnovers", st.get("turnovers", 0)))
        side = "home" if tid == home_id else "away"
        team_rows.append({
            "game_id": game["game_id"],
            "team_id": tid,
            "team": bt["team"]["abbreviation"],
            "opp_id": away_id if side == "home" else home_id,
            "home": side == "home",
            "pts": int(teams[side].get("score") or 0),
            "fga": fga, "fta": fta, "oreb": oreb, "tov": tov,
            "reb": int(st["totalRebounds"]),
            "poss": fga - oreb + tov + 0.44 * fta,
        })

    player_rows = []
    for bp in s.get("boxscore", {}).get("players", []):
        tid = bp["team"]["id"]
        block = bp["statistics"][0]
        keys = block["keys"]
        for a in block["athletes"]:
            ath = a["athlete"]
            if "id" not in ath:
                # ESPN sometimes lists an unlinked placeholder (shortName only, no id).
                if a.get("didNotPlay") or not a.get("stats"):
                    continue
                ath = {**ath, "id": f"noid:{tid}:{ath.get('shortName', '?')}",
                       "displayName": ath.get("shortName", "?")}
            row = {
                "game_id": game["game_id"],
                "team_id": tid,
                "opp_id": away_id if tid == home_id else home_id,
                "home": tid == home_id,
                "player_id": ath["id"],
                "player": ath["displayName"],
                "pos": (ath.get("position") or {}).get("abbreviation", ""),
                "starter": bool(a.get("starter")),
                "dnp": bool(a.get("didNotPlay")) or not a.get("stats"),
                "min": 0.0, "pts": 0, "reb": 0, "fga": 0, "fta": 0, "tov": 0,
            }
            if not row["dnp"]:
                v = dict(zip(keys, a["stats"]))
                row["min"] = _minutes(v["minutes"])
                row["pts"] = int(v["points"])
                row["reb"] = int(v["rebounds"])
                row["fga"] = _made_att(v["fieldGoalsMade-fieldGoalsAttempted"])[1]
                row["fta"] = _made_att(v["freeThrowsMade-freeThrowsAttempted"])[1]
                row["tov"] = int(v["turnovers"])
            player_rows.append(row)
    return game, team_rows, player_rows

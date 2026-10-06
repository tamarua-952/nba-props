"""Step 0: probe every candidate free data source and report what works.

Run from GitHub Actions and from a home connection; cloud IPs are often
blocked by stats.nba.com and some odds sites, so results differ by network.

    python scripts/probe_sources.py --label local

Writes output/step0/source_report_<label>.{json,md}. Exits 0 even when
sources fail: the report is the deliverable, not a pass/fail gate.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import requests

TIMEOUT = 30
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)
# A known completed regular-season date and player used for historical checks.
PAST_DATE = dt.date(2026, 3, 15)
JOKIC_NBA_ID = 203999
JOKIC_ESPN_ID = 3112335
SEASON = "2025-26"
PREV_SEASON = "2024-25"

ESPN_SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ESPN_CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"


@dataclass
class Result:
    name: str
    category: str
    ok: bool
    detail: str
    seconds: float
    status: str = ""  # OK / FAIL / SKIP
    notes: list[str] = field(default_factory=list)


def get(url: str, **kw) -> requests.Response:
    headers = {"User-Agent": UA, "Accept": "*/*"}
    headers.update(kw.pop("headers", {}))
    return requests.get(url, headers=headers, timeout=kw.pop("timeout", TIMEOUT), **kw)


def get_json(url: str, **kw):
    r = get(url, **kw)
    r.raise_for_status()
    return r.json()


class Skip(Exception):
    pass


# ---------------------------------------------------------------- game logs


def nba_api_league_gamelog(season: str):
    def check():
        from nba_api.stats.endpoints import leaguegamelog

        df = leaguegamelog.LeagueGameLog(
            season=season, player_or_team_abbreviation="P", timeout=TIMEOUT
        ).get_data_frames()[0]
        assert len(df) > 1000, f"only {len(df)} rows"
        cols = {"PLAYER_ID", "MIN", "PTS", "REB", "GAME_DATE", "MATCHUP"}
        missing = cols - set(df.columns)
        assert not missing, f"missing cols {missing}"
        return f"{len(df)} player-game rows, {df.GAME_DATE.min()}..{df.GAME_DATE.max()}"

    return check


def nba_api_player_gamelog():
    from nba_api.stats.endpoints import playergamelog

    df = playergamelog.PlayerGameLog(
        player_id=JOKIC_NBA_ID, season=SEASON, timeout=TIMEOUT
    ).get_data_frames()[0]
    assert len(df) > 10, f"only {len(df)} rows"
    return f"Jokic {SEASON}: {len(df)} games, last {df.iloc[0].GAME_DATE} PTS={df.iloc[0].PTS}"


def nba_api_team_pace():
    from nba_api.stats.endpoints import leaguedashteamstats

    df = leaguedashteamstats.LeagueDashTeamStats(
        season=SEASON, measure_type_detailed_defense="Advanced", timeout=TIMEOUT
    ).get_data_frames()[0]
    assert "PACE" in df.columns and len(df) == 30, f"{len(df)} rows"
    return f"30 teams, pace {df.PACE.min():.1f}-{df.PACE.max():.1f}"


def nba_api_player_index():
    from nba_api.stats.endpoints import playerindex

    df = playerindex.PlayerIndex(season=SEASON, timeout=TIMEOUT).get_data_frames()[0]
    assert len(df) > 300, f"only {len(df)} rows"
    return f"{len(df)} players with POSITION (e.g. {df.iloc[0].POSITION!r})"


def nba_cdn_boxscore():
    sched = get_json("https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json")
    # Find any completed game to fetch a box score for.
    game_id = None
    for d in sched["leagueSchedule"]["gameDates"]:
        for g in d["games"]:
            if g.get("gameStatus") == 3:
                game_id = g["gameId"]
        if game_id:
            break
    if not game_id:
        game_id = "0022500900"  # 2025-26 regular season fallback
    box = get_json(f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json")
    players = box["game"]["homeTeam"]["players"]
    p = players[0]
    return f"game {game_id}: {len(players)} home players, {p['name']} min={p['statistics']['minutes']}"


def espn_past_boxscore():
    sb = get_json(f"{ESPN_SITE}/scoreboard", params={"dates": PAST_DATE.strftime("%Y%m%d")})
    events = sb.get("events", [])
    assert events, "no events on past date"
    summ = get_json(f"{ESPN_SITE}/summary", params={"event": events[0]["id"]})
    teams = summ["boxscore"]["players"]
    labels = teams[0]["statistics"][0]["labels"]
    n = sum(len(t["statistics"][0]["athletes"]) for t in teams)
    return f"{len(events)} games on {PAST_DATE}; summary has {n} players, stats {labels[:6]}"


def espn_athlete_gamelog():
    url = f"https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{JOKIC_ESPN_ID}/gamelog"
    data = get_json(url)
    n = len(data.get("events", {}))
    assert n > 0, "no events"
    return f"Jokic gamelog: {n} events, labels {data.get('labels', [])[:6]}"


def bbref_gamelog():
    r = get("https://www.basketball-reference.com/players/j/jokicni01/gamelog/2026")
    r.raise_for_status()
    rows = len(re.findall(r'<tr id="player_game_log_reg', r.text)) or r.text.count('data-stat="pts"')
    assert rows > 10, "game log table not found"
    return f"HTML {len(r.text)//1024} KB, ~{rows} game rows (rate limit: <20 req/min)"


# ---------------------------------------------------------------- schedule


def nba_cdn_schedule():
    sched = get_json("https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json")
    ls = sched["leagueSchedule"]
    games = [g for d in ls["gameDates"] for g in d["games"]]
    upcoming = [g for g in games if g.get("gameStatus") == 1]
    first = upcoming[0] if upcoming else games[-1]
    return (
        f"season {ls.get('seasonYear')}: {len(games)} games, {len(upcoming)} upcoming; "
        f"next {first['awayTeam']['teamTricode']}@{first['homeTeam']['teamTricode']} {first['gameDateTimeUTC']}"
    )


def nba_cdn_today():
    data = get_json("https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json")
    sb = data["scoreboard"]
    return f"gameDate {sb['gameDate']}: {len(sb['games'])} games"


def nba_api_scoreboard_v3():
    from nba_api.stats.endpoints import scoreboardv3

    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    sb = scoreboardv3.ScoreboardV3(game_date=today, timeout=TIMEOUT).get_dict()
    games = sb["scoreboard"]["games"]
    return f"{today}: {len(games)} games"


def espn_scoreboard_today():
    today = dt.datetime.now(dt.timezone.utc).date()
    out = []
    spreads = 0
    for d in (today, today + dt.timedelta(days=1)):
        sb = get_json(f"{ESPN_SITE}/scoreboard", params={"dates": d.strftime("%Y%m%d")})
        ev = sb.get("events", [])
        spreads += sum(1 for e in ev if e["competitions"][0].get("odds"))
        out.append(f"{d}: {len(ev)} games")
    return "; ".join(out) + f"; {spreads} with spread/total attached"


# ---------------------------------------------------------------- injuries


def nba_official_injury_report():
    pdf_re = re.compile(r"https://ak-static\.cms\.nba\.com/referee/injury/Injury-Report_[^\"']+\.pdf")
    links, tried = [], []
    for season in ("2026-27", "2025-26"):
        url = f"https://official.nba.com/nba-injury-report-{season}-season/"
        tried.append(url)
        r = get(url)
        if r.ok:
            links = sorted(set(pdf_re.findall(r.text)))
            if links:
                break
    assert links, f"no PDF links on {tried}"
    latest = links[-1]
    pdf = get(latest)
    pdf.raise_for_status()
    assert pdf.content[:4] == b"%PDF", "not a PDF"
    return f"{len(links)} PDF links; latest {latest.rsplit('/', 1)[-1]} ({len(pdf.content)//1024} KB). Needs PDF parsing."


def espn_injuries_api():
    data = get_json(f"{ESPN_SITE}/injuries")
    teams = data.get("injuries", [])
    n = sum(len(t.get("injuries", [])) for t in teams)
    sample = ""
    for t in teams:
        for i in t.get("injuries", []):
            sample = f"{i['athlete']['displayName']}: {i.get('status')}"
            break
        if sample:
            break
    return f"{len(teams)} teams, {n} injury entries; e.g. {sample or 'none'}"


def espn_injuries_page():
    r = get("https://www.espn.com/nba/injuries")
    r.raise_for_status()
    n = r.text.count("Table__TR")
    return f"HTML {len(r.text)//1024} KB, ~{n} table rows"


# ---------------------------------------------------------------- consensus lines


def odds_api():
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise Skip("ODDS_API_KEY not set (free tier: 500 credits/month at the-odds-api.com)")
    base = "https://api.the-odds-api.com/v4/sports/basketball_nba"
    r = get(f"{base}/events", params={"apiKey": key})
    r.raise_for_status()
    events = r.json()
    msg = f"{len(events)} upcoming events"
    if events:
        r = get(
            f"{base}/events/{events[0]['id']}/odds",
            params={"apiKey": key, "regions": "us,au", "markets": "player_points,player_rebounds"},
        )
        r.raise_for_status()
        books = r.json().get("bookmakers", [])
        n = sum(len(m["outcomes"]) for b in books for m in b["markets"])
        msg += f"; event 0: {len(books)} books, {n} prop outcomes"
    return msg + f"; credits remaining {r.headers.get('x-requests-remaining')}"


def espn_prop_bets():
    """ESPN's core API exposes sportsbook prop bets for some events (undocumented)."""
    today = dt.datetime.now(dt.timezone.utc).date()
    for d in (today, today + dt.timedelta(days=1), PAST_DATE):
        ev = get_json(f"{ESPN_SITE}/scoreboard", params={"dates": d.strftime("%Y%m%d")}).get("events", [])
        if ev:
            break
    assert ev, "no events to test"
    eid = ev[0]["id"]
    odds = get_json(f"{ESPN_CORE}/events/{eid}/competitions/{eid}/odds")
    providers = [i["$ref"].rstrip("/").split("/")[-1].split("?")[0] for i in odds.get("items", [])]
    assert providers, f"event {eid}: no odds providers"
    found = []
    for pid in providers:
        r = get(f"{ESPN_CORE}/events/{eid}/competitions/{eid}/odds/{pid}/propBets", params={"limit": 50})
        if r.ok and r.json().get("count", 0) > 0:
            found.append(f"provider {pid}: {r.json()['count']} props")
    assert found, f"event {eid} ({d}): providers {providers} have no propBets"
    return f"event {eid} ({d}): " + ", ".join(found)


def prizepicks():
    data = get_json(
        "https://api.prizepicks.com/projections",
        params={"league_id": 7, "per_page": 250, "single_stat": "true"},
        headers={"Accept": "application/json"},
    )
    proj = data.get("data", [])
    types = sorted({p["attributes"].get("stat_type") for p in proj})[:6]
    return f"{len(proj)} NBA projections; stat types {types} (DFS lines, not sportsbook)"


def underdog():
    data = get_json("https://api.underdogfantasy.com/beta/v5/over_under_lines")
    lines = data.get("over_under_lines", [])
    return f"{len(lines)} lines across all sports (DFS lines, not sportsbook)"


CHECKS: list[tuple[str, str, Callable[[], str]]] = [
    ("Game logs", f"nba_api LeagueGameLog {SEASON} (all players, 1 call)", nba_api_league_gamelog(SEASON)),
    ("Game logs", f"nba_api LeagueGameLog {PREV_SEASON}", nba_api_league_gamelog(PREV_SEASON)),
    ("Game logs", "nba_api PlayerGameLog", nba_api_player_gamelog),
    ("Game logs", "nba_api team pace (Advanced)", nba_api_team_pace),
    ("Game logs", "nba_api PlayerIndex (positions)", nba_api_player_index),
    ("Game logs", "NBA CDN box score JSON", nba_cdn_boxscore),
    ("Game logs", "ESPN scoreboard + summary box score", espn_past_boxscore),
    ("Game logs", "ESPN athlete gamelog", espn_athlete_gamelog),
    ("Game logs", "Basketball-Reference player gamelog", bbref_gamelog),
    ("Schedule", "NBA CDN season schedule", nba_cdn_schedule),
    ("Schedule", "NBA CDN today's scoreboard", nba_cdn_today),
    ("Schedule", "nba_api ScoreboardV3 today", nba_api_scoreboard_v3),
    ("Schedule", "ESPN scoreboard today/tomorrow (+spreads)", espn_scoreboard_today),
    ("Injuries", "Official NBA injury report (PDF)", nba_official_injury_report),
    ("Injuries", "ESPN injuries JSON", espn_injuries_api),
    ("Injuries", "ESPN injuries HTML page", espn_injuries_page),
    ("Consensus lines", "The Odds API (free tier)", odds_api),
    ("Consensus lines", "ESPN core API propBets", espn_prop_bets),
    ("Consensus lines", "PrizePicks public API", prizepicks),
    ("Consensus lines", "Underdog public API", underdog),
]


def run_check(category: str, name: str, fn: Callable[[], str]) -> Result:
    t0 = time.monotonic()
    try:
        detail = fn()
        status, ok = "OK", True
    except Skip as e:
        detail, status, ok = str(e), "SKIP", False
    except requests.HTTPError as e:
        detail, status, ok = f"HTTP {e.response.status_code} from {e.response.url[:120]}", "FAIL", False
    except Exception as e:  # noqa: BLE001 - every failure mode is a finding
        last = traceback.format_exception_only(type(e), e)[-1].strip()
        detail, status, ok = last[:300], "FAIL", False
    return Result(name, category, ok, detail, round(time.monotonic() - t0, 1), status)


def to_markdown(label: str, when: str, results: list[Result]) -> str:
    lines = [
        f"# Step 0 source report — {label}",
        "",
        f"Run at {when} UTC. {sum(r.ok for r in results)}/{len(results)} checks OK.",
        "",
        "| Category | Source | Status | Secs | Detail |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        detail = r.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r.category} | {r.name} | {r.status} | {r.seconds} | {detail} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default=os.environ.get("PROBE_LABEL", "local"))
    ap.add_argument("--out", default="output/step0")
    args = ap.parse_args()

    when = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    results = []
    for category, name, fn in CHECKS:
        r = run_check(category, name, fn)
        print(f"[{r.status:4}] {category:15} {name:45} {r.seconds:5}s  {r.detail}", flush=True)
        results.append(r)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    md = to_markdown(args.label, when, results)
    (out / f"source_report_{args.label}.md").write_text(md)
    (out / f"source_report_{args.label}.json").write_text(
        json.dumps({"label": args.label, "run_at_utc": when, "results": [asdict(r) for r in results]}, indent=2)
    )
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(md)


if __name__ == "__main__":
    main()

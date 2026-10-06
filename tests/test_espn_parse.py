import gzip
import json
from pathlib import Path

from nbaprops import espn

FIX = Path(__file__).parent / "fixtures" / "espn"


def load(name):
    return json.loads(gzip.decompress((FIX / name).read_bytes()))


def test_parse_summary():
    game, teams, players = espn.parse_summary(load("summary_401810831.gz"))
    assert game["season"] == 2026 and game["season_type"] == 2 and game["completed"]
    assert game["home_spread"] == -8.5 and game["total"] == 227.5
    assert {t["team"] for t in teams} == {"OKC", "MIN"}
    by_team = {t["team"]: t for t in teams}
    assert by_team["OKC"]["pts"] == 116 and by_team["MIN"]["pts"] == 103
    assert all(80 < t["poss"] < 130 for t in teams)
    randle = next(p for p in players if p["player"] == "Julius Randle")
    assert (randle["min"], randle["pts"], randle["reb"], randle["pos"]) == (35, 32, 7, "F")
    assert not randle["home"] and randle["starter"]
    conley = next(p for p in players if p["player"] == "Mike Conley")
    assert conley["dnp"] and conley["min"] == 0
    # box score points add up to the team score
    for t in teams:
        assert sum(p["pts"] for p in players if p["team_id"] == t["team_id"]) == t["pts"]


def test_parse_scoreboard():
    games = espn.parse_scoreboard(load("scoreboard_20260315.gz"))
    assert len(games) == 7
    assert all(g["completed"] and g["season_type"] == 2 for g in games)


def test_placeholder_athlete_without_id_is_skipped_when_dnp():
    s = load("summary_401810831.gz")
    block = s["boxscore"]["players"][0]["statistics"][0]
    block["athletes"].append({"athlete": {"links": [], "shortName": "Olbrich"}, "starter": False,
                              "didNotPlay": True, "stats": []})
    _, _, players = espn.parse_summary(s)
    assert not any(p["player"] == "Olbrich" for p in players)

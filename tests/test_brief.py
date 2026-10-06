import datetime as dt

from nbaprops import brief, live


def pick(**kw):
    p = {"game_id": "1", "tip_utc": "2026-03-11T00:00Z", "tip_nzt": "Wed 11 Mar 13:00 NZT", "player_id": "9",
         "player": "A Player", "team": "AAA", "opp": "BBB", "home": True, "market": "REB", "side": "under",
         "line": 7.5, "projection": 5.9, "proj_min": 30.0, "last10_avg": 7.2, "model_prob": 0.66, "edge": 0.12,
         "fair_odds": 1.52, "threshold": 1.59, "flags": ["INJURY_PENDING"], "injury_pending": ["B Star (questionable)"],
         "ladder": [{"line": 6.5, "side": "under", "model_prob": 0.56, "threshold": 1.88}],
         "reasoning": "Under: proj 5.9 reb.", "consensus": {"line": 7.0, "books": 3, "model_prob_at_line": 0.6,
                                                            "market_prob_no_vig": 0.5}}
    p.update(kw)
    return p


def brief_dict(picks):
    return {"brief_date_nzt": "2026-03-11", "slate_date_et": "2026-03-10", "generated_at_utc": "x",
            "status": "OK", "message": "", "games": 1, "games_playable": 1, "candidates": 5,
            "markets": ["PTS", "REB"], "calibration": {"REB": {"shrink": 1.0, "offset": -0.01, "cap": None}},
            "margin_buffer": 0.05, "odds_api": {"top_games": ["1"], "morning_calls": 1, "note": ""}, "picks": picks}


def test_markdown_lists_pick_threshold_ladder_and_flags():
    md = brief.to_markdown(brief_dict([pick()]))
    assert "UNDER 7.5" in md and "**$1.59**" in md and "INJURY_PENDING" in md
    assert "6.5 U ≥$1.88" in md and "B Star (questionable)" in md and "Consensus line 7.0" in md


def test_down_brief_has_no_picks():
    b = brief.down_brief(dt.date(2026, 3, 10), dt.datetime(2026, 3, 10, 21, tzinfo=dt.timezone.utc), "HTTP 503")
    assert b["status"] == "DATA_SOURCE_DOWN" and b["picks"] == []
    assert "Data source down, no picks" in brief.to_markdown(b)


def test_ledger_rows_leave_user_columns_blank():
    rows = brief.ledger_rows(brief_dict([pick()]))
    assert rows[0]["flags"] == "INJURY_PENDING" and rows[0]["consensus_line"] == 7.0
    assert "betcha_price" not in rows[0]


def test_select_one_per_player_by_edge():
    a = pick(market="PTS", edge=0.05)
    b = pick(market="REB", edge=0.10)
    c = pick(player_id="8", edge=0.07)
    assert [(p["player_id"], p["market"]) for p in brief.select([a, b, c], 8)] == [("9", "REB"), ("8", "REB")]


def test_season_for():
    assert live.season_for(dt.date(2026, 10, 21)) == 2027
    assert live.season_for(dt.date(2027, 3, 1)) == 2027

import datetime as dt
import json

import pytest

from nbaprops.odds_api import BudgetExceeded, OddsAPI


def make(tmp_path, calls):
    f = tmp_path / "usage.json"
    f.write_text(json.dumps({"calls": calls}))
    return OddsAPI(api_key="test", usage_file=f)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def test_first_call_of_month_allowed(tmp_path):
    make(tmp_path, []).check_budget("event_odds")


def test_unobserved_cost_uses_markets_times_regions(tmp_path):
    assert make(tmp_path, []).estimated_cost("event_odds") == 2


def test_uses_max_observed_cost(tmp_path):
    api = make(tmp_path, [
        {"at": now(), "kind": "event_odds", "cost": 2, "remaining": 400},
        {"at": now(), "kind": "event_odds", "cost": 4, "remaining": 396},
    ])
    assert api.estimated_cost("event_odds") == 4
    assert api.remaining() == 396


def test_guard_stops_before_reserve(tmp_path):
    api = make(tmp_path, [{"at": now(), "kind": "event_odds", "cost": 2, "remaining": 41}])
    with pytest.raises(BudgetExceeded):
        api.check_budget("event_odds")  # 41 - 2 < 40


def test_guard_allows_when_above_reserve(tmp_path):
    api = make(tmp_path, [{"at": now(), "kind": "event_odds", "cost": 2, "remaining": 42}])
    api.check_budget("event_odds")


def test_last_month_balance_ignored(tmp_path):
    api = make(tmp_path, [{"at": "2000-01-01T00:00:00+00:00", "kind": "event_odds", "cost": 2, "remaining": 1}])
    assert api.remaining() is None
    api.check_budget("event_odds")


def test_can_afford_reserves_for_closing(tmp_path):
    api = make(tmp_path, [{"at": now(), "kind": "event_odds", "cost": 2, "remaining": 52}])
    assert api.can_afford("event_odds", 6)       # 52 - 12 = 40
    assert not api.can_afford("event_odds", 7)   # 52 - 14 < 40


def test_match_event_and_consensus():
    from nbaprops.odds_api import consensus, match_event

    events = [{"id": "e1", "home_team": "Los Angeles Clippers", "away_team": "Utah Jazz",
               "commence_time": "2026-03-11T03:00:00Z"}]
    assert match_event(events, "LA Clippers", "Utah Jazz", "2026-03-11T03:30Z")["id"] == "e1"
    assert match_event(events, "LA Clippers", "Utah Jazz", "2026-03-12T03:30Z") is None
    odds = {"bookmakers": [
        {"key": "a", "markets": [{"key": "player_points", "outcomes": [
            {"name": "Over", "description": "Kawhi Leonard", "price": 1.9, "point": 24.5},
            {"name": "Under", "description": "Kawhi Leonard", "price": 1.9, "point": 24.5}]}]},
        {"key": "b", "markets": [{"key": "player_points", "outcomes": [
            {"name": "Over", "description": "Kawhi Leonard", "price": 1.8, "point": 24.5},
            {"name": "Under", "description": "Kawhi Leonard", "price": 2.0, "point": 24.5}]}]},
        {"key": "c", "markets": [{"key": "player_points", "outcomes": [
            {"name": "Over", "description": "Kawhi Leonard", "price": 1.9, "point": 25.5}]}]},
    ]}
    c = consensus(odds)[("kawhileonard", "PTS")]
    assert c["line"] == 24.5 and c["books"] == 2
    assert c["over_price"] == pytest.approx(1.85) and c["under_price"] == pytest.approx(1.95)

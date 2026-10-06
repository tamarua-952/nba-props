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

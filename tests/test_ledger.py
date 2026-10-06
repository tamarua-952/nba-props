import pytest

from nbaprops import ledger


def row(**kw):
    r = {"date": "2026-03-11", "game_id": "1", "player_id": "9", "player": "X", "market": "PTS",
         "side": "over", "line": "24.5", "threshold": "1.9"}
    r.update(kw)
    return r


def test_grade():
    assert ledger.grade("over", 24.5, 25, True) == "WIN"
    assert ledger.grade("over", 24.5, 24, True) == "LOSS"
    assert ledger.grade("under", 24.5, 24, True) == "WIN"
    assert ledger.grade("under", 24, 24, True) == "PUSH"
    assert ledger.grade("over", 24.5, None, False) == "VOID"


def test_settle_paper_only():
    r = ledger.settle(row(), 27, True)
    assert r["result"] == "WIN" and r["pl_units"] == "" and r["paper_pl_units"] == pytest.approx(0.9)


def test_settle_uses_betcha_line_and_price():
    r = ledger.settle(row(betcha_line="25.5", betcha_price="1.95"), 25, True)
    assert r["result"] == "LOSS" and r["pl_units"] == -1.0
    assert r["paper_pl_units"] == pytest.approx(0.9)  # brief line 24.5 still won on paper


def test_void_when_not_played():
    r = ledger.settle(row(betcha_price="1.95"), None, False)
    assert r["result"] == "VOID" and r["pl_units"] == 0.0


def test_clv():
    r = ledger.settle(row(betcha_line="24.5", betcha_price="2.0", closing_line="24.5",
                          closing_over_price="1.80", closing_under_price="2.00"), 20, True)
    fair_over = (1 / 1.8) / (1 / 1.8 + 1 / 2.0)
    assert r["clv_pct"] == pytest.approx(round(2.0 * fair_over - 1, 4))
    assert r["clv_line"] == 0
    r = ledger.settle(row(closing_line="26.5"), 20, True)
    assert r["clv_line"] == 2.0


def test_append_dedupes(tmp_path):
    p = tmp_path / "ledger.csv"
    assert ledger.append(p, [row()]) == 1
    assert ledger.append(p, [row(), row(market="REB")]) == 1
    assert len(ledger.read(p)) == 2

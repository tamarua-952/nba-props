import math

import pytest
from scipy import stats

from nbaprops import dist


def test_count_dist_matches_requested_moments():
    d = dist.count_dist(22.0, 60.0)
    assert d.mean() == pytest.approx(22.0)
    assert d.var() == pytest.approx(60.0)


def test_underdispersed_falls_back_to_poisson():
    d = dist.count_dist(8.0, 6.0)
    assert d.mean() == pytest.approx(8.0)
    assert d.var() == pytest.approx(8.0)


def test_nonpositive_mean_rejected():
    with pytest.raises(ValueError):
        dist.count_dist(0.0, 1.0)


def test_half_line_over_under_sum_to_one():
    p = dist.line_probs(24.5, 25.0, 70.0)
    assert p.push == 0
    assert p.over + p.under == pytest.approx(1.0)


def test_half_line_matches_cdf():
    p = dist.line_probs(9.5, 10.0, 18.0)
    assert p.under == pytest.approx(dist.count_dist(10.0, 18.0).cdf(9))


def test_whole_line_has_push():
    p = dist.line_probs(10, 10.0, 18.0)
    d = dist.count_dist(10.0, 18.0)
    assert p.push == pytest.approx(d.pmf(10))
    assert p.over == pytest.approx(1 - d.cdf(10))
    assert p.under == pytest.approx(d.cdf(9))
    assert p.over + p.under + p.push == pytest.approx(1.0)


def test_zero_line():
    p = dist.line_probs(0, 2.0, 2.0)
    assert p.under == 0
    assert p.push == pytest.approx(math.exp(-2))


def test_over_probability_falls_as_line_rises():
    probs = [dist.line_probs(x + 0.5, 20.0, 50.0).over for x in range(10, 30)]
    assert all(a > b for a, b in zip(probs, probs[1:]))


def test_poisson_case_matches_scipy():
    p = dist.line_probs(5.5, 6.0, 6.0)
    assert p.over == pytest.approx(stats.poisson(6.0).sf(5))


def test_more_variance_pulls_probability_toward_half_for_line_at_mean():
    tight = dist.line_probs(15.5, 20.0, 21.0).over
    loose = dist.line_probs(15.5, 20.0, 120.0).over
    assert tight > loose > 0.5


def test_fair_odds_and_threshold():
    assert dist.fair_odds(0.5) == pytest.approx(2.0)
    assert dist.fair_odds(0.6) == pytest.approx(1 / 0.6)
    assert dist.bet_threshold(0.6, 0.05) == pytest.approx(1.05 / 0.6)
    assert dist.bet_threshold(0.5, 0.0) == pytest.approx(2.0)


@pytest.mark.parametrize("p", [0.0, 1.0, -0.1, 1.2])
def test_fair_odds_rejects_degenerate(p):
    with pytest.raises(ValueError):
        dist.fair_odds(p)


def test_ev_is_zero_at_fair_price_and_positive_at_threshold():
    p = 0.58
    assert dist.expected_value(p, dist.fair_odds(p)) == pytest.approx(0.0)
    assert dist.expected_value(p, dist.bet_threshold(p, 0.05)) == pytest.approx(0.05)


def test_edge_vs_typical_price():
    # $1.87 implies ~53.5%
    assert dist.edge_vs_price(0.60, 1.87) == pytest.approx(0.60 - 1 / 1.87)

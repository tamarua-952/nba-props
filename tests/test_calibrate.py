import numpy as np

from nbaprops.calibrate import Recalibrator


def simulate(n, true_s, true_c, seed=0):
    rng = np.random.default_rng(seed)
    q = rng.uniform(0.2, 0.8, n)
    p_true = 0.5 + true_s * (q - 0.5) + true_c
    return q, (rng.random(n) < p_true).astype(int)


def test_identity_until_min_obs_except_cap():
    r = Recalibrator(shrink=True, offset=True, cap=0.7, min_obs=100)
    assert r.params() is None
    assert np.allclose(r.apply([0.6, 0.9, 0.1]), [0.6, 0.7, 0.3])


def test_recovers_shrink_and_offset():
    q, y = simulate(15_000, 0.75, -0.02)
    r = Recalibrator(shrink=True, offset=True, min_obs=100)
    r.update(q, y)
    s, c = r.params()
    assert abs(s - 0.75) < 0.1 and abs(c + 0.02) < 0.015


def test_offset_only_keeps_slope_one():
    q, y = simulate(15_000, 1.0, 0.03)
    r = Recalibrator(shrink=False, offset=True, min_obs=100)
    r.update(q, y)
    s, c = r.params()
    assert s == 1.0 and abs(c - 0.03) < 0.015


def test_cap_is_symmetric():
    r = Recalibrator(shrink=False, offset=False, cap=0.7)
    assert np.allclose(r.apply([0.95, 0.05, 0.5]), [0.7, 0.3, 0.5])

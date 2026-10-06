"""Probability and fair-odds maths.

Points and rebounds are modelled as negative binomial counts parameterised by
mean and variance. When variance <= mean (under-dispersed), fall back to
Poisson, the NB limit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy import stats


@dataclass(frozen=True)
class LineProbs:
    over: float
    under: float
    push: float


def count_dist(mean: float, var: float):
    """Frozen scipy distribution for a count with the given mean and variance."""
    if mean <= 0:
        raise ValueError(f"mean must be positive, got {mean}")
    if var <= mean * (1 + 1e-9):
        return stats.poisson(mean)
    r = mean * mean / (var - mean)
    return stats.nbinom(r, r / (r + mean))


def line_probs(line: float, mean: float, var: float) -> LineProbs:
    """P(over), P(under), P(push) for a prop line.

    Half-point lines cannot push. On a whole-number line, landing exactly on
    it is a push (stake refunded), so over and under do not sum to 1.
    """
    d = count_dist(mean, var)
    if line != math.floor(line):
        under = float(d.cdf(math.floor(line)))
        return LineProbs(over=1.0 - under, under=under, push=0.0)
    k = int(line)
    push = float(d.pmf(k))
    under = float(d.cdf(k - 1)) if k > 0 else 0.0
    return LineProbs(over=1.0 - under - push, under=under, push=push)


def fair_odds(p: float) -> float:
    """Decimal odds with zero expected value at win probability p."""
    if not 0 < p < 1:
        raise ValueError(f"probability must be in (0, 1), got {p}")
    return 1.0 / p


def bet_threshold(p: float, buffer: float) -> float:
    """Minimum decimal price worth taking: fair price plus a margin buffer (e.g. 0.05 = +5%)."""
    return fair_odds(p) * (1.0 + buffer)


def expected_value(p: float, price: float) -> float:
    """Expected profit per unit staked at decimal `price` with win probability p."""
    return p * price - 1.0


def edge_vs_price(p: float, price: float) -> float:
    """Model probability minus the probability implied by a decimal price."""
    return p - 1.0 / price

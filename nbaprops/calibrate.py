"""Walk-forward probability recalibration.

    q' = 0.5 + s * (q - 0.5) + c,  then capped to [1 - cap, cap]

`s` shrinks toward 50% (overconfidence), `c` shifts toward over (c > 0) or
under (c < 0). Both are fitted by maximum likelihood over a grid, using only
results fed in through `update`, i.e. only earlier dates when used
walk-forward. Until `min_obs` results have been seen, `apply` returns the
input unchanged (apart from the cap).
"""

from __future__ import annotations

import numpy as np

S_GRID = np.round(np.arange(0.30, 1.201, 0.01), 2)
C_GRID = np.round(np.arange(-0.06, 0.0601, 0.0025), 4)


class Recalibrator:
    def __init__(self, shrink: bool, offset: bool, cap: float | None = None, min_obs: int = 2000):
        self.s_grid = S_GRID if shrink else np.array([1.0])
        self.c_grid = C_GRID if offset else np.array([0.0])
        self.cap = cap
        self.min_obs = min_obs
        self.ll = np.zeros((len(self.s_grid), len(self.c_grid)))
        self.n = 0

    def params(self) -> tuple[float, float] | None:
        if self.n < self.min_obs:
            return None
        i, j = np.unravel_index(self.ll.argmax(), self.ll.shape)
        return float(self.s_grid[i]), float(self.c_grid[j])

    def apply(self, q):
        q = np.asarray(q, dtype=float)
        p = self.params()
        if p is not None:
            q = 0.5 + p[0] * (q - 0.5) + p[1]
        q = np.clip(q, 0.01, 0.99)
        if self.cap is not None:
            q = np.clip(q, 1 - self.cap, self.cap)
        return q

    def update(self, q_raw, over) -> None:
        """Add results: q_raw = raw P(over | no push), over = 1 if the over won (pushes excluded)."""
        q = np.asarray(q_raw, dtype=float)
        y = np.asarray(over, dtype=float)
        if not len(q):
            return
        p = 0.5 + self.s_grid[:, None, None] * (q - 0.5) + self.c_grid[None, :, None]
        p = np.clip(p, 1e-6, 1 - 1e-6)
        self.ll += (y * np.log(p) + (1 - y) * np.log(1 - p)).sum(axis=2)
        self.n += len(q)

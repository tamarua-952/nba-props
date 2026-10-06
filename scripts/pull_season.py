"""Pull and cache every backtest season in config.yaml (ESPN, BBRef gap fill).

    python scripts/pull_season.py

See nbaprops/pull.py.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nbaprops import config  # noqa: E402
from nbaprops.pull import pull  # noqa: E402

if __name__ == "__main__":
    for s in config.load()["backtest"]["seasons"]:
        pull(s["season"], dt.date.fromisoformat(str(s["start"])), dt.date.fromisoformat(str(s["end"])))

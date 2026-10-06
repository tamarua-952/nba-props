"""Fetch one sample of each ESPN response the pipeline parses, for parser tests.

Runs on GitHub Actions (ESPN is not reachable from every network) and writes
gzipped raw bodies to tests/fixtures/espn/.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nbaprops.http import Fetcher  # noqa: E402

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"


def main() -> None:
    f = Fetcher("espn", 0.5, cache_dir=ROOT / "tests" / "fixtures")
    sb = f.get_json(f"{SITE}/scoreboard", {"dates": "20260315"}, name="scoreboard_20260315")
    eid = sb["events"][0]["id"]
    f.get_json(f"{SITE}/summary", {"event": eid}, name=f"summary_{eid}")
    f.get_json(f"{SITE}/injuries", name="injuries")
    f.get_json(f"{SITE}/teams", name="teams")
    f.get_json(f"{SITE}/teams/7/roster", name="roster_7")
    # Date ranges would cut the season schedule pull to a few calls; check whether ESPN accepts them.
    for limit in (100, 300):
        try:
            f.get_json(f"{SITE}/scoreboard", {"dates": "20251021-20251031", "limit": limit},
                       name=f"scoreboard_range_{limit}")
        except Exception as e:  # noqa: BLE001
            print(f"date range limit={limit}: {e}")
    for p in sorted((ROOT / "tests" / "fixtures" / "espn").glob("*.gz")):
        print(p.name, p.stat().st_size)


if __name__ == "__main__":
    main()

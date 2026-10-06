"""Basketball-Reference box scores: gap filling only, under the rate limit.

Used only when ESPN has no usable box score for a completed game. Requests go
through the shared raw-response cache and are spaced so we stay well under
Basketball-Reference's 20 requests/minute limit.
"""

from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from . import config
from .http import Fetcher

BASE = "https://www.basketball-reference.com"
# ESPN abbreviation -> Basketball-Reference abbreviation, where they differ.
TEAM_CODES = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA",
              "WSH": "WAS", "BKN": "BRK", "CHA": "CHO", "PHX": "PHO"}
ET = ZoneInfo("America/New_York")


def fetcher(cache_dir=None) -> Fetcher:
    cfg = config.load()["sources"]["bbref"]
    return Fetcher("bbref", cfg["min_interval_s"], cache_dir=cache_dir)


def boxscore_url(start_utc: str, home_abbr: str) -> str:
    start = dt.datetime.fromisoformat(start_utc.replace("Z", "+00:00")).astimezone(ET)
    return f"{BASE}/boxscores/{start:%Y%m%d}0{TEAM_CODES.get(home_abbr, home_abbr)}.html"


_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL = re.compile(r'<(?:td|th)[^>]*data-stat="([^"]+)"[^>]*>(.*?)</(?:td|th)>', re.S)
_SLUG = re.compile(r'data-append-csv="([^"]+)"')
_TAG = re.compile(r"<[^>]+>")


def parse_boxscore(html: str, espn_abbr: str) -> list[dict]:
    """Player rows (name, slug, min, pts, reb, fga, fta, tov, dnp) for one team."""
    code = TEAM_CODES.get(espn_abbr, espn_abbr)
    m = re.search(rf'<table[^>]*id="box-{code}-game-basic".*?</table>', html, re.S)
    if not m:
        raise ValueError(f"no box score table for {code}")
    rows = []
    for tr in _ROW.findall(m.group(0)):
        cells = {k: _TAG.sub("", v).strip() for k, v in _CELL.findall(tr)}
        slug = _SLUG.search(tr)
        if not slug or "player" not in cells:
            continue
        dnp = "reason" in cells or not cells.get("mp")
        mp = cells.get("mp", "0:00") if not dnp else "0:00"
        mins, secs = (mp.split(":") + ["0"])[:2]

        def num(k):
            return int(cells.get(k) or 0) if not dnp else 0

        rows.append({
            "player": cells["player"], "slug": slug.group(1), "dnp": dnp,
            "min": int(mins) + int(secs) / 60, "pts": num("pts"), "reb": num("trb"),
            "fga": num("fga"), "fta": num("fta"), "tov": num("tov"),
        })
    return rows

"""The Odds API client with a monthly credit budget guard.

Used only as a sanity check (CONSENSUS_GAP) and a proxy closing line (CLV),
never as a model input. Calls are restricted to games that have picks.

Every call records the credit headers The Odds API returns
(x-requests-used / x-requests-remaining / x-requests-last) in a usage file,
so the real per-call cost is measured rather than assumed. Before a call the
guard estimates its cost from past calls and refuses if it would take the
remaining balance below the configured reserve.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import requests

from . import config

BASE = "https://api.the-odds-api.com/v4/sports/basketball_nba"


class BudgetExceeded(Exception):
    pass


class OddsAPI:
    def __init__(self, api_key: str | None = None, usage_file: str | Path | None = None):
        cfg = config.load()["odds_api"]
        self.cfg = cfg
        self.key = api_key or os.environ.get("ODDS_API_KEY")
        if not self.key:
            raise BudgetExceeded("ODDS_API_KEY not set")
        self.usage_file = Path(usage_file or config.ROOT / cfg["usage_file"])
        self.usage = self._load_usage()

    # ---------------------------------------------------------- usage ledger

    def _load_usage(self) -> dict:
        if self.usage_file.exists():
            return json.loads(self.usage_file.read_text())
        return {"calls": []}

    def _save_usage(self) -> None:
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
        self.usage_file.write_text(json.dumps(self.usage, indent=1))

    def remaining(self) -> int | None:
        """Last remaining-credit balance reported by the API this month."""
        month = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")
        calls = [c for c in self.usage["calls"] if c["at"].startswith(month) and c.get("remaining") is not None]
        return calls[-1]["remaining"] if calls else None

    def estimated_cost(self, kind: str) -> int:
        """Max observed cost of this kind of call; documented formula if never observed."""
        seen = [c["cost"] for c in self.usage["calls"] if c["kind"] == kind and c.get("cost") is not None]
        if seen:
            return max(seen)
        if kind == "event_odds":
            return len(self.cfg["markets"]) * len(self.cfg["regions"].split(","))
        return 1

    def check_budget(self, kind: str) -> None:
        rem = self.remaining()
        if rem is None:
            return  # first call of the month: the response headers will tell us
        cost = self.estimated_cost(kind)
        if rem - cost < self.cfg["reserve"]:
            raise BudgetExceeded(
                f"Odds API budget guard: {rem} credits left, call costs ~{cost}, reserve {self.cfg['reserve']}"
            )

    # ---------------------------------------------------------- calls

    def _get(self, kind: str, url: str, params: dict) -> object:
        self.check_budget(kind)
        r = requests.get(url, params={"apiKey": self.key, **params}, timeout=20)
        h = r.headers

        def num(name):
            v = h.get(name)
            return int(float(v)) if v not in (None, "") else None

        self.usage["calls"].append({
            "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "status": r.status_code,
            "cost": num("x-requests-last"),
            "used": num("x-requests-used"),
            "remaining": num("x-requests-remaining"),
            "params": {k: v for k, v in params.items()},
        })
        self._save_usage()
        r.raise_for_status()
        return r.json()

    def events(self) -> list[dict]:
        return self._get("events", f"{BASE}/events", {})

    def event_props(self, event_id: str) -> dict:
        return self._get("event_odds", f"{BASE}/events/{event_id}/odds", {
            "regions": self.cfg["regions"],
            "markets": ",".join(self.cfg["markets"]),
            "oddsFormat": "decimal",
        })

    def can_afford(self, kind: str, n_calls: int) -> bool:
        """Whether n_calls of this kind fit above the reserve (uses the quota if no call yet this month)."""
        rem = self.remaining()
        if rem is None:
            rem = self.cfg["monthly_quota"]
        return rem - n_calls * self.estimated_cost(kind) >= self.cfg["reserve"]


# ---------------------------------------------------------------- matching and consensus


def _nickname(team_name: str) -> str:
    """Last word of a team name ('Los Angeles Clippers' and 'LA Clippers' -> 'clippers')."""
    return team_name.strip().split()[-1].lower()


def match_event(events: list[dict], home_name: str, away_name: str, start_utc: str) -> dict | None:
    """Find the Odds API event for an ESPN game by team nicknames and start time (within 6 h)."""
    start = dt.datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
    for e in events:
        if _nickname(e["home_team"]) != _nickname(home_name) or _nickname(e["away_team"]) != _nickname(away_name):
            continue
        t = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
        if abs((t - start).total_seconds()) <= 6 * 3600:
            return e
    return None


def norm_name(name: str) -> str:
    import re
    import unicodedata

    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    return re.sub(r"[^a-z]", "", s)


MARKETS = {"player_points": "PTS", "player_rebounds": "REB"}


def consensus(event_odds: dict) -> dict:
    """{(norm player name, 'PTS'|'REB'): {line, over_price, under_price, books}} across bookmakers.

    The consensus line is the most common line (ties: the median); prices are
    averaged over books quoting that line.
    """
    quotes: dict = {}
    for b in event_odds.get("bookmakers", []):
        for m in b.get("markets", []):
            mk = MARKETS.get(m["key"])
            if not mk:
                continue
            for o in m.get("outcomes", []):
                if o.get("point") is None or not o.get("description"):
                    continue
                k = (norm_name(o["description"]), mk)
                quotes.setdefault(k, []).append((b["key"], float(o["point"]), o["name"].lower(), float(o["price"])))
    out = {}
    for k, qs in quotes.items():
        lines = [q[1] for q in qs]
        counts = {ln: lines.count(ln) for ln in set(lines)}
        top = max(counts.values())
        cands = sorted(ln for ln, c in counts.items() if c == top)
        line = cands[len(cands) // 2]
        over = [q[3] for q in qs if q[1] == line and q[2] == "over"]
        under = [q[3] for q in qs if q[1] == line and q[2] == "under"]
        out[k] = {"line": line, "over_price": sum(over) / len(over) if over else None,
                  "under_price": sum(under) / len(under) if under else None,
                  "books": len({q[0] for q in qs if q[1] == line})}
    return out

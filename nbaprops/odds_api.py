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

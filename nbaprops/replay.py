"""Chronological replay of cached box scores through the model.

Shared by the backtest and the daily brief: both replay history date by
date (projections for a date only see earlier dates), and the daily brief
then projects one more slate from the resulting state.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import dist
from .model import League, model_position

ET = ZoneInfo("America/New_York")
PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"


def load(seasons: list[int], processed: Path = PROCESSED):
    g, t, p = [], [], []
    for s in seasons:
        f = processed / f"games_{s}.csv.gz"
        if not f.exists():
            continue
        g.append(pd.read_csv(f, dtype={"game_id": str, "home_id": str, "away_id": str}))
        t.append(pd.read_csv(processed / f"team_games_{s}.csv.gz",
                             dtype={"game_id": str, "team_id": str, "opp_id": str}))
        p.append(pd.read_csv(processed / f"player_games_{s}.csv.gz",
                             dtype={"game_id": str, "team_id": str, "opp_id": str, "player_id": str}))
    games, teams, players = pd.concat(g), pd.concat(t), pd.concat(p)
    games["date"] = pd.to_datetime(games["start_utc"], utc=True).dt.tz_convert(ET).dt.date
    # Fill missing positions (BBRef gap-fill rows) with the player's usual ESPN position.
    has = players["pos"].notna() & (players["pos"] != "")
    usual = players[has].groupby("player_id")["pos"].agg(lambda s: s.mode().iat[0])
    players["pos"] = players["pos"].where(has, players["player_id"].map(usual))
    players["pos_model"] = players["pos"].fillna("F").map(model_position)
    return games.sort_values("start_utc"), teams, players


class Replayer:
    def __init__(self, games: pd.DataFrame, teams: pd.DataFrame, players: pd.DataFrame,
                 min_prior: int, min_minutes: float):
        self.games, self.players = games, players
        self.tg = {k: v for k, v in teams.groupby("game_id")}
        self.pg = {k: v for k, v in players.groupby("game_id")}
        self.min_prior, self.min_minutes = min_prior, min_minutes
        self.last10 = defaultdict(lambda: {"pts": deque(maxlen=10), "reb": deque(maxlen=10)})
        self.lg = League()
        self.season = None
        self.names = dict(zip(players["player_id"], players["player"]))

    def start_season(self, season: int) -> None:
        """Move the state to `season` (season boundary if it differs from the last replayed one)."""
        if self.season is not None and season != self.season:
            self.lg.new_season()
        self.season = season

    def project_game(self, date, game_id, home_id, away_id, home_spread, available: dict[str, set]) -> list[dict]:
        rows = []
        for tid, oid, home in ((home_id, away_id, True), (away_id, home_id, False)):
            spread = None if home_spread is None or home_spread != home_spread else (
                home_spread if home else -home_spread)
            for r in self.lg.project_team(tid, oid, home, available.get(tid, set()), date, spread, self.min_prior):
                r.update(game_id=game_id, date=date, season=self.season, team_id=tid, opp_id=oid,
                         home=home, spread=spread, player=self.names.get(r["player_id"], r["player_id"]))
                for s in ("pts", "reb"):
                    h = self.last10[r["player_id"]][s]
                    r[f"{s}_l10"] = sum(h) / len(h) if h else math.nan
                rows.append(r)
        return rows

    def run(self, until=None, on_date: Callable | None = None) -> None:
        """Replay every date before `until` (all dates if None).

        on_date(date, rows, acts) receives that date's projections (made before
        the date's games were folded in) and actual results keyed by
        (game_id, player_id).
        """
        games = self.games if until is None else self.games[self.games["date"] < until]
        for date, day in games.groupby("date", sort=True):
            self.start_season(day["season"].iat[0])
            rows = []
            for g in day.itertuples():
                prow = self.pg.get(g.game_id)
                if prow is None or g.game_id not in self.tg:
                    continue
                available = {tid: set(grp["player_id"]) for tid, grp in prow.groupby("team_id")}
                rows += self.project_game(date, g.game_id, g.home_id, g.away_id,
                                          None if pd.isna(g.home_spread) else g.home_spread, available)
            acts = {}
            for g in day.itertuples():
                if g.game_id in self.pg:
                    for a in self.pg[g.game_id].itertuples():
                        acts[(g.game_id, a.player_id)] = {"min": a.min, "pts": a.pts, "reb": a.reb}
            # Feed back results, then fold the whole date into the state (no same-day leakage).
            for r in rows:
                a = acts.get((r["game_id"], r["player_id"]))
                if a and a["min"] > 0 and r["proj_min"] >= self.min_minutes:
                    self.lg.record_result(r, a)
            if on_date:
                on_date(date, rows, acts)
            for g in day.itertuples():
                if g.game_id in self.pg and g.game_id in self.tg:
                    prow = self.pg[g.game_id]
                    self.lg.update_game(date, self.tg[g.game_id], prow)
                    for r in prow[prow["min"] > 0].itertuples():
                        self.last10[r.player_id]["pts"].append(r.pts)
                        self.last10[r.player_id]["reb"].append(r.reb)


def proxy_line(l10, version: str = "half"):
    """Proxy for a book line from a last-10 average: nearest x.5, or nearest 0.5."""
    l10 = np.asarray(l10, dtype=float)
    return np.floor(l10) + 0.5 if version == "half" else np.floor(l10 * 2 + 0.5) / 2


def raw_over_prob(lines, means, variances):
    """P(over | no push) from the model distribution."""
    over, under, _ = dist.line_probs_vec(lines, means, variances)
    return over / (over + under)

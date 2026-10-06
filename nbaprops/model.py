"""Walk-forward projection model for player points and rebounds.

State is updated one game date at a time, so a projection for a game only
ever sees games played on earlier dates. The same state machine serves the
backtest (replay a season) and the live run (replay history, then project
today's slate).

Projection = minutes x per-minute rate x adjustments, then a negative
binomial with a player-specific variance-to-mean ratio.

Minutes: recent-weighted minutes, plus a share of the minutes absent regulars
usually play, weighted toward players with room to play more. The share that
actually reaches projected players (the rest goes to call-ups and deep bench)
is learned walk-forward. Then back-to-back and blowout (spread) adjustments.

Rates: recent-weighted per-minute points/rebounds blended with season rate,
adjusted for usage freed by absent regulars (pass-through learned
walk-forward), opponent points/rebounds
allowed to the player's position (per 100 possessions, shrunk), expected
game pace, and home/away. No head-to-head features.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field

import pandas as pd

POSITIONS = ("G", "F", "C")

# Fixed priors for v1; revisit with the backtest's segment reports.
P = {
    "min_halflife": 6,        # games
    "rate_halflife": 12,      # games
    "pace_halflife": 10,
    "def_halflife": 15,
    "season_rate_weight": 0.25,
    "max_minutes": 42.0,
    "b2b_minutes_factor": 0.97,       # applied to players projected >= 28 min
    "blowout_per_point": 0.005,       # starters' minutes cut per spread point beyond 6
    # Pass-through priors, replaced walk-forward once enough results exist.
    "minutes_pass_through": 0.5,      # share of freed minutes that reaches projected players
    "usage_pass_through_pts": 0.5,    # share of freed usage that lifts a player's scoring rate
    "usage_pass_through_reb": 0.3,
    "pass_through_min_obs": 300,
    "def_shrink_games": 15,
    "phi_shrink_games": 10,
    "home_pts": 1.01,
    "regular_min": 15.0,              # a "regular": ew minutes >= this ...
    "regular_recent": 3,              # ... and played in >= this many of the team's last 5 games
}


class EW:
    """Exponentially weighted mean with bias correction (weights decay per update)."""

    __slots__ = ("a", "s", "w")

    def __init__(self, halflife: float):
        self.a = 1 - 0.5 ** (1 / halflife)
        self.s = 0.0
        self.w = 0.0

    def update(self, x: float) -> None:
        self.s = self.s * (1 - self.a) + x
        self.w = self.w * (1 - self.a) + 1

    @property
    def value(self) -> float:
        return self.s / self.w if self.w else math.nan


@dataclass
class PlayerState:
    pos: str = "F"
    n: int = 0
    ew_min: EW = field(default_factory=lambda: EW(P["min_halflife"]))
    ew_pts: EW = field(default_factory=lambda: EW(P["rate_halflife"]))
    ew_reb: EW = field(default_factory=lambda: EW(P["rate_halflife"]))
    ew_mins_r: EW = field(default_factory=lambda: EW(P["rate_halflife"]))
    ew_usage: EW = field(default_factory=lambda: EW(P["rate_halflife"]))
    sum_min: float = 0.0
    sum_pts: float = 0.0
    sum_reb: float = 0.0
    sum_pts2: float = 0.0
    sum_reb2: float = 0.0

    def rate(self, stat: str) -> float:
        ew = (self.ew_pts if stat == "pts" else self.ew_reb).value / max(self.ew_mins_r.value, 1e-9)
        season = (self.sum_pts if stat == "pts" else self.sum_reb) / max(self.sum_min, 1e-9)
        w = P["season_rate_weight"]
        return (1 - w) * ew + w * season

    def phi_raw(self, stat: str) -> float:
        s, s2 = (self.sum_pts, self.sum_pts2) if stat == "pts" else (self.sum_reb, self.sum_reb2)
        mean = s / self.n
        var = s2 / self.n - mean * mean
        return var * self.n / (self.n - 1) / max(mean, 0.5)


@dataclass
class TeamState:
    ew_poss: EW = field(default_factory=lambda: EW(P["pace_halflife"]))
    ew_usage: EW = field(default_factory=lambda: EW(P["pace_halflife"]))
    ew_reb: EW = field(default_factory=lambda: EW(P["pace_halflife"]))
    recent: deque = field(default_factory=lambda: deque(maxlen=10))  # sets of player ids who played
    last_date: object = None
    # Defence: per-100-possession points/rebounds allowed to each position.
    def_pts: dict = field(default_factory=lambda: {p: EW(P["def_halflife"]) for p in POSITIONS})
    def_reb: dict = field(default_factory=lambda: {p: EW(P["def_halflife"]) for p in POSITIONS})
    def_n: int = 0


class League:
    def __init__(self):
        self.players: dict[str, PlayerState] = defaultdict(PlayerState)
        self.teams: dict[str, TeamState] = defaultdict(TeamState)
        self.lg_pts = {p: [0.0, 0] for p in POSITIONS}  # per-100 sums, counts
        self.lg_reb = {p: [0.0, 0] for p in POSITIONS}
        self.lg_poss = [0.0, 0]
        # Walk-forward variance calibration: running mean of squared standardised
        # errors of past projections, per stat. Multiplies the model variance.
        self.z2 = {"pts": [0.0, 0], "reb": [0.0, 0]}
        # Walk-forward pass-through: least-squares slope through the origin of the
        # realised change on the attempted adjustment, from past projections.
        self.pt = {k: [0.0, 0.0, 0] for k in ("min", "pts", "reb")}

    def var_inflation(self, stat: str) -> float:
        s, n = self.z2[stat]
        return max(s / n, 1.0) if n >= 500 else 1.0

    def pass_through(self, key: str) -> float:
        num, den, n = self.pt[key]
        prior = {"min": P["minutes_pass_through"], "pts": P["usage_pass_through_pts"],
                 "reb": P["usage_pass_through_reb"]}[key]
        if n < P["pass_through_min_obs"] or den <= 0:
            return prior
        return min(max(num / den, 0.0), 1.0)

    def record_result(self, row: dict, actual: dict) -> None:
        """Feed back a completed projection. `actual` has min, pts, reb."""
        for stat in ("pts", "reb"):
            self.z2[stat][0] += (actual[stat] - row[f"{stat}_mean"]) ** 2 / row[f"{stat}_var_model"]
            self.z2[stat][1] += 1
        # Minutes: realised gain over base vs the full freed-minutes allocation.
        if row["alloc_min"] > 0:
            self.pt["min"][0] += (actual["min"] - row["base_min"]) * row["alloc_min"]
            self.pt["min"][1] += row["alloc_min"] ** 2
            self.pt["min"][2] += 1
        # Rates: realised per-minute rate relative to the unadjusted rate vs freed share.
        for stat in ("pts", "reb"):
            share = row[f"{stat}_share"]
            if share > 0 and actual["min"] >= 10:
                ratio = actual[stat] / actual["min"] / max(row[f"{stat}_base_rate"], 1e-6) - 1
                self.pt[stat][0] += ratio * share
                self.pt[stat][1] += share ** 2
                self.pt[stat][2] += 1

    # ------------------------------------------------------------ helpers

    def league_phi(self, stat: str) -> float:
        vals = [s.phi_raw(stat) for s in self.players.values() if s.n >= 10]
        return sum(vals) / len(vals) if vals else (1.8 if stat == "pts" else 1.4)

    def regulars(self, team_id: str) -> set[str]:
        t = self.teams[team_id]
        last5 = list(t.recent)[-5:]
        counts = defaultdict(int)
        for s in last5:
            for pid in s:
                counts[pid] += 1
        return {pid for pid, c in counts.items()
                if c >= min(P["regular_recent"], len(last5)) and self.players[pid].ew_min.value >= P["regular_min"]}

    def recent_players(self, team_id: str) -> set[str]:
        out = set()
        for s in self.teams[team_id].recent:
            out |= s
        return out

    # ------------------------------------------------------------ projection

    def project_team(self, team_id: str, opp_id: str, home: bool, available: set[str], date,
                     team_spread: float | None, min_prior_games: int) -> list[dict]:
        """Project every available player on one team for one game.

        `available`: players not ruled out (live: roster minus OUT; backtest:
        players listed in the box score, which omits inactive/injured players).
        """
        t, o = self.teams[team_id], self.teams[opp_id]
        pool = [pid for pid in (self.recent_players(team_id) & available) if self.players[pid].n > 0]
        if not pool:
            return []
        out_regulars = self.regulars(team_id) - available

        # Minutes: recent-weighted minutes, plus the minutes absent regulars usually play,
        # handed out by room to grow (so starters near the cap gain little). Players who
        # merely appear on the roster are not scaled down: most DNP-coach's-decision
        # players would otherwise drag every starter's projection below reality.
        base = {pid: min(self.players[pid].ew_min.value, P["max_minutes"]) for pid in pool}
        freed = sum(min(self.players[p].ew_min.value, P["max_minutes"]) for p in out_regulars)
        room = {pid: max(P["max_minutes"] - m, 0.0) * m for pid, m in base.items()}
        rsum = sum(room.values()) or 1.0
        alloc = {pid: freed * room[pid] / rsum for pid in pool}
        k_min = self.pass_through("min")
        mins = {pid: min(base[pid] + k_min * alloc[pid], P["max_minutes"]) for pid in pool}

        b2b = t.last_date is not None and (date - t.last_date).days == 1
        spread_abs = abs(team_spread) if team_spread is not None else 0.0

        # Usage / rebounds freed by absent regulars, as a share of the team's.
        team_usage = t.ew_usage.value if t.ew_usage.w else math.nan
        team_reb = t.ew_reb.value if t.ew_reb.w else math.nan
        missing_usage = sum(self.players[p].ew_usage.value for p in out_regulars)
        missing_reb = sum(self.players[p].ew_reb.value / max(self.players[p].ew_mins_r.value, 1e-9)
                          * self.players[p].ew_min.value for p in out_regulars)
        usage_share = missing_usage / team_usage if team_usage and team_usage == team_usage else 0.0
        reb_share = missing_reb / team_reb if team_reb and team_reb == team_reb else 0.0

        lg_poss = self.lg_poss[0] / self.lg_poss[1] if self.lg_poss[1] else 100.0
        team_pace = t.ew_poss.value if t.ew_poss.w else lg_poss
        opp_pace = o.ew_poss.value if o.ew_poss.w else lg_poss
        pace_factor = (team_pace * opp_pace / lg_poss) / team_pace

        phi_lg = {s: self.league_phi(s) for s in ("pts", "reb")}
        rows = []
        for pid in pool:
            ps = self.players[pid]
            if ps.n < min_prior_games:
                continue
            m = mins[pid]
            if b2b and m >= 28:
                m *= P["b2b_minutes_factor"]
            if spread_abs > 6 and m >= 28:
                m *= 1 - P["blowout_per_point"] * (spread_abs - 6)

            row = {"player_id": pid, "pos": ps.pos, "proj_min": m, "b2b": b2b,
                   "base_min": base[pid], "alloc_min": alloc[pid],
                   "out_regulars": len(out_regulars), "usage_share_freed": usage_share}
            for stat, defd, lg, pass_through, share in (
                ("pts", o.def_pts, self.lg_pts, self.pass_through("pts"), usage_share),
                ("reb", o.def_reb, self.lg_reb, self.pass_through("reb"), reb_share),
            ):
                rate = ps.rate(stat)
                lg_sum, lg_n = lg[ps.pos]
                opp_factor = 1.0
                if lg_n and defd[ps.pos].w:
                    raw = defd[ps.pos].value / (lg_sum / lg_n)
                    k = o.def_n / (o.def_n + P["def_shrink_games"])
                    opp_factor = 1 + (raw - 1) * k
                share = min(share, 0.5)
                usage_factor = 1 + pass_through * share
                ha = (P["home_pts"] if home else 1 / P["home_pts"]) if stat == "pts" else 1.0
                mean = max(m * rate * opp_factor * pace_factor * usage_factor * ha, 0.3)
                phi_p = ps.phi_raw(stat) if ps.n >= 3 else phi_lg[stat]
                w = ps.n / (ps.n + P["phi_shrink_games"])
                phi = max(w * phi_p + (1 - w) * phi_lg[stat], 1.0)
                row[f"{stat}_mean"] = mean
                row[f"{stat}_share"] = share
                row[f"{stat}_base_rate"] = rate * opp_factor * pace_factor * ha
                row[f"{stat}_var_model"] = mean * phi
                row[f"{stat}_var"] = mean * phi * self.var_inflation(stat)
                row[f"{stat}_opp_factor"] = opp_factor
            row["pace_factor"] = pace_factor
            rows.append(row)
        return rows

    # ------------------------------------------------------------ updates

    def update_game(self, date, team_rows: pd.DataFrame, player_rows: pd.DataFrame) -> None:
        """Fold one completed game into the state."""
        played = player_rows[player_rows["min"] > 0]
        by_team = {tid: g for tid, g in played.groupby("team_id")}
        tr = {r.team_id: r for r in team_rows.itertuples()}
        for tid, r in tr.items():
            t = self.teams[tid]
            opp = tr.get(r.opp_id)
            poss = (r.poss + opp.poss) / 2 if opp is not None else r.poss
            t.ew_poss.update(poss)
            t.ew_usage.update(r.fga + 0.44 * r.fta + r.tov)
            t.ew_reb.update(r.reb)
            t.recent.append(set(by_team.get(tid, played.iloc[0:0])["player_id"]))
            t.last_date = date
            self.lg_poss[0] += poss
            self.lg_poss[1] += 1

            # Defence of the opponent: what this team's players scored against them.
            if opp is None:
                continue
            d = self.teams[r.opp_id]
            g = by_team.get(tid)
            if g is None:
                continue
            for pos in POSITIONS:
                sub = g[g["pos_model"] == pos]
                pts100 = sub["pts"].sum() / poss * 100
                reb100 = sub["reb"].sum() / poss * 100
                d.def_pts[pos].update(pts100)
                d.def_reb[pos].update(reb100)
                self.lg_pts[pos][0] += pts100
                self.lg_pts[pos][1] += 1
                self.lg_reb[pos][0] += reb100
                self.lg_reb[pos][1] += 1
            d.def_n += 1

        for r in played.itertuples():
            ps = self.players[r.player_id]
            ps.pos = r.pos_model
            ps.n += 1
            ps.ew_min.update(r.min)
            ps.ew_pts.update(r.pts)
            ps.ew_reb.update(r.reb)
            ps.ew_mins_r.update(r.min)
            ps.ew_usage.update(r.fga + 0.44 * r.fta + r.tov)
            ps.sum_min += r.min
            ps.sum_pts += r.pts
            ps.sum_reb += r.reb
            ps.sum_pts2 += r.pts ** 2
            ps.sum_reb2 += r.reb ** 2


def model_position(pos: str) -> str:
    pos = (pos or "").upper()
    if pos.startswith("C"):
        return "C"
    if pos.endswith("G") or pos == "G":
        return "G"
    return "F"

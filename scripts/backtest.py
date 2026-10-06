"""Walk-forward calibration backtest on a cached season.

    python scripts/backtest.py

Measures calibration only, not edge: there are no free historical prop
lines. Probabilities are checked at
  * a proxy line = the player's last-10-game average, floored to x.5
    (a crude stand-in for where a book might set the line), and
  * a grid of half-point lines around each projection.

Writes output/backtest/calibration_<season>.{md,json} and
data/processed/backtest_projections_<season>.csv.gz.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nbaprops import config, dist  # noqa: E402
from nbaprops.model import League, model_position  # noqa: E402

ET = ZoneInfo("America/New_York")
GRID = {"pts": [-4, -2, 0, 2, 4], "reb": [-2, -1, 0, 1, 2]}
BINS = [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0001]
PICK_BINS = [.5, .55, .6, .65, .7, .75, 1.0001]


def load(season: int):
    d = ROOT / "data" / "processed"
    games = pd.read_csv(d / f"games_{season}.csv.gz", dtype={"game_id": str, "home_id": str, "away_id": str})
    teams = pd.read_csv(d / f"team_games_{season}.csv.gz", dtype={"game_id": str, "team_id": str, "opp_id": str})
    players = pd.read_csv(d / f"player_games_{season}.csv.gz",
                          dtype={"game_id": str, "team_id": str, "opp_id": str, "player_id": str})
    games["date"] = pd.to_datetime(games["start_utc"], utc=True).dt.tz_convert(ET).dt.date
    # Fill missing positions (BBRef gap-fill rows) with the player's usual ESPN position.
    usual = players[players["pos"].notna() & (players["pos"] != "")].groupby("player_id")["pos"].agg(
        lambda s: s.mode().iat[0])
    players["pos"] = players["pos"].where(players["pos"].notna() & (players["pos"] != ""),
                                          players["player_id"].map(usual))
    players["pos_model"] = players["pos"].fillna("F").map(model_position)
    return games.sort_values("start_utc"), teams, players


def run(season: int, min_prior: int, min_minutes: float) -> pd.DataFrame:
    games, teams, players = load(season)
    tg = {k: v for k, v in teams.groupby("game_id")}
    pg = {k: v for k, v in players.groupby("game_id")}
    last10 = defaultdict(lambda: {"pts": deque(maxlen=10), "reb": deque(maxlen=10)})
    lg = League()
    out = []
    for date, day in games.groupby("date", sort=True):
        day_rows = []
        for g in day.itertuples():
            prow = pg.get(g.game_id)
            if prow is None or g.game_id not in tg:
                continue
            for tid, oid, home in ((g.home_id, g.away_id, True), (g.away_id, g.home_id, False)):
                listed = set(prow.loc[prow.team_id == tid, "player_id"])
                spread = None if pd.isna(g.home_spread) else (g.home_spread if home else -g.home_spread)
                for r in lg.project_team(tid, oid, home, listed, date, spread, min_prior):
                    r.update(game_id=g.game_id, date=date, team_id=tid, opp_id=oid, home=home, spread=spread)
                    for s in ("pts", "reb"):
                        h = last10[r["player_id"]][s]
                        r[f"{s}_l10"] = sum(h) / len(h) if h else math.nan
                    day_rows.append(r)
        # Results, then fold the whole date into the state (no same-day leakage).
        for r in day_rows:
            act = pg[r["game_id"]].set_index("player_id")
            if r["player_id"] in act.index and act.at[r["player_id"], "min"] > 0 and r["proj_min"] >= min_minutes:
                for s in ("pts", "reb"):
                    lg.record_result(s, r[f"{s}_mean"], r[f"{s}_var_model"], act.at[r["player_id"], s])
        for g in day.itertuples():
            if g.game_id in pg and g.game_id in tg:
                prow = pg[g.game_id]
                lg.update_game(date, tg[g.game_id], prow)
                for r in prow[prow["min"] > 0].itertuples():
                    last10[r.player_id]["pts"].append(r.pts)
                    last10[r.player_id]["reb"].append(r.reb)
        out += day_rows

    proj = pd.DataFrame(out)
    actual = players[["game_id", "player_id", "player", "min", "pts", "reb"]].rename(
        columns={"min": "act_min", "pts": "act_pts", "reb": "act_reb"})
    proj = proj.merge(actual, on=["game_id", "player_id"], how="left")
    # Props are voided if the player does not play, and are only offered on rotation players.
    return proj[(proj["act_min"] > 0) & (proj["proj_min"] >= min_minutes)].reset_index(drop=True)


def add_line_probs(proj: pd.DataFrame) -> pd.DataFrame:
    """Long table: one row per (player-game, market, line)."""
    rows = []
    for r in proj.itertuples():
        for s in ("pts", "reb"):
            mean, var, act = getattr(r, f"{s}_mean"), getattr(r, f"{s}_var"), getattr(r, f"act_{s}")
            l10 = getattr(r, f"{s}_l10")
            lines = {("grid", k): math.floor(mean) + 0.5 + k for k in GRID[s]}
            if not math.isnan(l10):
                lines[("proxy", 0)] = math.floor(l10) + 0.5
            for (kind, off), line in lines.items():
                if line <= 0:
                    continue
                p = dist.line_probs(line, mean, var)
                rows.append({"game_id": r.game_id, "date": r.date, "player": r.player, "market": s.upper(),
                             "kind": kind, "offset": off, "line": line, "mean": mean, "var": var,
                             "actual": act, "p_over": p.over, "over": int(act > line),
                             "out_regulars": r.out_regulars, "b2b": r.b2b, "l10": l10})
    return pd.DataFrame(rows)


def reliability(df: pd.DataFrame, pcol: str, ycol: str, bins) -> list[dict]:
    cut = pd.cut(df[pcol], bins, right=False)
    out = []
    for b, g in df.groupby(cut, observed=True):
        n = len(g)
        hit = g[ycol].mean()
        se = math.sqrt(max(hit * (1 - hit), 1e-9) / n)
        out.append({"bucket": f"{b.left:.0%}–{min(b.right, 1):.0%}", "n": n, "pred": g[pcol].mean(),
                    "hit": hit, "ci95": 1.96 * se, "gap": hit - g[pcol].mean()})
    return out


def brier(p, y):
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def logloss(p, y):
    p = np.clip(np.asarray(p), 1e-6, 1 - 1e-6)
    y = np.asarray(y)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def summarise(proj: pd.DataFrame, long: pd.DataFrame) -> dict:
    res = {"player_games": len(proj), "dates": [str(proj["date"].min()), str(proj["date"].max())]}
    for s in ("pts", "reb"):
        m = s.upper()
        sub = proj.dropna(subset=[f"{s}_l10"])
        res[f"{m}_projection"] = {
            "mae_model": float((sub[f"{s}_mean"] - sub[f"act_{s}"]).abs().mean()),
            "mae_last10_avg": float((sub[f"{s}_l10"] - sub[f"act_{s}"]).abs().mean()),
            "bias_model": float((sub[f"{s}_mean"] - sub[f"act_{s}"]).mean()),
            "minutes_mae": float((sub["proj_min"] - sub["act_min"]).abs().mean()),
        }
        px = long[(long.market == m) & (long.kind == "proxy")].copy()
        grid = long[(long.market == m) & (long.kind == "grid")]
        px["p_side"] = np.maximum(px.p_over, 1 - px.p_over)
        px["side_hit"] = np.where(px.p_over >= 0.5, px.over, 1 - px.over)
        # Naive baseline: same NB family, mean = last-10 average, league variance ratio.
        phi = float((grid["var"] / grid["mean"]).median())
        base = [dist.line_probs(r.line, max(r.l10, .3), max(r.l10, .3) * phi).over for r in px.itertuples()]
        res[m] = {
            "proxy_reliability": reliability(px, "p_over", "over", BINS),
            "proxy_pick_side": reliability(px, "p_side", "side_hit", PICK_BINS),
            "grid_reliability": reliability(grid, "p_over", "over", BINS),
            "proxy_scores": {"n": len(px), "brier_model": brier(px.p_over, px.over),
                             "brier_naive_l10": brier(base, px.over), "brier_coin": 0.25,
                             "logloss_model": logloss(px.p_over, px.over),
                             "logloss_naive_l10": logloss(base, px.over)},
            "segments": {},
        }
        for name, mask in (("teammate_regular_out", px.out_regulars > 0),
                           ("no_regular_out", px.out_regulars == 0),
                           ("back_to_back", px.b2b.astype(bool))):
            g = px[mask]
            if len(g):
                res[m]["segments"][name] = {"n": len(g), "pred_over": float(g.p_over.mean()),
                                            "hit_over": float(g.over.mean()),
                                            "mean_minus_actual": float((g["mean"] - g.actual).mean())}
        px["month"] = pd.to_datetime(px["date"]).dt.strftime("%Y-%m")
        res[m]["by_month"] = {k: {"n": len(g), "pred_over": float(g.p_over.mean()), "hit_over": float(g.over.mean())}
                             for k, g in px.groupby("month")}
    return res


def to_md(res: dict, season: int) -> str:
    L = [f"# Backtest calibration — {season - 1}–{str(season)[2:]} regular season", "",
         "**Calibration only, not edge.** No historical prop lines are available, so this checks whether "
         "the model's probabilities are honest, not whether they beat a bookmaker.", "",
         f"Player-games projected: {res['player_games']} ({res['dates'][0]} to {res['dates'][1]}). "
         "Walk-forward: each projection uses only games on earlier dates.", "",
         "Proxy line = player's last-10 average floored to x.5. Real book lines are sharper than this, "
         "so results at the proxy line say nothing about edge.", ""]
    for m in ("PTS", "REB"):
        r, pj = res[m], res[f"{m}_projection"]
        sc = r["proxy_scores"]
        L += [f"## {m}", "",
              f"Projection MAE {pj['mae_model']:.2f} (last-10 average: {pj['mae_last10_avg']:.2f}); "
              f"bias {pj['bias_model']:+.2f}; minutes MAE {pj['minutes_mae']:.1f}.", "",
              f"At the proxy line (n={sc['n']}): Brier {sc['brier_model']:.4f} vs naive last-10 "
              f"{sc['brier_naive_l10']:.4f} vs coin 0.25; log loss {sc['logloss_model']:.4f} vs "
              f"{sc['logloss_naive_l10']:.4f}.", "",
              "### Pick-side calibration at the proxy line", "",
              "Model's probability for the side it favours vs how often that side won. "
              "This is the table that matters for picks (spec needs > ~53.5% at $1.87).", "",
              "| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred |", "|---|---|---|---|---|---|"]
        for b in r["proxy_pick_side"]:
            L.append(f"| {b['bucket']} | {b['n']} | {b['pred']:.1%} | {b['hit']:.1%} | {b['ci95']:.1%} | {b['gap']:+.1%} |")
        L += ["", "### P(over) reliability, all grid lines", "",
              "| P(over) | n | Mean pred | Hit rate | ±95% | Hit − pred |", "|---|---|---|---|---|---|"]
        for b in r["grid_reliability"]:
            L.append(f"| {b['bucket']} | {b['n']} | {b['pred']:.1%} | {b['hit']:.1%} | {b['ci95']:.1%} | {b['gap']:+.1%} |")
        L += ["", "### Segments (proxy line)", "", "| Segment | n | Pred over | Hit over | Mean − actual |",
              "|---|---|---|---|---|"]
        for k, v in r["segments"].items():
            L.append(f"| {k} | {v['n']} | {v['pred_over']:.1%} | {v['hit_over']:.1%} | {v['mean_minus_actual']:+.2f} |")
        L += ["", "| Month | n | Pred over | Hit over |", "|---|---|---|---|"]
        for k, v in r["by_month"].items():
            L.append(f"| {k} | {v['n']} | {v['pred_over']:.1%} | {v['hit_over']:.1%} |")
        L.append("")
    return "\n".join(L)


def main() -> None:
    cfg = config.load()["backtest"]
    season = cfg["season"]
    proj = run(season, cfg["min_prior_games"], cfg["min_proj_minutes"])
    long = add_line_probs(proj)
    res = summarise(proj, long)
    out = ROOT / "output" / "backtest"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"calibration_{season}.json").write_text(json.dumps(res, indent=1, default=str))
    (out / f"calibration_{season}.md").write_text(to_md(res, season))
    proj.to_csv(ROOT / "data" / "processed" / f"backtest_projections_{season}.csv.gz", index=False)
    print(to_md(res, season))


if __name__ == "__main__":
    main()

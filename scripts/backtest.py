"""Walk-forward calibration backtest.

    python scripts/backtest.py

Measures calibration only, not edge: there are no free historical prop
lines. The model is replayed over every season in config.yaml (earlier
seasons are history: they count toward the min-games rule and warm up the
learned corrections); calibration is reported on `evaluate_season` only.

Probabilities are checked at a proxy line built from the player's last-10
average, in two versions:
  * half:  floor(avg) + 0.5, the nearest x.5 line (no pushes);
  * round: avg rounded to the nearest 0.5, so whole-number lines (pushes) occur.
Real book lines are sharper than either, so none of this measures edge.

Points probabilities are recalibrated by walk-forward shrinkage toward 50%:
on each date, the shrink factor is fitted (max likelihood) only on proxy-line
results from earlier dates, then applied to that date. Rebounds are left raw.

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
PICK_BINS = [.5, .55, .6, .65, .7, .75, 1.0001]
GATE_BUCKETS = ("60%–65%", "65%–70%", "70%–75%")
GATE_PP = 0.02
SHRINK_GRID = np.round(np.arange(0.30, 1.201, 0.01), 2)
SHRINK_MIN_OBS = 2000
EARLY_DAYS = 21
VERSIONS = {
    "half": ("nearest x.5 (floor + 0.5)", lambda a: np.floor(a) + 0.5),
    "round": ("nearest 0.5 (whole lines push)", lambda a: np.floor(a * 2 + 0.5) / 2),
}


def load(seasons: list[int]):
    d = ROOT / "data" / "processed"
    g, t, p = [], [], []
    for s in seasons:
        g.append(pd.read_csv(d / f"games_{s}.csv.gz", dtype={"game_id": str, "home_id": str, "away_id": str}))
        t.append(pd.read_csv(d / f"team_games_{s}.csv.gz", dtype={"game_id": str, "team_id": str, "opp_id": str}))
        p.append(pd.read_csv(d / f"player_games_{s}.csv.gz",
                             dtype={"game_id": str, "team_id": str, "opp_id": str, "player_id": str}))
    games, teams, players = pd.concat(g), pd.concat(t), pd.concat(p)
    games["date"] = pd.to_datetime(games["start_utc"], utc=True).dt.tz_convert(ET).dt.date
    # Fill missing positions (BBRef gap-fill rows) with the player's usual ESPN position.
    has = players["pos"].notna() & (players["pos"] != "")
    usual = players[has].groupby("player_id")["pos"].agg(lambda s: s.mode().iat[0])
    players["pos"] = players["pos"].where(has, players["player_id"].map(usual))
    players["pos_model"] = players["pos"].fillna("F").map(model_position)
    return games.sort_values("start_utc"), teams, players


def run(seasons: list[int], min_prior: int, min_minutes: float) -> pd.DataFrame:
    games, teams, players = load(seasons)
    tg = {k: v for k, v in teams.groupby("game_id")}
    pg = {k: v for k, v in players.groupby("game_id")}
    last10 = defaultdict(lambda: {"pts": deque(maxlen=10), "reb": deque(maxlen=10)})
    lg = League()
    out = []
    season = None
    for date, day in games.groupby("date", sort=True):
        if season is not None and day["season"].iat[0] != season:
            lg.new_season()
        season = day["season"].iat[0]
        day_rows = []
        for g in day.itertuples():
            prow = pg.get(g.game_id)
            if prow is None or g.game_id not in tg:
                continue
            for tid, oid, home in ((g.home_id, g.away_id, True), (g.away_id, g.home_id, False)):
                listed = set(prow.loc[prow.team_id == tid, "player_id"])
                spread = None if pd.isna(g.home_spread) else (g.home_spread if home else -g.home_spread)
                for r in lg.project_team(tid, oid, home, listed, date, spread, min_prior):
                    r.update(game_id=g.game_id, date=date, season=season, team_id=tid, opp_id=oid,
                             home=home, spread=spread)
                    for s in ("pts", "reb"):
                        h = last10[r["player_id"]][s]
                        r[f"{s}_l10"] = sum(h) / len(h) if h else math.nan
                    day_rows.append(r)
        # Results, then fold the whole date into the state (no same-day leakage).
        acts = {}
        for g in day.itertuples():
            if g.game_id in pg:
                for a in pg[g.game_id].itertuples():
                    acts[(g.game_id, a.player_id)] = {"min": a.min, "pts": a.pts, "reb": a.reb}
        for r in day_rows:
            a = acts.get((r["game_id"], r["player_id"]))
            if a and a["min"] > 0 and r["proj_min"] >= min_minutes:
                lg.record_result(r, a)
        for g in day.itertuples():
            if g.game_id in pg and g.game_id in tg:
                prow = pg[g.game_id]
                lg.update_game(date, tg[g.game_id], prow)
                for r in prow[prow["min"] > 0].itertuples():
                    last10[r.player_id]["pts"].append(r.pts)
                    last10[r.player_id]["reb"].append(r.reb)
        out += day_rows

    proj = pd.DataFrame(out)
    print("learned pass-through (end):", {k: round(float(lg.pass_through(k)), 3) for k in ("min", "pts", "reb")},
          "variance inflation:", {k: round(float(lg.var_inflation(k)), 3) for k in ("pts", "reb")}, flush=True)
    actual = players[["game_id", "player_id", "player", "min", "pts", "reb"]].rename(
        columns={"min": "act_min", "pts": "act_pts", "reb": "act_reb"})
    proj = proj.merge(actual, on=["game_id", "player_id"], how="left")
    proj["flags"] = proj["flags"].fillna("")
    # Props are voided if the player does not play, and are only offered on rotation players.
    return proj[(proj["act_min"] > 0) & (proj["proj_min"] >= min_minutes)].reset_index(drop=True)


# ---------------------------------------------------------------- proxy-line evaluation


def proxy_table(proj: pd.DataFrame, stat: str, version: str) -> pd.DataFrame:
    """One row per projection at the proxy line, with raw and walk-forward-shrunk probabilities."""
    df = proj.dropna(subset=[f"{stat}_l10"]).copy()
    df["line"] = VERSIONS[version][1](df[f"{stat}_l10"].to_numpy())
    df = df[df["line"] > 0]
    over, under, push = dist.line_probs_vec(df["line"], df[f"{stat}_mean"], df[f"{stat}_var"])
    df["q_raw"] = over / (over + under)  # P(over | no push)
    act = df[f"act_{stat}"]
    df["push"] = act == df["line"]
    df["over"] = (act > df["line"]).astype(int)
    df = df.sort_values("date").reset_index(drop=True)

    # Walk-forward shrinkage: per date, use the factor that best fit earlier dates only.
    ll = np.zeros(len(SHRINK_GRID))
    n_seen = 0
    s_for_row = np.ones(len(df))
    for date, idx in df.groupby("date").groups.items():
        s_now = float(SHRINK_GRID[ll.argmax()]) if n_seen >= SHRINK_MIN_OBS else math.nan
        s_for_row[idx] = s_now
        d = df.loc[idx]
        d = d[~d["push"]]
        q = np.clip(0.5 + np.outer(SHRINK_GRID, d["q_raw"].to_numpy() - 0.5), 1e-6, 1 - 1e-6)
        y = d["over"].to_numpy()
        ll += (y * np.log(q) + (1 - y) * np.log(1 - q)).sum(axis=1)
        n_seen += len(d)
    df["shrink"] = s_for_row
    df["q_cal"] = dist.shrink(df["q_raw"], df["shrink"].fillna(1.0))
    return df


def pick_side(df: pd.DataFrame, qcol: str) -> pd.DataFrame:
    d = df[~df["push"]].copy()
    d["side"] = np.where(d[qcol] >= 0.5, "over", "under")
    d["p_side"] = np.maximum(d[qcol], 1 - d[qcol])
    d["hit"] = np.where(d["side"] == "over", d["over"], 1 - d["over"])
    return d


def buckets(d: pd.DataFrame) -> list[dict]:
    out = []
    for b, g in d.groupby(pd.cut(d["p_side"], PICK_BINS, right=False), observed=True):
        n, hit, pred = len(g), g["hit"].mean(), g["p_side"].mean()
        out.append({"bucket": f"{b.left:.0%}–{min(b.right, 1):.0%}", "n": n, "pred": pred, "hit": hit,
                    "ci95": 1.96 * math.sqrt(max(hit * (1 - hit), 1e-9) / n), "gap": hit - pred,
                    "over_share": float((g["side"] == "over").mean())})
    return out


def side_split(d: pd.DataFrame) -> dict:
    out = {}
    for label, sub in (("all", d), ("p>=55%", d[d.p_side >= .55]), ("p>=60%", d[d.p_side >= .60])):
        row = {"n": len(sub)}
        for side in ("over", "under"):
            g = sub[sub.side == side]
            row[side] = {"n": len(g), "share": len(g) / len(sub) if len(sub) else math.nan,
                         "pred": float(g.p_side.mean()) if len(g) else math.nan,
                         "hit": float(g.hit.mean()) if len(g) else math.nan}
        out[label] = row
    return out


def gate(bk: list[dict]) -> dict:
    rows = {b["bucket"]: b for b in bk}
    gaps = {k: rows[k]["gap"] if k in rows else math.nan for k in GATE_BUCKETS}
    ok = all(abs(g) <= GATE_PP for g in gaps.values() if g == g) and all(g == g for g in gaps.values())
    return {"pass": bool(ok), "gaps": gaps}


def evaluate(proj: pd.DataFrame, ev_season: int) -> dict:
    res = {"versions": {}}
    ev = proj[proj.season == ev_season]
    res["player_games"] = len(ev)
    res["dates"] = [str(ev["date"].min()), str(ev["date"].max())]
    res["history_seasons"] = sorted(int(s) for s in proj.season.unique() if s != ev_season)
    for s in ("pts", "reb"):
        res[f"{s.upper()}_projection"] = {
            "mae_model": float((ev[f"{s}_mean"] - ev[f"act_{s}"]).abs().mean()),
            "mae_last10_avg": float((ev[f"{s}_l10"] - ev[f"act_{s}"]).abs().dropna().mean()),
            "bias_model": float((ev[f"{s}_mean"] - ev[f"act_{s}"]).mean()),
        }
    res["minutes_mae"] = float((ev["proj_min"] - ev["act_min"]).abs().mean())

    season_start = pd.to_datetime(ev["date"]).min()
    for version in VERSIONS:
        vres = {}
        for s in ("pts", "reb"):
            t = proxy_table(proj, s, version)
            te = t[t.season == ev_season]
            m = {"pushes": int(te["push"].sum()), "n": len(te),
                 "shrink_end": float(t["shrink"].iloc[-1]),
                 "shrink_range_eval": [float(te["shrink"].min()), float(te["shrink"].max())]}
            raw, cal = pick_side(te, "q_raw"), pick_side(te, "q_cal")
            m["raw"] = {"buckets": buckets(raw), "split": side_split(raw), "gate": gate(buckets(raw))}
            m["cal"] = {"buckets": buckets(cal), "split": side_split(cal), "gate": gate(buckets(cal))}
            # Season start (item 5): picks that exist only because last season's history counts.
            use = cal if s == "pts" else raw
            early = use[(pd.to_datetime(use["date"]) - season_start).dt.days < EARLY_DAYS]
            m["season_start"] = {
                "days": EARLY_DAYS,
                "all": {"n": len(early), "pred": float(early.p_side.mean()), "hit": float(early.hit.mean())},
                "carried_history(<5 games this season)": summary_row(early[early.season_games < 5]),
                "flagged": summary_row(early[early["flags"] != ""]),
                "unflagged": summary_row(early[early["flags"] == ""]),
                "buckets_unflagged": buckets(early[early["flags"] == ""]),
            }
            m["flags_season"] = {f: summary_row(use[use["flags"].str.contains(f)]) for f in ("TEAM_CHANGE", "ROLE_CHANGE")}
            vres[s.upper()] = m
        res["versions"][version] = vres
    res["flag_counts_eval_season"] = {f: int(ev["flags"].str.contains(f).sum()) for f in ("TEAM_CHANGE", "ROLE_CHANGE")}
    early_ev = ev[(pd.to_datetime(ev["date"]) - season_start).dt.days < EARLY_DAYS]
    res["season_start_projections"] = {
        "first_days": EARLY_DAYS, "projected": len(early_ev),
        "carried_history": int((early_ev.season_games < 5).sum()),
        "flagged_team_change": int(early_ev["flags"].str.contains("TEAM_CHANGE").sum()),
        "flagged_role_change": int(early_ev["flags"].str.contains("ROLE_CHANGE").sum()),
    }
    return res


def summary_row(d: pd.DataFrame) -> dict:
    if not len(d):
        return {"n": 0}
    hi = d[d.p_side >= .6]
    return {"n": len(d), "pred": float(d.p_side.mean()), "hit": float(d.hit.mean()),
            "n_p60": len(hi), "pred_p60": float(hi.p_side.mean()) if len(hi) else None,
            "hit_p60": float(hi.hit.mean()) if len(hi) else None}


# ---------------------------------------------------------------- report


def pct(x):
    return "–" if x is None or x != x else f"{x:.1%}"


def bucket_table(bk: list[dict]) -> list[str]:
    L = ["| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred | Over share |",
         "|---|---|---|---|---|---|---|"]
    for b in bk:
        L.append(f"| {b['bucket']} | {b['n']} | {b['pred']:.1%} | {b['hit']:.1%} | {b['ci95']:.1%} | "
                 f"{b['gap']:+.1%} | {b['over_share']:.0%} |")
    return L


def split_table(sp: dict) -> list[str]:
    L = ["| Picks | n | Over: share / pred / hit | Under: share / pred / hit |", "|---|---|---|---|"]
    for k, v in sp.items():
        o, u = v["over"], v["under"]
        L.append(f"| {k} | {v['n']} | {pct(o['share'])} / {pct(o['pred'])} / {pct(o['hit'])} | "
                 f"{pct(u['share'])} / {pct(u['pred'])} / {pct(u['hit'])} |")
    return L


def to_md(res: dict, ev_season: int) -> str:
    L = [f"# Backtest calibration — {ev_season - 1}–{str(ev_season)[2:]} regular season", "",
         "**Calibration only, not edge.** No historical prop lines are available, so this checks whether "
         "the model's probabilities are honest, not whether they beat a bookmaker.", "",
         f"Evaluated player-games: {res['player_games']} ({res['dates'][0]} to {res['dates'][1]}). "
         f"History seasons replayed first (count toward the 5-game minimum, warm up learned corrections): "
         f"{res['history_seasons']}. Walk-forward throughout: each projection uses only earlier dates.", "",
         f"Minutes MAE {res['minutes_mae']:.1f}. "
         + " ".join(f"{m}: MAE {res[m + '_projection']['mae_model']:.2f} vs last-10 "
                    f"{res[m + '_projection']['mae_last10_avg']:.2f}, bias {res[m + '_projection']['bias_model']:+.2f}."
                    for m in ("PTS", "REB")), "",
         f"Points gate: calibrated pick-side buckets {', '.join(GATE_BUCKETS)} within ±{GATE_PP:.0%}.", ""]
    for version, (label, _) in VERSIONS.items():
        v = res["versions"][version]
        L += [f"## Proxy line: {label}", ""]
        for m in ("PTS", "REB"):
            r = v[m]
            L += [f"### {m}" + (f" — {r['pushes']} pushes excluded of {r['n']}" if r["pushes"] else f" (n={r['n']})"), ""]
            if m == "PTS":
                g = r["cal"]["gate"]
                L += [f"Walk-forward shrink factor during the season: {r['shrink_range_eval'][0]:.2f}–"
                      f"{r['shrink_range_eval'][1]:.2f}. **Gate: {'PASS' if g['pass'] else 'FAIL'}** "
                      f"({', '.join(f'{k} {x:+.1%}' for k, x in g['gaps'].items())}).", "",
                      "Calibrated (shrunk) pick-side:", ""] + bucket_table(r["cal"]["buckets"]) + [
                      "", "Over/under split, calibrated:", ""] + split_table(r["cal"]["split"]) + [
                      "", "Raw (before shrinkage), for reference:", ""] + bucket_table(r["raw"]["buckets"]) + [""]
            else:
                L += ["Raw pick-side (no recalibration applied):", ""] + bucket_table(r["raw"]["buckets"]) + [
                      "", "Over/under split:", ""] + split_table(r["raw"]["split"]) + [""]
    ss = res["season_start_projections"]
    L += ["## Season start: prior-season history counts toward the 5-game minimum", "",
          f"First {ss['first_days']} days of the season: {ss['projected']} projections, of which "
          f"{ss['carried_history']} relied on last season (fewer than 5 games this season). "
          f"Flags: TEAM_CHANGE {ss['flagged_team_change']}, ROLE_CHANGE {ss['flagged_role_change']}.", "",
          "Pick-side at the nearest-x.5 proxy (PTS calibrated, REB raw):", "",
          "| Market | Group | n | Pred | Hit | n (p≥60%) | Pred | Hit |", "|---|---|---|---|---|---|---|---|"]
    for m in ("PTS", "REB"):
        st = res["versions"]["half"][m]["season_start"]
        for k in ("carried_history(<5 games this season)", "flagged", "unflagged"):
            r = st[k]
            if r["n"]:
                L.append(f"| {m} | {k} | {r['n']} | {pct(r['pred'])} | {pct(r['hit'])} | {r['n_p60']} | "
                         f"{pct(r['pred_p60'])} | {pct(r['hit_p60'])} |")
        for f, r in res["versions"]["half"][m]["flags_season"].items():
            if r["n"]:
                L.append(f"| {m} | {f} (whole season) | {r['n']} | {pct(r['pred'])} | {pct(r['hit'])} | "
                         f"{r['n_p60']} | {pct(r['pred_p60'])} | {pct(r['hit_p60'])} |")
    return "\n".join(L) + "\n"


def main() -> None:
    cfg = config.load()["backtest"]
    seasons = [s["season"] for s in cfg["seasons"]]
    ev_season = cfg["evaluate_season"]
    have = [s for s in seasons if (ROOT / "data" / "processed" / f"games_{s}.csv.gz").exists()]
    if have != seasons:
        print(f"warning: missing processed data for {sorted(set(seasons) - set(have))}; replaying {have}")
    proj = run(have, cfg["min_prior_games"], cfg["min_proj_minutes"])
    res = evaluate(proj, ev_season)
    out = ROOT / "output" / "backtest"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"calibration_{ev_season}.json").write_text(json.dumps(res, indent=1, default=str))
    (out / f"calibration_{ev_season}.md").write_text(to_md(res, ev_season))
    proj[proj.season == ev_season].to_csv(ROOT / "data" / "processed" / f"backtest_projections_{ev_season}.csv.gz",
                                          index=False)
    print(to_md(res, ev_season))


if __name__ == "__main__":
    main()

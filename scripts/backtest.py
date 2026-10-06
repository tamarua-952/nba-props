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

Recalibration (nbaprops/calibrate.py) is walk-forward: on each date the
shrink/offset are fitted only on proxy-line results from earlier dates.
Several variants are scored; the one configured in config.yaml is reported
in full.

Writes output/backtest/calibration_<season>.{md,json} and
data/processed/backtest_projections_<season>.csv.gz.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nbaprops import config  # noqa: E402
from nbaprops.calibrate import Recalibrator  # noqa: E402
from nbaprops.replay import Replayer, load, proxy_line, raw_over_prob  # noqa: E402

PICK_BINS = [.5, .55, .6, .65, .7, .75, 1.0001]
GATE_BUCKETS = ("60%–65%", "65%–70%", "70%–75%")
EARLY_DAYS = 21
VERSIONS = {"half": "nearest x.5 (floor + 0.5)", "round": "nearest 0.5 (whole lines push)"}
VARIANTS = {  # name -> (shrink, offset)
    "raw": (False, False), "offset": (False, True), "shrink": (True, False), "shrink+offset": (True, True)}


def run(seasons: list[int], min_prior: int, min_minutes: float) -> pd.DataFrame:
    games, teams, players = load(seasons)
    rp = Replayer(games, teams, players, min_prior, min_minutes)
    out = []
    rp.run(on_date=lambda date, rows, acts: out.extend(rows))
    lg = rp.lg
    print("learned pass-through (end):", {k: round(float(lg.pass_through(k)), 3) for k in ("min", "pts", "reb")},
          "variance inflation:", {k: round(float(lg.var_inflation(k)), 3) for k in ("pts", "reb")}, flush=True)
    proj = pd.DataFrame(out)
    actual = players[["game_id", "player_id", "min", "pts", "reb"]].rename(
        columns={"min": "act_min", "pts": "act_pts", "reb": "act_reb"})
    proj = proj.merge(actual, on=["game_id", "player_id"], how="left")
    proj["flags"] = proj["flags"].fillna("")
    # Props are voided if the player does not play, and are only offered on rotation players.
    return proj[(proj["act_min"] > 0) & (proj["proj_min"] >= min_minutes)].reset_index(drop=True)


# ---------------------------------------------------------------- proxy-line evaluation


def proxy_table(proj: pd.DataFrame, stat: str, version: str, cap: float | None, min_obs: int) -> pd.DataFrame:
    """One row per projection at the proxy line, with raw and walk-forward-recalibrated P(over)."""
    df = proj.dropna(subset=[f"{stat}_l10"]).copy()
    df["line"] = proxy_line(df[f"{stat}_l10"], version)
    df = df[df["line"] > 0]
    df["q_raw"] = raw_over_prob(df["line"], df[f"{stat}_mean"], df[f"{stat}_var"])
    act = df[f"act_{stat}"]
    df["push"] = act == df["line"]
    df["over"] = (act > df["line"]).astype(int)
    df = df.sort_values("date").reset_index(drop=True)
    cals = {k: Recalibrator(shrink=s, offset=o, cap=cap, min_obs=min_obs) for k, (s, o) in VARIANTS.items()}
    for k in VARIANTS:
        df[f"qv_{k}"] = np.nan
    df["s"], df["c"] = np.nan, np.nan
    for _, idx in df.groupby("date").groups.items():
        d = df.loc[idx]
        for k, cal in cals.items():
            df.loc[idx, f"qv_{k}"] = cal.apply(d["q_raw"])
            if k == "shrink+offset" and cal.params():
                df.loc[idx, "s"], df.loc[idx, "c"] = cal.params()
        live = d[~d["push"]]
        for cal in cals.values():
            cal.update(live["q_raw"], live["over"])
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


def gate(bk: list[dict], pp: float) -> dict:
    rows = {b["bucket"]: b for b in bk}
    gaps = {k: rows[k]["gap"] for k in GATE_BUCKETS if k in rows}
    return {"pass": all(abs(g) <= pp for g in gaps.values()), "gaps": gaps}


def logloss(q, y):
    q = np.clip(np.asarray(q, dtype=float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))


def summary_row(d: pd.DataFrame) -> dict:
    if not len(d):
        return {"n": 0}
    hi = d[d.p_side >= .6]
    return {"n": len(d), "pred": float(d.p_side.mean()), "hit": float(d.hit.mean()),
            "n_p60": len(hi), "pred_p60": float(hi.p_side.mean()) if len(hi) else None,
            "hit_p60": float(hi.hit.mean()) if len(hi) else None}


def evaluate(proj: pd.DataFrame, ev_season: int, cal_cfg: dict) -> dict:
    res = {"versions": {}, "calibration_config": {k: cal_cfg[k] for k in ("PTS", "REB")}}
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
            m = s.upper()
            cfg = cal_cfg[m]
            chosen = {v: k for k, v in VARIANTS.items()}[(cfg["shrink"], cfg["offset"])]
            t = proxy_table(proj, s, version, cfg["cap"], cal_cfg["min_obs"])
            te = t[t.season == ev_season]
            live = te[~te["push"]]
            r = {"pushes": int(te["push"].sum()), "n": len(te), "chosen": chosen,
                 "s_range": [float(te["s"].min()), float(te["s"].max())],
                 "c_range": [float(te["c"].min()), float(te["c"].max())], "variants": {}}
            for k in VARIANTS:
                d = pick_side(te, f"qv_{k}")
                sp = side_split(d)["p>=60%"]
                r["variants"][k] = {
                    "logloss": logloss(live[f"qv_{k}"], live["over"]), "gate": gate(buckets(d), cal_cfg["gate_pp"]),
                    "over_gap_p60": sp["over"]["hit"] - sp["over"]["pred"],
                    "under_gap_p60": sp["under"]["hit"] - sp["under"]["pred"],
                    "over_share_p60": sp["over"]["share"]}
            r["variants"]["raw (no cap)"] = {"logloss": logloss(live["q_raw"], live["over"])}
            d = pick_side(te, f"qv_{chosen}")
            r["buckets"], r["split"], r["gate"] = buckets(d), side_split(d), gate(buckets(d), cal_cfg["gate_pp"])
            early = d[(pd.to_datetime(d["date"]) - season_start).dt.days < EARLY_DAYS]
            r["season_start"] = {
                "carried_history(<5 games this season)": summary_row(early[early.season_games < 5]),
                "flagged": summary_row(early[early["flags"] != ""]),
                "unflagged": summary_row(early[early["flags"] == ""])}
            r["flags_season"] = {f: summary_row(d[d["flags"].str.contains(f)]) for f in ("TEAM_CHANGE", "ROLE_CHANGE")}
            vres[m] = r
        res["versions"][version] = vres
    early_ev = ev[(pd.to_datetime(ev["date"]) - season_start).dt.days < EARLY_DAYS]
    res["season_start_projections"] = {
        "first_days": EARLY_DAYS, "projected": len(early_ev),
        "carried_history": int((early_ev.season_games < 5).sum()),
        "flagged_team_change": int(early_ev["flags"].str.contains("TEAM_CHANGE").sum()),
        "flagged_role_change": int(early_ev["flags"].str.contains("ROLE_CHANGE").sum()),
    }
    return res


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
         f"History seasons replayed first: {res['history_seasons']}. Walk-forward throughout: each projection "
         "and each recalibration uses only earlier dates.", "",
         f"Minutes MAE {res['minutes_mae']:.1f}. "
         + " ".join(f"{m}: MAE {res[m + '_projection']['mae_model']:.2f} vs last-10 "
                    f"{res[m + '_projection']['mae_last10_avg']:.2f}, bias {res[m + '_projection']['bias_model']:+.2f}."
                    for m in ("PTS", "REB")), "",
         f"Recalibration in use: {json.dumps(res['calibration_config'])}.", ""]
    for version, label in VERSIONS.items():
        v = res["versions"][version]
        L += [f"## Proxy line: {label}", ""]
        for m in ("PTS", "REB"):
            r = v[m]
            g = r["gate"]
            L += [f"### {m} — recalibration `{r['chosen']}`"
                  + (f", {r['pushes']} pushes excluded of {r['n']}" if r["pushes"] else f" (n={r['n']})"), "",
                  f"Fitted during the season: s {r['s_range'][0]:.2f}–{r['s_range'][1]:.2f}, "
                  f"c {r['c_range'][0]:+.3f}–{r['c_range'][1]:+.3f} (shrink+offset variant). "
                  f"60–75% gate: **{'PASS' if g['pass'] else 'FAIL'}** "
                  f"({', '.join(f'{k} {x:+.1%}' for k, x in g['gaps'].items())}).", ""]
            L += bucket_table(r["buckets"]) + ["", "Over/under split:", ""] + split_table(r["split"]) + [
                "", "Variants (walk-forward, evaluated season):", "",
                "| Variant | Log loss | Gate | Over gap p≥60 | Under gap p≥60 | Over share p≥60 |", "|---|---|---|---|---|---|"]
            for k, x in r["variants"].items():
                if "gate" in x:
                    L.append(f"| {k} | {x['logloss']:.4f} | {'PASS' if x['gate']['pass'] else 'FAIL'} | "
                             f"{x['over_gap_p60']:+.1%} | {x['under_gap_p60']:+.1%} | {pct(x['over_share_p60'])} |")
                else:
                    L.append(f"| {k} | {x['logloss']:.4f} | | | | |")
            L.append("")
    ss = res["season_start_projections"]
    L += ["## Season start: prior-season history counts toward the 5-game minimum", "",
          f"First {ss['first_days']} days: {ss['projected']} projections, {ss['carried_history']} relying on last "
          f"season (<5 games this season). TEAM_CHANGE {ss['flagged_team_change']}, "
          f"ROLE_CHANGE {ss['flagged_role_change']}.", "",
          "| Market | Group | n | Pred | Hit | n (p≥60%) | Pred | Hit |", "|---|---|---|---|---|---|---|---|"]
    for m in ("PTS", "REB"):
        rr = res["versions"]["half"][m]
        for k, r in list(rr["season_start"].items()) + [(f"{f} (season)", x) for f, x in rr["flags_season"].items()]:
            if r["n"]:
                L.append(f"| {m} | {k} | {r['n']} | {pct(r['pred'])} | {pct(r['hit'])} | {r['n_p60']} | "
                         f"{pct(r['pred_p60'])} | {pct(r['hit_p60'])} |")
    return "\n".join(L) + "\n"


def main() -> None:
    cfg = config.load()
    bt = cfg["backtest"]
    seasons = [s["season"] for s in bt["seasons"]]
    ev_season = bt["evaluate_season"]
    proj = run(seasons, bt["min_prior_games"], bt["min_proj_minutes"])
    res = evaluate(proj, ev_season, cfg["calibration"])
    out = ROOT / "output" / "backtest"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"calibration_{ev_season}.json").write_text(json.dumps(res, indent=1, default=str))
    (out / f"calibration_{ev_season}.md").write_text(to_md(res, ev_season))
    proj[proj.season == ev_season].to_csv(ROOT / "data" / "processed" / f"backtest_projections_{ev_season}.csv.gz",
                                          index=False)
    print(to_md(res, ev_season))


if __name__ == "__main__":
    main()

"""Daily brief: replay history, project today's slate, pick, price and flag.

Source-agnostic: the caller supplies the slate (live from ESPN, or replayed
from cached box scores) and the history to replay. See scripts/daily.py.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import dist
from .calibrate import Recalibrator
from .odds_api import BudgetExceeded, OddsAPI, consensus, match_event, norm_name
from .replay import Replayer, proxy_line, raw_over_prob

NZ = ZoneInfo("Pacific/Auckland")
ET = ZoneInfo("America/New_York")
MARKETS = {"pts": "PTS", "reb": "REB"}


@dataclass
class SlateGame:
    game_id: str
    start_utc: str
    home_id: str
    away_id: str
    home: str
    away: str
    home_name: str
    away_name: str
    home_spread: float | None
    available: dict[str, set] = field(default_factory=dict)
    # team_id -> [{player_id, player, cls}] for players listed questionable/doubtful/out
    injuries: dict[str, list] = field(default_factory=dict)


def tip_nzt(start_utc: str) -> str:
    t = dt.datetime.fromisoformat(start_utc.replace("Z", "+00:00")).astimezone(NZ)
    return t.strftime("%a %d %b %H:%M NZT").replace(" 0", " ")


# ---------------------------------------------------------------- learning from history


def replay_history(hist, cfg: dict, until: dt.date) -> tuple[Replayer, dict]:
    """Replay history before `until`, learning the walk-forward recalibration at the proxy line."""
    games, teams, players = hist
    bt, cal_cfg = cfg["backtest"], cfg["calibration"]
    rp = Replayer(games, teams, players, bt["min_prior_games"], bt["min_proj_minutes"])
    cals = {m: Recalibrator(shrink=cal_cfg[m]["shrink"], offset=cal_cfg[m]["offset"], cap=cal_cfg[m]["cap"],
                            min_obs=cal_cfg["min_obs"]) for m in MARKETS.values()}

    def learn(date, rows, acts):
        ok = [r for r in rows if r["proj_min"] >= bt["min_proj_minutes"]
              and acts.get((r["game_id"], r["player_id"]), {}).get("min", 0) > 0]
        for s, m in MARKETS.items():
            rr = [r for r in ok if not math.isnan(r[f"{s}_l10"])]
            if not rr:
                continue
            line = proxy_line([r[f"{s}_l10"] for r in rr])
            keep = line > 0
            act = np.array([acts[(r["game_id"], r["player_id"])][s] for r in rr])[keep]
            q = raw_over_prob(line[keep], np.array([r[f"{s}_mean"] for r in rr])[keep],
                              np.array([r[f"{s}_var"] for r in rr])[keep])
            line = line[keep]
            cals[m].update(q[act != line], (act > line)[act != line].astype(int))

    rp.run(until=until, on_date=learn)
    return rp, cals


# ---------------------------------------------------------------- the brief


def reasoning(r: dict, stat: str, side: str) -> str:
    unit = "pts" if stat == "pts" else "reb"
    bits = [f"proj {r[f'{stat}_mean']:.1f} {unit} in {r['proj_min']:.0f} min vs last-10 avg {r[f'{stat}_l10']:.1f}"]
    of = r[f"{stat}_opp_factor"]
    if abs(of - 1) >= 0.03:
        bits.append(f"opp allows {of - 1:+.0%} {unit} to {r['pos']}s")
    if abs(r["pace_factor"] - 1) >= 0.02:
        bits.append(f"pace {r['pace_factor'] - 1:+.0%}")
    if r["out_regulars"]:
        bits.append(f"{r['out_regulars']} teammate regular(s) out")
    if r["b2b"]:
        bits.append("back-to-back")
    if r.get("spread") is not None and abs(r["spread"]) >= 8:
        bits.append(f"spread {r['spread']:+.1f} (blowout risk)")
    return f"{side.capitalize()}: " + "; ".join(bits) + "."


def candidates(rows: list[dict], game: SlateGame, cals: dict, cfg: dict, rp: Replayer) -> list[dict]:
    pr, br = cfg["pricing"], cfg["brief"]
    implied = 1 / pr["typical_market_price"]
    out = []
    for r in rows:
        if r["proj_min"] < cfg["backtest"]["min_proj_minutes"]:
            continue
        for s, m in MARKETS.items():
            if not cfg["calibration"][m].get("enabled", True) or m not in cfg["markets"]:
                continue
            l10 = r[f"{s}_l10"]
            if l10 != l10:
                continue
            line = float(proxy_line([l10])[0])
            if line <= 0:
                continue
            q = float(cals[m].apply(raw_over_prob([line], [r[f"{s}_mean"]], [r[f"{s}_var"]]))[0])
            side = "over" if q >= 0.5 else "under"
            p = q if side == "over" else 1 - q
            edge = p - implied
            if edge <= br["min_edge"]:
                continue

            def q_at(ln, _s=s, _m=m, _r=r):
                return float(cals[_m].apply(raw_over_prob([ln], [_r[f"{_s}_mean"]], [_r[f"{_s}_var"]]))[0])

            def prob_at(ln, _side=side):
                return q_at(ln) if _side == "over" else 1 - q_at(ln)

            # Betcha's line is unknown, so price every half-point line around the projection:
            # at each line, the side the model favours, its probability and the bet threshold.
            ladder = []
            centre = math.floor(r[f"{s}_mean"]) + 0.5
            for k in range(-br["ladder_width"][m], br["ladder_width"][m] + 1):
                ln = centre + k
                if ln <= 0:
                    continue
                qo = q_at(ln)
                sd, pp = ("over", qo) if qo >= 0.5 else ("under", 1 - qo)
                ladder.append({"line": ln, "side": sd, "model_prob": round(pp, 4),
                               "threshold": round(dist.bet_threshold(pp, pr["margin_buffer"]), 2)})

            flags = [f for f in r["flags"].split(",") if f]
            pending = [i for tid in (r["team_id"],) for i in game.injuries.get(tid, [])
                       if i["cls"] in ("questionable", "doubtful")
                       and (i["player_id"] == r["player_id"]
                            or rp.lg.players[i["player_id"]].ew_min.value >= br["key_player_minutes"])]
            if pending:
                flags.append("INJURY_PENDING")
            team, opp = (game.home, game.away) if r["home"] else (game.away, game.home)
            out.append({
                "game_id": game.game_id, "tip_utc": game.start_utc, "tip_nzt": tip_nzt(game.start_utc),
                "player_id": r["player_id"], "player": r["player"], "team": team, "opp": opp,
                "home": bool(r["home"]), "market": m, "side": side, "line": line,
                "projection": round(r[f"{s}_mean"], 1), "proj_min": round(r["proj_min"], 1),
                "last10_avg": round(l10, 1), "model_prob": round(p, 4), "edge": round(edge, 4),
                "fair_odds": round(dist.fair_odds(p), 2),
                "threshold": round(dist.bet_threshold(p, pr["margin_buffer"]), 2),
                "ladder": ladder,
                "flags": flags,
                "injury_pending": [f"{i['player']} ({i['cls']})" for i in pending],
                "reasoning": reasoning(r, s, side),
                "_prob_at": prob_at,
            })
    return out


def select(cands: list[dict], max_picks: int) -> list[dict]:
    """Best edge per player, then the top `max_picks` by edge."""
    best: dict = {}
    for c in cands:
        if c["player_id"] not in best or c["edge"] > best[c["player_id"]]["edge"]:
            best[c["player_id"]] = c
    return sorted(best.values(), key=lambda c: -c["edge"])[:max_picks]


def apply_consensus(picks: list[dict], slate: list[SlateGame], odds: OddsAPI | None, cfg: dict,
                    now: dt.datetime) -> dict:
    """Morning Odds API call for the top pick games (CONSENSUS_GAP), within the budget rules."""
    oc = cfg["odds_api"]
    games = []
    for p in picks:
        if p["game_id"] not in games:
            games.append(p["game_id"])
    top = games[: oc["max_games_per_day"]]
    status = {"top_games": top, "morning_calls": 0, "skipped_morning": False, "note": ""}
    if odds is None:
        status["note"] = "Odds API not used (no key, or replay mode)."
        return status
    n = len(top)
    if not odds.can_afford("event_odds", 2 * n):
        status["skipped_morning"] = True
        status["note"] = ("Budget short: morning consensus call skipped to keep the closing-line call."
                          if odds.can_afford("event_odds", n) else "Budget exhausted: no Odds API calls today.")
        return status
    try:
        events = odds.events()
    except Exception as e:  # noqa: BLE001
        status["note"] = f"Odds API events failed: {e}"
        return status
    by_id = {g.game_id: g for g in slate}
    gap = cfg["brief"]["consensus_gap"]
    status["events"] = {}
    for gid in top:
        g = by_id[gid]
        ev = match_event(events, g.home_name, g.away_name, g.start_utc)
        if not ev:
            status["note"] += f" No Odds API event for {g.away}@{g.home}."
            continue
        status["events"][gid] = ev["id"]
        try:
            cons = consensus(odds.event_props(ev["id"]))
            status["morning_calls"] += 1
        except BudgetExceeded as e:
            status["note"] += f" {e}"
            break
        except Exception as e:  # noqa: BLE001
            status["note"] += f" Odds API props failed for {g.away}@{g.home}: {e}"
            continue
        for p in picks:
            if p["game_id"] != gid:
                continue
            c = cons.get((norm_name(p["player"]), p["market"]))
            if not c:
                p["consensus"] = None
                continue
            p_model = p["_prob_at"](c["line"])
            mkt = None
            if c["over_price"] and c["under_price"]:
                io, iu = 1 / c["over_price"], 1 / c["under_price"]
                mkt = (io if p["side"] == "over" else iu) / (io + iu)
            p["consensus"] = {"line": c["line"], "books": c["books"], "model_prob_at_line": round(p_model, 4),
                              "market_prob_no_vig": None if mkt is None else round(mkt, 4)}
            if (abs(c["line"] - p["line"]) >= gap[p["market"]] or p_model < 0.5
                    or (mkt is not None and abs(p_model - mkt) >= gap["prob"])):
                p["flags"].append("CONSENSUS_GAP")
    return status


def build(slate_date: dt.date, slate: list[SlateGame], hist, cfg: dict, now: dt.datetime,
          season: int, odds: OddsAPI | None = None) -> dict:
    """Build the brief for the US slate on `slate_date` (ET), as seen at `now`."""
    rp, cals = replay_history(hist, cfg, until=slate_date)
    rp.start_season(season)
    br = cfg["brief"]
    cutoff = now + dt.timedelta(minutes=br["min_minutes_to_tip"])
    playable = [g for g in slate
                if dt.datetime.fromisoformat(g.start_utc.replace("Z", "+00:00")) > cutoff]
    cands = []
    for g in playable:
        rows = rp.project_game(slate_date, g.game_id, g.home_id, g.away_id, g.home_spread, g.available)
        cands += candidates(rows, g, cals, cfg, rp)
    picks = select(cands, cfg["pricing"]["max_picks"])
    odds_status = apply_consensus(picks, playable, odds, cfg, now)
    for p in picks:
        p.pop("_prob_at", None)
        p.setdefault("consensus", None)
    cal_state = {m: c.params() for m, c in cals.items()}
    return {
        "brief_date_nzt": (slate_date + dt.timedelta(days=1)).isoformat(),
        "slate_date_et": slate_date.isoformat(),
        "generated_at_utc": now.astimezone(dt.timezone.utc).isoformat(timespec="minutes"),
        "status": "OK" if slate else "NO_GAMES",
        "message": "" if slate else "No regular-season NBA games on this slate.",
        "games": len(slate), "games_playable": len(playable), "candidates": len(cands),
        "markets": [m for m in MARKETS.values() if m in cfg["markets"]
                    and cfg["calibration"][m].get("enabled", True)],
        "calibration": {m: {"shrink": None if v is None else v[0], "offset": None if v is None else v[1],
                            "cap": cfg["calibration"][m]["cap"]} for m, v in cal_state.items()},
        "margin_buffer": cfg["pricing"]["margin_buffer"],
        "odds_api": odds_status,
        "picks": picks,
    }


def down_brief(slate_date: dt.date, now: dt.datetime, error: str) -> dict:
    return {"brief_date_nzt": (slate_date + dt.timedelta(days=1)).isoformat(),
            "slate_date_et": slate_date.isoformat(),
            "generated_at_utc": now.astimezone(dt.timezone.utc).isoformat(timespec="minutes"),
            "status": "DATA_SOURCE_DOWN", "message": "Data source down, no picks.", "error": error[:500],
            "picks": []}


# ---------------------------------------------------------------- rendering


def to_markdown(b: dict) -> str:
    L = [f"# NBA props brief — {b['brief_date_nzt']} (NZ morning)", "",
         f"US slate {b['slate_date_et']}. Generated {b['generated_at_utc']} UTC.", ""]
    if b["status"] == "DATA_SOURCE_DOWN":
        return "\n".join(L + ["**Data source down, no picks.**", "", f"`{b.get('error', '')}`", ""])
    if not b["picks"]:
        msg = b.get("message") or "No picks clear the edge threshold today."
        return "\n".join(L + [f"**No picks.** {msg}", ""])
    L += ["**How to use:** find the player and market on Betcha. If Betcha's line matches the pick line, bet "
          "only if the price is **at or above the threshold**. If the line differs, use that pick's ladder "
          "(side and threshold at each line; lines missing from the ladder have no edge). Singles only; every "
          "pick goes in the ledger whether you bet or not.", "",
          "**Caution:** pick lines are a proxy (last-10 average) because Betcha's lines are not available to "
          "the model. A very high probability usually means Betcha's line will sit closer to the projection — "
          "check the ladder at Betcha's actual line.", "",
          "| # | Tip-off | Player | Market | Pick | Proj | Model | Fair | **Bet at ≥** | Flags |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for i, p in enumerate(b["picks"], 1):
        L.append(f"| {i} | {p['tip_nzt']} | {p['player']} ({p['team']} {'v' if p['home'] else '@'} {p['opp']}) | "
                 f"{p['market']} | {p['side'].upper()} {p['line']} | {p['projection']} | {p['model_prob']:.1%} | "
                 f"${p['fair_odds']:.2f} | **${p['threshold']:.2f}** | {', '.join(p['flags']) or '–'} |")
    L += ["", "## Notes per pick", ""]
    for i, p in enumerate(b["picks"], 1):
        ladder = " · ".join(f"{x['line']} {x['side'][0].upper()} ≥${x['threshold']:.2f}"
                            for x in p["ladder"] if x["model_prob"] > 1 / 1.87)
        L.append(f"{i}. **{p['player']} {p['market']} {p['side']} {p['line']}** — {p['reasoning']}")
        if ladder:
            L.append(f"   - If Betcha's line differs (line, side, bet at ≥): {ladder}")
        if p["injury_pending"]:
            L.append(f"   - Injury pending: {', '.join(p['injury_pending'])}. Check status before betting.")
        c = p.get("consensus")
        if c:
            mk = f", market no-vig {c['market_prob_no_vig']:.1%}" if c["market_prob_no_vig"] is not None else ""
            L.append(f"   - Consensus line {c['line']} ({c['books']} books): model {c['model_prob_at_line']:.1%}{mk}.")
    oa = b["odds_api"]
    L += ["", "## Flags", "",
          "- `INJURY_PENDING`: a key teammate (or the player) is questionable/doubtful; the pick depends on it.",
          "- `CONSENSUS_GAP`: far from the market consensus line/price; likely model error or missing news.",
          "- `TEAM_CHANGE`: first 10 games with a new team. `ROLE_CHANGE`: minutes this season differ from "
          "last season's by 6+ (first 10 games).", "",
          "## Run details", "",
          f"- Games on slate: {b['games']} ({b['games_playable']} not yet tipping); candidates with edge: "
          f"{b['candidates']}; markets: {', '.join(b['markets'])}.",
          "- Calibration: " + "; ".join(
              f"{m} shrink {v['shrink']}, offset {v['offset']}, cap {v['cap']}" for m, v in b["calibration"].items()),
          f"- Threshold = fair price × (1 + {b['margin_buffer']:.0%}). Edge ranked vs a typical $1.87 price.",
          f"- Odds API: {oa['morning_calls']} morning call(s) for top games {oa['top_games']}. {oa['note']}".rstrip(),
          ""]
    return "\n".join(L)


def ledger_rows(b: dict) -> list[dict]:
    return [{"date": b["brief_date_nzt"], "game_id": p["game_id"], "tip_nzt": p["tip_nzt"],
             "player_id": p["player_id"], "player": p["player"], "team": p["team"], "opp": p["opp"],
             "market": p["market"], "side": p["side"], "line": p["line"], "projection": p["projection"],
             "model_prob": p["model_prob"], "fair_odds": p["fair_odds"], "threshold": p["threshold"],
             "flags": ";".join(p["flags"]),
             "consensus_line": (p.get("consensus") or {}).get("line", "")} for p in b["picks"]]


def results_lookup(players: pd.DataFrame) -> dict:
    """(game_id, player_id) -> {min, pts, reb} from processed box scores."""
    return {(r.game_id, r.player_id): {"min": r.min, "PTS": r.pts, "REB": r.reb}
            for r in players.itertuples()}

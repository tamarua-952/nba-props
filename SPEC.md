# NBA Props Analyst — Build Spec

Hand this file to Claude Code as the brief for the build. Keep it in the repo root.

## Goal

Each morning (NZ time), find NBA player points and rebounds over/under props where the model's probability is meaningfully higher than the price Betcha/TAB NZ is likely to offer. Output a ranked brief with a fair-odds threshold for each pick, so the user only checks Betcha's price and bets if it is at or above the threshold.

Singles only. No multis until 300+ logged picks show positive closing-line value (CLV).

## Constraints

* Free data sources only.
* No scraping Betcha/TAB (terms of service). The user checks Betcha prices manually.
* The user is a beginner bettor with a tiny bankroll ($20). Every pick is logged to a paper ledger whether or not it is bet.

## Step 0 — Test data sources before writing the model

Write a small script that tests each candidate source from GitHub Actions (cloud IPs are sometimes blocked) and from local, and reports what works:

* Player game logs and box scores: `nba_api` (stats.nba.com); fallback ESPN's public JSON endpoints or Basketball-Reference (respect rate limits).
* Schedule and game times.
* Injury status: the official NBA injury report; fallback ESPN injuries page.
* Free consensus prop lines: test free sources (e.g. The Odds API free tier, public odds-comparison pages). Used only as a sanity check, never as a model input.

Do not build further until Step 0 reports which sources are reliable.

## Pipeline

1. Ingest today's NBA slate, player game logs (this season and last season), team pace, opponent defence by position, and injury statuses.
2. Project minutes for each player. Start from the recent minutes trend, then adjust for:
   * teammates ruled out or questionable
   * back-to-backs and rest
   * blowout risk, using the spread if available
3. Project per-minute rates for points and rebounds. Adjust for:
   * usage redistribution when teammates are out (use on/off splits where samples allow)
   * opponent points and rebounds allowed to that position (recent-weighted)
   * expected game pace
   * home/away

   Do not use raw head-to-head history as a feature; the samples are too small.
4. Distribution. Turn the projection into P(over line) and P(under line) using a player-specific variance:
   * points: normal or negative binomial
   * rebounds: negative binomial
5. Fair odds. Fair price = 1 / P. Bet threshold = the fair price plus a margin buffer (start at +5%, configurable).
6. Flags. Mark each pick with:
   * `INJURY_PENDING`: a key player is questionable and the pick depends on his status
   * `CONSENSUS_GAP`: the model's line or probability is far from the free consensus line (likely a model error or missing news)
7. Rank. Sort by model edge versus a typical market price (implied probability around 52–53% at ~$1.87). Keep the top 5–8 only.

## Outputs

* `output/brief_YYYY-MM-DD.json` and `.md`. Each pick has:
  * player, team, opponent, tip-off time in NZT
  * market (PTS/REB), side (over/under) and line
  * projection and model probability
  * fair odds and bet threshold
  * flags
  * one-line reasoning
* `ledger.csv`: every pick (date, player, market, line, side, model probability, threshold), plus the Betcha price taken (if any), the closing line, the result and the profit/loss. Results and closing lines are filled in by the next day's run.
* A weekly report covering: hit rate versus model probability (calibration), average CLV, and profit/loss per unit.

## Backtest

Do a walk-forward backtest on the 2025–26 season before any live use:

* Use only information available before each game.
* Report calibration buckets (does a model 60% hit about 60% of the time?).
* Compare projections against historical closing lines where available.

## Automation

* A GitHub Action runs the pipeline daily at 09:00 NZT. That is 20:00 UTC the previous day while NZ is on daylight time; adjust when NZ daylight time ends. It commits the brief and ledger to the repo.
* A Claude scheduled task at about 09:45 NZT reads the latest brief from the repo, checks late injury news, and sends the user the final brief.

## Tech

* Python 3.11 with pandas, numpy, scipy and nba_api.
* Tests for the probability and fair-odds maths.
* Configuration (thresholds, buffer, markets) in `config.yaml`.

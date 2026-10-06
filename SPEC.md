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

### Step 0 outcome (GitHub Actions, 2026-10-06) and source decisions

Report: `output/step0/source_report_github-actions.md`.

* `nba_api` / stats.nba.com timed out and cdn.nba.com returned 403 from GitHub Actions. **Treat `nba_api` as unavailable.** It is not used anywhere in the pipeline.
* **ESPN's public JSON is the primary source** for schedule, box scores, player game logs, rosters/positions, game spreads and injuries.
* **Basketball-Reference is for gap filling only** (e.g. a box score ESPN is missing), always under its rate limit (<20 requests/minute; the fetcher spaces requests ≥3.5 s apart).
* **Cache every raw response** gzipped, exactly as received (`data/raw/<source>/`). Completed games and past dates are never refetched.
* **If ESPN fails** (after retries) on the run's required data, the brief says **"Data source down, no picks"** and contains no picks. No partial or stale-data picks.
* The official NBA injury report PDF was not found during preseason. ESPN injuries is the injury source; recheck the official report after opening night.
* PrizePicks (403) and Underdog (426) are unusable. ESPN propBets had no props for a preseason game; not relied on.

### The Odds API (free tier, `ODDS_API_KEY` secret)

* Used **only for games that have picks**, and never as a model input. Two uses:
  1. One morning call per pick's game, for `CONSENSUS_GAP`.
  2. One call per pick's game near tip-off, as a **proxy closing line** for CLV.
* The real credit cost of each call type is measured from the API's response headers (`x-requests-last`, `x-requests-remaining`) and logged to `data/odds_api_usage.json`.
* **Monthly budget guard**: before each call, estimate its cost from the largest cost observed for that call type. Refuse the call if it would take the remaining balance below a reserve (`odds_api.reserve` in `config.yaml`), so usage stops before the 500-credit monthly limit. A refused call means the pick goes out without `CONSENSUS_GAP` checking / without a closing line, and the brief says so.

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
   * `CONSENSUS_GAP`: the model's line or probability is far from The Odds API consensus line (likely a model error or missing news)
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
* **The backtest measures calibration only, not edge.** There are no free historical prop lines, so it cannot show the model beats the market. Edge is measured live, by CLV against the proxy closing line, in the paper ledger.
* Because there are no historical lines, calibration is checked at a set of lines around each projection, using box-score data pulled from ESPN and cached.

## Automation

* A GitHub Action runs the pipeline daily at 09:00 NZT. That is 20:00 UTC the previous day while NZ is on daylight time; adjust when NZ daylight time ends. It commits the brief and ledger to the repo.
* A Claude scheduled task at about 09:45 NZT reads the latest brief from the repo, checks late injury news, and sends the user the final brief.

## Tech

* Python 3.11 with pandas, numpy, scipy and requests (ESPN JSON). No `nba_api`.
* Every workflow that commits to the repo shares one concurrency group, so runs queue instead of racing each other's pushes.
* Tests for the probability and fair-odds maths.
* Configuration (thresholds, buffer, markets) in `config.yaml`.

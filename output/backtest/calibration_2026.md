# Backtest calibration — 2025–26 regular season

**Calibration only, not edge.** No historical prop lines are available, so this checks whether the model's probabilities are honest, not whether they beat a bookmaker.

Evaluated player-games: 16726 (2025-10-21 to 2026-04-12). History seasons replayed first (count toward the 5-game minimum, warm up learned corrections): [2025]. Walk-forward throughout: each projection uses only earlier dates.

Minutes MAE 4.6. PTS: MAE 5.22 vs last-10 5.29, bias +0.28. REB: MAE 2.01 vs last-10 2.07, bias +0.14.

Points gate: calibrated pick-side buckets 60%–65%, 65%–70%, 70%–75% within ±2%.

## Proxy line: nearest x.5 (floor + 0.5)

### PTS (n=16726)

Walk-forward shrink factor during the season: 0.73–0.77. **Gate: FAIL** (60%–65% -0.1%, 65%–70% +0.0%, 70%–75% -2.6%).

Calibrated (shrunk) pick-side:

| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred | Over share |
|---|---|---|---|---|---|---|
| 50%–55% | 6544 | 52.5% | 52.2% | 1.2% | -0.2% | 42% |
| 55%–60% | 5336 | 57.4% | 57.2% | 1.3% | -0.2% | 29% |
| 60%–65% | 3205 | 62.2% | 62.1% | 1.7% | -0.1% | 21% |
| 65%–70% | 1350 | 66.9% | 67.0% | 2.5% | +0.0% | 21% |
| 70%–75% | 253 | 71.7% | 69.2% | 5.7% | -2.6% | 19% |
| 75%–100% | 38 | 76.6% | 84.2% | 11.6% | +7.7% | 32% |

Over/under split, calibrated:

| Picks | n | Over: share / pred / hit | Under: share / pred / hit |
|---|---|---|---|
| all | 16726 | 32.0% / 56.0% / 55.5% | 68.0% / 58.1% / 58.1% |
| p>=55% | 10182 | 25.5% / 59.9% / 59.7% | 74.5% / 60.8% / 60.7% |
| p>=60% | 4846 | 21.3% / 64.1% / 62.8% | 78.7% / 64.2% / 64.4% |

Raw (before shrinkage), for reference:

| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred | Over share |
|---|---|---|---|---|---|---|
| 50%–55% | 4954 | 52.5% | 52.1% | 1.4% | -0.4% | 44% |
| 55%–60% | 4375 | 57.4% | 54.4% | 1.5% | -3.0% | 34% |
| 60%–65% | 3445 | 62.3% | 59.3% | 1.6% | -3.0% | 25% |
| 65%–70% | 2256 | 67.3% | 63.2% | 2.0% | -4.1% | 21% |
| 70%–75% | 1206 | 72.1% | 66.5% | 2.7% | -5.6% | 22% |
| 75%–100% | 490 | 78.3% | 70.2% | 4.0% | -8.1% | 21% |

### REB (n=16726)

Raw pick-side (no recalibration applied):

| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred | Over share |
|---|---|---|---|---|---|---|
| 50%–55% | 5145 | 52.5% | 51.9% | 1.4% | -0.6% | 46% |
| 55%–60% | 4390 | 57.4% | 56.3% | 1.5% | -1.1% | 37% |
| 60%–65% | 3464 | 62.4% | 63.4% | 1.6% | +1.0% | 29% |
| 65%–70% | 2167 | 67.2% | 66.8% | 2.0% | -0.4% | 24% |
| 70%–75% | 1090 | 72.2% | 72.4% | 2.7% | +0.2% | 21% |
| 75%–100% | 470 | 78.4% | 79.1% | 3.7% | +0.8% | 23% |

Over/under split:

| Picks | n | Over: share / pred / hit | Under: share / pred / hit |
|---|---|---|---|
| all | 16726 | 34.8% / 58.0% / 55.9% | 65.2% / 60.7% / 61.3% |
| p>=55% | 11581 | 30.1% / 61.8% / 60.1% | 69.9% / 63.5% / 64.0% |
| p>=60% | 7191 | 25.6% / 65.9% / 63.7% | 74.4% / 66.6% / 67.9% |

## Proxy line: nearest 0.5 (whole lines push)

### PTS — 578 pushes excluded of 16726

Walk-forward shrink factor during the season: 0.73–0.77. **Gate: PASS** (60%–65% +0.8%, 65%–70% -0.7%, 70%–75% -1.8%).

Calibrated (shrunk) pick-side:

| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred | Over share |
|---|---|---|---|---|---|---|
| 50%–55% | 6304 | 52.4% | 52.3% | 1.2% | -0.1% | 41% |
| 55%–60% | 5088 | 57.4% | 56.5% | 1.4% | -0.9% | 30% |
| 60%–65% | 3111 | 62.2% | 63.0% | 1.7% | +0.8% | 23% |
| 65%–70% | 1339 | 67.0% | 66.2% | 2.5% | -0.7% | 22% |
| 70%–75% | 270 | 71.8% | 70.0% | 5.5% | -1.8% | 24% |
| 75%–100% | 36 | 76.5% | 83.3% | 12.2% | +6.8% | 33% |

Over/under split, calibrated:

| Picks | n | Over: share / pred / hit | Under: share / pred / hit |
|---|---|---|---|
| all | 16148 | 32.4% / 56.2% / 55.8% | 67.6% / 58.1% / 57.9% |
| p>=55% | 9844 | 26.6% / 60.1% / 59.6% | 73.4% / 60.9% / 60.6% |
| p>=60% | 4756 | 22.5% / 64.3% / 64.6% | 77.5% / 64.2% / 64.4% |

Raw (before shrinkage), for reference:

| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred | Over share |
|---|---|---|---|---|---|---|
| 50%–55% | 4809 | 52.5% | 51.5% | 1.4% | -1.0% | 43% |
| 55%–60% | 4148 | 57.4% | 54.5% | 1.5% | -3.0% | 34% |
| 60%–65% | 3327 | 62.3% | 59.8% | 1.7% | -2.6% | 26% |
| 65%–70% | 2164 | 67.3% | 63.6% | 2.0% | -3.7% | 22% |
| 70%–75% | 1182 | 72.2% | 65.4% | 2.7% | -6.8% | 22% |
| 75%–100% | 518 | 78.3% | 70.7% | 3.9% | -7.7% | 24% |

### REB — 1317 pushes excluded of 16726

Raw pick-side (no recalibration applied):

| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred | Over share |
|---|---|---|---|---|---|---|
| 50%–55% | 4761 | 52.4% | 52.5% | 1.4% | +0.1% | 47% |
| 55%–60% | 4199 | 57.4% | 57.5% | 1.5% | +0.1% | 38% |
| 60%–65% | 3091 | 62.4% | 62.5% | 1.7% | +0.1% | 31% |
| 65%–70% | 1935 | 67.3% | 66.7% | 2.1% | -0.6% | 28% |
| 70%–75% | 963 | 72.2% | 73.3% | 2.8% | +1.1% | 26% |
| 75%–100% | 460 | 78.5% | 76.1% | 3.9% | -2.4% | 29% |

Over/under split:

| Picks | n | Over: share / pred / hit | Under: share / pred / hit |
|---|---|---|---|
| all | 15409 | 37.0% / 58.3% / 56.5% | 63.0% / 60.5% / 61.5% |
| p>=55% | 10648 | 32.7% / 62.1% / 60.2% | 67.3% / 63.3% / 64.2% |
| p>=60% | 6449 | 29.1% / 66.2% / 62.7% | 70.9% / 66.6% / 67.8% |

## Season start: prior-season history counts toward the 5-game minimum

First 21 days of the season: 2153 projections, of which 1161 relied on last season (fewer than 5 games this season). Flags: TEAM_CHANGE 396, ROLE_CHANGE 505.

Pick-side at the nearest-x.5 proxy (PTS calibrated, REB raw):

| Market | Group | n | Pred | Hit | n (p≥60%) | Pred | Hit |
|---|---|---|---|---|---|---|---|
| PTS | carried_history(<5 games this season) | 1161 | 57.7% | 60.1% | 348 | 64.1% | 75.9% |
| PTS | flagged | 781 | 57.6% | 58.3% | 225 | 64.5% | 69.3% |
| PTS | unflagged | 1372 | 57.6% | 59.2% | 414 | 64.3% | 69.3% |
| PTS | TEAM_CHANGE (whole season) | 778 | 57.3% | 59.1% | 219 | 63.9% | 69.4% |
| PTS | ROLE_CHANGE (whole season) | 686 | 57.8% | 60.8% | 220 | 64.1% | 72.7% |
| REB | carried_history(<5 games this season) | 1161 | 59.9% | 63.0% | 523 | 66.2% | 71.5% |
| REB | flagged | 781 | 59.5% | 62.2% | 330 | 66.0% | 70.3% |
| REB | unflagged | 1372 | 59.7% | 60.6% | 601 | 66.2% | 69.7% |
| REB | TEAM_CHANGE (whole season) | 778 | 59.6% | 64.4% | 321 | 66.4% | 72.0% |
| REB | ROLE_CHANGE (whole season) | 686 | 59.9% | 63.4% | 306 | 66.1% | 70.3% |

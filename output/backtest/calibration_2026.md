# Backtest calibration — 2025–26 regular season

**Calibration only, not edge.** No historical prop lines are available, so this checks whether the model's probabilities are honest, not whether they beat a bookmaker.

Evaluated player-games: 16726 (2025-10-21 to 2026-04-12). History seasons replayed first: [2025]. Walk-forward throughout: each projection and each recalibration uses only earlier dates.

Minutes MAE 4.6. PTS: MAE 5.22 vs last-10 5.29, bias +0.28. REB: MAE 2.01 vs last-10 2.07, bias +0.14.

Recalibration in use: {"PTS": {"shrink": true, "offset": false, "cap": 0.7}, "REB": {"shrink": false, "offset": true, "cap": null}}.

## Proxy line: nearest x.5 (floor + 0.5)

### PTS — recalibration `shrink` (n=16726)

Fitted during the season: s 0.73–0.80, c -0.003–+0.010 (shrink+offset variant). 60–75% gate: **PASS** (60%–65% -0.1%, 65%–70% +0.0%, 70%–75% +1.1%).

| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred | Over share |
|---|---|---|---|---|---|---|
| 50%–55% | 6544 | 52.5% | 52.2% | 1.2% | -0.2% | 42% |
| 55%–60% | 5336 | 57.4% | 57.2% | 1.3% | -0.2% | 29% |
| 60%–65% | 3205 | 62.2% | 62.1% | 1.7% | -0.1% | 21% |
| 65%–70% | 1350 | 66.9% | 67.0% | 2.5% | +0.0% | 21% |
| 70%–75% | 291 | 70.0% | 71.1% | 5.2% | +1.1% | 21% |

Over/under split:

| Picks | n | Over: share / pred / hit | Under: share / pred / hit |
|---|---|---|---|
| all | 16726 | 32.0% / 56.0% / 55.5% | 68.0% / 58.0% / 58.1% |
| p>=55% | 10182 | 25.5% / 59.9% / 59.7% | 74.5% / 60.8% / 60.7% |
| p>=60% | 4846 | 21.3% / 64.0% / 62.8% | 78.7% / 64.0% / 64.4% |

Variants (walk-forward, evaluated season):

| Variant | Log loss | Gate | Over gap p≥60 | Under gap p≥60 | Over share p≥60 |
|---|---|---|---|---|---|
| raw | 0.6788 | FAIL | -3.5% | -3.1% | 23.1% |
| offset | 0.6788 | FAIL | -4.5% | -2.2% | 29.1% |
| shrink | 0.6771 | PASS | -1.2% | +0.3% | 21.3% |
| shrink+offset | 0.6773 | PASS | -1.3% | +0.5% | 22.4% |
| raw (no cap) | 0.6795 | | | | |

### REB — recalibration `offset` (n=16726)

Fitted during the season: s 0.82–0.91, c -0.020–-0.015 (shrink+offset variant). 60–75% gate: **PASS** (60%–65% +0.4%, 65%–70% -1.3%, 70%–75% +0.2%).

| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred | Over share |
|---|---|---|---|---|---|---|
| 50%–55% | 4930 | 52.5% | 52.5% | 1.4% | -0.0% | 44% |
| 55%–60% | 4161 | 57.4% | 55.9% | 1.5% | -1.5% | 34% |
| 60%–65% | 3478 | 62.4% | 62.8% | 1.6% | +0.4% | 25% |
| 65%–70% | 2340 | 67.2% | 65.9% | 1.9% | -1.3% | 18% |
| 70%–75% | 1209 | 72.2% | 72.5% | 2.5% | +0.2% | 16% |
| 75%–100% | 608 | 78.4% | 77.8% | 3.3% | -0.6% | 12% |

Over/under split:

| Picks | n | Over: share / pred / hit | Under: share / pred / hit |
|---|---|---|---|
| all | 16726 | 30.8% / 57.7% / 57.1% | 69.2% / 61.3% / 60.9% |
| p>=55% | 11796 | 25.2% / 61.6% / 60.7% | 74.8% / 64.0% / 63.4% |
| p>=60% | 7635 | 20.4% / 65.5% / 64.0% | 79.6% / 67.0% / 67.1% |

Variants (walk-forward, evaluated season):

| Variant | Log loss | Gate | Over gap p≥60 | Under gap p≥60 | Over share p≥60 |
|---|---|---|---|---|---|
| raw | 0.6635 | PASS | -2.2% | +1.3% | 25.6% |
| offset | 0.6632 | PASS | -1.5% | +0.1% | 20.4% |
| shrink | 0.6638 | FAIL | -0.9% | +3.1% | 25.1% |
| shrink+offset | 0.6635 | PASS | +1.1% | +1.8% | 16.1% |
| raw (no cap) | 0.6635 | | | | |

## Proxy line: nearest 0.5 (whole lines push)

### PTS — recalibration `shrink`, 578 pushes excluded of 16726

Fitted during the season: s 0.74–0.80, c +0.000–+0.013 (shrink+offset variant). 60–75% gate: **PASS** (60%–65% +0.8%, 65%–70% -0.7%, 70%–75% +1.6%).

| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred | Over share |
|---|---|---|---|---|---|---|
| 50%–55% | 6304 | 52.4% | 52.3% | 1.2% | -0.1% | 41% |
| 55%–60% | 5088 | 57.4% | 56.5% | 1.4% | -0.9% | 30% |
| 60%–65% | 3111 | 62.2% | 63.0% | 1.7% | +0.8% | 23% |
| 65%–70% | 1339 | 67.0% | 66.2% | 2.5% | -0.7% | 22% |
| 70%–75% | 306 | 70.0% | 71.6% | 5.1% | +1.6% | 25% |

Over/under split:

| Picks | n | Over: share / pred / hit | Under: share / pred / hit |
|---|---|---|---|
| all | 16148 | 32.4% / 56.2% / 55.8% | 67.6% / 58.0% / 57.9% |
| p>=55% | 9844 | 26.6% / 60.0% / 59.6% | 73.4% / 60.8% / 60.6% |
| p>=60% | 4756 | 22.5% / 64.1% / 64.6% | 77.5% / 64.1% / 64.4% |

Variants (walk-forward, evaluated season):

| Variant | Log loss | Gate | Over gap p≥60 | Under gap p≥60 | Over share p≥60 |
|---|---|---|---|---|---|
| raw | 0.6784 | FAIL | -3.2% | -3.0% | 24.1% |
| offset | 0.6784 | FAIL | -4.5% | -2.1% | 31.1% |
| shrink | 0.6767 | PASS | +0.6% | +0.4% | 22.5% |
| shrink+offset | 0.6769 | PASS | +0.1% | +0.4% | 24.8% |
| raw (no cap) | 0.6791 | | | | |

### REB — recalibration `offset`, 1317 pushes excluded of 16726

Fitted during the season: s 0.78–0.88, c -0.022–-0.018 (shrink+offset variant). 60–75% gate: **PASS** (60%–65% +0.3%, 65%–70% -1.4%, 70%–75% -0.2%).

| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred | Over share |
|---|---|---|---|---|---|---|
| 50%–55% | 4571 | 52.5% | 52.9% | 1.4% | +0.4% | 45% |
| 55%–60% | 3965 | 57.4% | 56.7% | 1.5% | -0.7% | 35% |
| 60%–65% | 3201 | 62.4% | 62.7% | 1.7% | +0.3% | 27% |
| 65%–70% | 2027 | 67.3% | 65.9% | 2.1% | -1.4% | 21% |
| 70%–75% | 1067 | 72.2% | 72.0% | 2.7% | -0.2% | 19% |
| 75%–100% | 578 | 78.5% | 76.6% | 3.4% | -1.8% | 17% |

Over/under split:

| Picks | n | Over: share / pred / hit | Under: share / pred / hit |
|---|---|---|---|
| all | 15409 | 32.7% / 57.9% / 57.6% | 67.3% / 61.1% / 60.9% |
| p>=55% | 10838 | 27.3% / 61.9% / 60.8% | 72.7% / 63.8% / 63.5% |
| p>=60% | 6873 | 23.0% / 65.9% / 63.5% | 77.0% / 67.0% / 67.1% |

Variants (walk-forward, evaluated season):

| Variant | Log loss | Gate | Over gap p≥60 | Under gap p≥60 | Over share p≥60 |
|---|---|---|---|---|---|
| raw | 0.6644 | PASS | -3.5% | +1.3% | 29.1% |
| offset | 0.6640 | PASS | -2.4% | +0.1% | 23.0% |
| shrink | 0.6649 | FAIL | -1.5% | +3.2% | 28.7% |
| shrink+offset | 0.6644 | FAIL | +2.2% | +2.2% | 18.0% |
| raw (no cap) | 0.6644 | | | | |

## Season start: prior-season history counts toward the 5-game minimum

First 21 days: 2153 projections, 1161 relying on last season (<5 games this season). TEAM_CHANGE 396, ROLE_CHANGE 505.

| Market | Group | n | Pred | Hit | n (p≥60%) | Pred | Hit |
|---|---|---|---|---|---|---|---|
| PTS | carried_history(<5 games this season) | 1161 | 57.6% | 60.1% | 348 | 64.0% | 75.9% |
| PTS | flagged | 781 | 57.5% | 58.3% | 225 | 64.3% | 69.3% |
| PTS | unflagged | 1372 | 57.6% | 59.2% | 414 | 64.1% | 69.3% |
| PTS | TEAM_CHANGE (season) | 778 | 57.3% | 59.1% | 219 | 63.7% | 69.4% |
| PTS | ROLE_CHANGE (season) | 686 | 57.7% | 60.8% | 220 | 64.0% | 72.7% |
| REB | carried_history(<5 games this season) | 1161 | 60.4% | 63.3% | 559 | 66.5% | 70.3% |
| REB | flagged | 781 | 60.0% | 62.5% | 362 | 66.3% | 68.8% |
| REB | unflagged | 1372 | 60.1% | 61.9% | 631 | 66.4% | 68.6% |
| REB | TEAM_CHANGE (season) | 778 | 59.9% | 63.5% | 347 | 66.6% | 71.2% |
| REB | ROLE_CHANGE (season) | 686 | 60.4% | 64.3% | 331 | 66.4% | 68.9% |

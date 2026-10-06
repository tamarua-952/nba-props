# Backtest calibration — 2025–26 regular season

**Calibration only, not edge.** No historical prop lines are available, so this checks whether the model's probabilities are honest, not whether they beat a bookmaker.

Player-games projected: 15170 (2025-10-30 to 2026-04-12). Walk-forward: each projection uses only games on earlier dates.

Proxy line = player's last-10 average floored to x.5. Real book lines are sharper than this, so results at the proxy line say nothing about edge.

## PTS

Projection MAE 5.18 (last-10 average: 5.25); bias +0.19; minutes MAE 4.4.

At the proxy line (n=15170): Brier 0.2444 vs naive last-10 0.2508 vs coin 0.25; log loss 0.6820 vs 0.6949.

### Pick-side calibration at the proxy line

Model's probability for the side it favours vs how often that side won. This is the table that matters for picks (spec needs > ~53.5% at $1.87).

| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred |
|---|---|---|---|---|---|
| 50%–55% | 4919 | 52.5% | 51.4% | 1.4% | -1.1% |
| 55%–60% | 4337 | 57.4% | 55.2% | 1.5% | -2.3% |
| 60%–65% | 3103 | 62.3% | 59.3% | 1.7% | -3.0% |
| 65%–70% | 1731 | 67.2% | 62.3% | 2.3% | -4.9% |
| 70%–75% | 813 | 72.1% | 65.6% | 3.3% | -6.5% |
| 75%–100% | 267 | 77.7% | 70.4% | 5.5% | -7.3% |

### P(over) reliability, all grid lines

| P(over) | n | Mean pred | Hit rate | ±95% | Hit − pred |
|---|---|---|---|---|---|
| 0%–10% | 2 | 8.3% | 0.0% | 0.0% | -8.3% |
| 10%–20% | 2287 | 17.7% | 19.9% | 1.6% | +2.2% |
| 20%–30% | 14555 | 25.4% | 26.5% | 0.7% | +1.1% |
| 30%–40% | 14552 | 34.3% | 34.8% | 0.8% | +0.5% |
| 40%–50% | 14354 | 44.4% | 46.3% | 0.8% | +1.9% |
| 50%–60% | 13059 | 55.7% | 58.4% | 0.8% | +2.7% |
| 60%–70% | 10616 | 65.3% | 67.7% | 0.9% | +2.4% |
| 70%–80% | 5448 | 73.7% | 74.1% | 1.2% | +0.4% |
| 80%–90% | 903 | 83.5% | 82.5% | 2.5% | -1.0% |
| 90%–100% | 66 | 91.8% | 84.8% | 8.7% | -6.9% |

### Segments (proxy line)

| Segment | n | Pred over | Hit over | Mean − actual |
|---|---|---|---|---|
| teammate_regular_out | 7464 | 47.8% | 50.2% | +0.13 |
| no_regular_out | 7706 | 42.4% | 43.8% | +0.25 |
| back_to_back | 2638 | 44.6% | 48.3% | -0.19 |

| Month | n | Pred over | Hit over |
|---|---|---|---|
| 2025-10 | 59 | 54.7% | 44.1% |
| 2025-11 | 2746 | 47.0% | 47.6% |
| 2025-12 | 2624 | 45.0% | 44.8% |
| 2026-01 | 3108 | 45.3% | 46.1% |
| 2026-02 | 2199 | 44.7% | 48.7% |
| 2026-03 | 3224 | 43.7% | 47.0% |
| 2026-04 | 1210 | 43.9% | 49.2% |

## REB

Projection MAE 2.02 (last-10 average: 2.06); bias +0.09; minutes MAE 4.4.

At the proxy line (n=15170): Brier 0.2390 vs naive last-10 0.2468 vs coin 0.25; log loss 0.6705 vs 0.6868.

### Pick-side calibration at the proxy line

Model's probability for the side it favours vs how often that side won. This is the table that matters for picks (spec needs > ~53.5% at $1.87).

| Model prob | n | Mean pred | Hit rate | ±95% | Hit − pred |
|---|---|---|---|---|---|
| 50%–55% | 5041 | 52.5% | 51.4% | 1.4% | -1.1% |
| 55%–60% | 4127 | 57.4% | 55.3% | 1.5% | -2.1% |
| 60%–65% | 3086 | 62.4% | 62.2% | 1.7% | -0.1% |
| 65%–70% | 1796 | 67.2% | 66.3% | 2.2% | -0.9% |
| 70%–75% | 790 | 72.1% | 71.6% | 3.1% | -0.5% |
| 75%–100% | 330 | 78.3% | 77.6% | 4.5% | -0.7% |

### P(over) reliability, all grid lines

| P(over) | n | Mean pred | Hit rate | ±95% | Hit − pred |
|---|---|---|---|---|---|
| 0%–10% | 542 | 8.3% | 10.0% | 2.5% | +1.7% |
| 10%–20% | 7460 | 16.1% | 16.4% | 0.8% | +0.3% |
| 20%–30% | 13054 | 25.1% | 24.1% | 0.7% | -0.9% |
| 30%–40% | 11418 | 34.8% | 33.4% | 0.9% | -1.5% |
| 40%–50% | 10168 | 45.0% | 44.9% | 1.0% | -0.1% |
| 50%–60% | 9352 | 54.9% | 54.5% | 1.0% | -0.5% |
| 60%–70% | 9530 | 65.0% | 65.1% | 1.0% | +0.1% |
| 70%–80% | 8176 | 74.7% | 74.5% | 0.9% | -0.2% |
| 80%–90% | 4717 | 84.4% | 85.0% | 1.0% | +0.6% |
| 90%–100% | 987 | 91.9% | 92.5% | 1.6% | +0.6% |

### Segments (proxy line)

| Segment | n | Pred over | Hit over | Mean − actual |
|---|---|---|---|---|
| teammate_regular_out | 7464 | 48.0% | 46.9% | +0.12 |
| no_regular_out | 7706 | 43.6% | 44.0% | +0.06 |
| back_to_back | 2638 | 45.3% | 45.8% | +0.06 |

| Month | n | Pred over | Hit over |
|---|---|---|---|
| 2025-10 | 59 | 49.3% | 42.4% |
| 2025-11 | 2746 | 47.2% | 47.4% |
| 2025-12 | 2624 | 45.7% | 46.1% |
| 2026-01 | 3108 | 45.2% | 45.6% |
| 2026-02 | 2199 | 45.5% | 43.6% |
| 2026-03 | 3224 | 45.3% | 44.4% |
| 2026-04 | 1210 | 45.6% | 45.4% |

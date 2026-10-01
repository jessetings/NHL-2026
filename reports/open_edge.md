# Opening-line test (2026-01-17+): does the model predict line movement and beat the OPEN price?

## 1. Line movement toward the model

slope = Δp(open→close) per unit of (model − open). 0 = market ignores the model; 1 = market moves all the way.

| Model | Stat | n | corr(edge, move) | slope | t-stat | mean |move| |
|---|---|---|---|---|---|---|
| v1 | assists | 20802 | +0.169 | +0.0496 | +24.7 | 0.0063 |
| v1 | goals+assists | 20864 | +0.158 | +0.0511 | +23.2 | 0.0077 |
| v1 | points | 9517 | +0.244 | +0.0863 | +24.6 | 0.0080 |
| v1 | shots_onGoal | 22522 | +0.275 | +0.1083 | +42.9 | 0.0129 |
| v2 | assists | 17444 | +0.209 | +0.0736 | +28.2 | 0.0059 |
| v2 | goals+assists | 17477 | +0.179 | +0.0627 | +24.1 | 0.0072 |
| v2 | points | 8398 | +0.236 | +0.0969 | +22.2 | 0.0077 |
| v2 | shots_onGoal | 18818 | +0.250 | +0.0925 | +35.3 | 0.0118 |

## 2. Bet at the OPEN price when model edge ≥ threshold (flat 1u; graded on results)

| Model | Stat | Side | Thr | n | hit | ROI | ±2se | avg CLV (pts) |
|---|---|---|---|---|---|---|---|---|
| v1 | assists | over | 3% | 787 | 0.314 | -1.0% | 10.9% | +0.75 |
| v1 | assists | over | 6% | 183 | 0.333 | +7.8% | 23.6% | +1.08 |
| v1 | assists | under | 3% | 1049 | 0.638 | -3.0% | 4.7% | +0.05 |
| v1 | assists | under | 6% | 302 | 0.675 | +4.1% | 8.8% | +0.09 |
| v1 | goals+assists | over | 3% | 1073 | 0.417 | -0.6% | 7.5% | +0.64 |
| v1 | goals+assists | over | 6% | 287 | 0.408 | +2.2% | 15.2% | +1.10 |
| v1 | goals+assists | under | 3% | 888 | 0.521 | -6.6% | 6.2% | +0.05 |
| v1 | goals+assists | under | 6% | 258 | 0.531 | -4.7% | 11.5% | +0.15 |
| v1 | points | over | 3% | 224 | 0.286 | -11.1% | 19.1% | +0.72 |
| v1 | points | over | 6% | 56 | 0.268 | -16.2% | 37.6% | +1.38 |
| v1 | points | under | 3% | 64 | 0.703 | +2.0% | 17.0% | +1.15 |
| v1 | shots_onGoal | over | 3% | 1182 | 0.470 | -6.0% | 5.9% | +1.16 |
| v1 | shots_onGoal | over | 6% | 360 | 0.469 | -3.8% | 11.0% | +1.69 |
| v1 | shots_onGoal | under | 3% | 2088 | 0.531 | +3.4% | 4.3% | +0.79 |
| v1 | shots_onGoal | under | 6% | 799 | 0.531 | +6.1% | 7.2% | +1.11 |
| v2 | assists | over | 3% | 211 | 0.237 | -22.0% | 19.9% | +0.92 |
| v2 | assists | over | 6% | 31 | 0.226 | -30.0% | 49.2% | +1.74 |
| v2 | assists | under | 3% | 817 | 0.569 | -3.9% | 6.1% | +0.12 |
| v2 | assists | under | 6% | 181 | 0.597 | +5.8% | 13.5% | +0.19 |
| v2 | goals+assists | over | 3% | 427 | 0.410 | -6.0% | 11.2% | +0.87 |
| v2 | goals+assists | over | 6% | 84 | 0.369 | -10.0% | 26.5% | +1.40 |
| v2 | goals+assists | under | 3% | 890 | 0.520 | -3.0% | 6.5% | +0.11 |
| v2 | goals+assists | under | 6% | 213 | 0.498 | -9.9% | 12.9% | +0.26 |
| v2 | points | over | 3% | 82 | 0.268 | -8.9% | 33.9% | +0.99 |
| v2 | points | under | 3% | 48 | 0.604 | -2.9% | 23.2% | +1.33 |
| v2 | shots_onGoal | over | 3% | 218 | 0.495 | -1.5% | 13.7% | +2.09 |
| v2 | shots_onGoal | over | 6% | 39 | 0.385 | -22.9% | 31.8% | +3.92 |
| v2 | shots_onGoal | under | 3% | 3958 | 0.531 | +2.2% | 3.1% | +0.37 |
| v2 | shots_onGoal | under | 6% | 1946 | 0.536 | +4.5% | 4.5% | +0.52 |

## 3. Live rule: SOG unders, level-corrected v2 edge (DK/FD open prices)

| Edge ≥ | n | ROI | ±2se | CLV (pts) |
|---|---|---|---|---|
| all (blanket) | 11376 | -2.1% | 1.8% | +0.07 |
| 0% | 3025 | +2.0% | 3.6% | +0.35 |
| 2% | 1775 | +4.8% | 4.7% | +0.42 |
| 4% | 925 | +4.0% | 6.6% | +0.51 |
| 6% | 439 | +9.7% | 9.5% | +0.71 |
# Opening-line test (2026-01-17+): does the model predict line movement and beat the OPEN price?

## 1. Line movement toward the model

slope = Δp(open→close) per unit of (model − open). 0 = market ignores the model; 1 = market moves all the way.

| Model | Stat | n | corr(edge, move) | slope | t-stat | mean |move| |
|---|---|---|---|---|---|---|
| v1 | assists | 20802 | +0.169 | +0.0496 | +24.7 | 0.0063 |
| v1 | goals+assists | 20864 | +0.158 | +0.0511 | +23.2 | 0.0077 |
| v1 | points | 9517 | +0.244 | +0.0863 | +24.6 | 0.0080 |
| v1 | shots_onGoal | 22522 | +0.275 | +0.1083 | +42.9 | 0.0129 |
| v2 | assists | 17444 | +0.206 | +0.0725 | +27.8 | 0.0059 |
| v2 | goals+assists | 17477 | +0.168 | +0.0589 | +22.6 | 0.0072 |
| v2 | points | 8398 | +0.220 | +0.0891 | +20.7 | 0.0077 |
| v2 | shots_onGoal | 18818 | +0.249 | +0.0926 | +35.3 | 0.0118 |

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
| v2 | assists | over | 3% | 210 | 0.252 | -17.6% | 20.2% | +0.97 |
| v2 | assists | over | 6% | 30 | 0.167 | -42.3% | 48.8% | +1.80 |
| v2 | assists | under | 3% | 829 | 0.577 | -3.2% | 6.0% | +0.12 |
| v2 | assists | under | 6% | 178 | 0.601 | +7.4% | 13.7% | +0.21 |
| v2 | goals+assists | over | 3% | 420 | 0.417 | -5.0% | 11.3% | +0.81 |
| v2 | goals+assists | over | 6% | 89 | 0.348 | -15.6% | 25.2% | +1.40 |
| v2 | goals+assists | under | 3% | 884 | 0.508 | -6.4% | 6.4% | +0.11 |
| v2 | goals+assists | under | 6% | 200 | 0.540 | -3.3% | 13.1% | +0.25 |
| v2 | points | over | 3% | 83 | 0.265 | -10.9% | 33.3% | +0.91 |
| v2 | points | under | 3% | 54 | 0.704 | +11.0% | 20.1% | +0.99 |
| v2 | shots_onGoal | over | 3% | 222 | 0.486 | -2.7% | 13.7% | +2.11 |
| v2 | shots_onGoal | over | 6% | 36 | 0.389 | -21.4% | 33.4% | +4.00 |
| v2 | shots_onGoal | under | 3% | 3933 | 0.529 | +1.9% | 3.1% | +0.36 |
| v2 | shots_onGoal | under | 6% | 1912 | 0.538 | +5.1% | 4.5% | +0.52 |
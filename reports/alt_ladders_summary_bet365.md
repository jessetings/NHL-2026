# Alt ladders: simulator vs bet365 pregame (≤90 min before puck drop, 2026-01-17+)

616 games, 21701 prices. Flat 1u per qualifying price, graded on final scores (OT/SO winner +1).

## By market

| kind | n prices | book ROI (all) | EV>3%: n | ROI | ±2se | EV>8%: n | ROI | ±2se |
|---|---|---|---|---|---|---|---|---|
| spread | 6778 | -20.7% | 26 | +38.8% | 76.6% | 2 | -100.0% | 0.0% |
| team_total | 5154 | -11.2% | 4 | +61.2% | 189.4% | 0 | +nan% | nan% |
| total | 9769 | -14.9% | 10 | -26.8% | 61.2% | 0 | +nan% | nan% |

## By price band (all markets)

| price_band | n prices | book ROI (all) | EV>3%: n | ROI | ±2se | EV>8%: n | ROI | ±2se |
|---|---|---|---|---|---|---|---|---|
| <-300 | 8870 | -3.5% | 0 | +nan% | nan% | 0 | +nan% | nan% |
| -300..-150 | 1531 | -2.8% | 1 | +37.0% | nan% | 0 | +nan% | nan% |
| -150..+100 | 446 | -6.5% | 5 | -26.1% | 90.5% | 0 | +nan% | nan% |
| +100..+250 | 2343 | -12.5% | 9 | -43.9% | 74.8% | 0 | +nan% | nan% |
| +250..+600 | 4828 | -14.8% | 24 | +65.6% | 82.1% | 2 | -100.0% | 0.0% |
| >+600 | 3683 | -55.6% | 1 | -100.0% | nan% | 0 | +nan% | nan% |

## By side

| sd | n prices | book ROI (all) | EV>3%: n | ROI | ±2se | EV>8%: n | ROI | ±2se |
|---|---|---|---|---|---|---|---|---|
| spread/away | 3343 | -14.0% | 12 | +65.8% | 118.8% | 0 | +nan% | nan% |
| spread/home | 3435 | -27.3% | 14 | +15.7% | 101.8% | 2 | -100.0% | 0.0% |
| team_total/over | 2577 | -7.2% | 3 | -6.7% | 186.7% | 0 | +nan% | nan% |
| team_total/under | 2577 | -15.2% | 1 | +265.0% | nan% | 0 | +nan% | nan% |
| total/over | 4827 | -13.8% | 2 | -6.9% | 186.2% | 0 | +nan% | nan% |
| total/under | 4942 | -16.0% | 8 | -31.8% | 68.6% | 0 | +nan% | nan% |

## Alt totals by line parity

| parity | n prices | book ROI (all) | EV>3%: n | ROI | ±2se | EV>8%: n | ROI | ±2se |
|---|---|---|---|---|---|---|---|---|
| line k.5, k even (over needs odd+) | 4951 | -15.1% | 5 | -26.1% | 90.5% | 0 | +nan% | nan% |
| line k.5, k odd (over needs even+) | 4818 | -14.7% | 5 | -27.6% | 92.9% | 0 | +nan% | nan% |

## Calibration (no-push rows)

| Bucket (sim p) | n | actual | sim | book implied (with vig) |
|---|---|---|---|---|
| (0.0, 0.05] | 1572 | 0.019 | 0.029 | 0.071 |
| (0.05, 0.1] | 1767 | 0.066 | 0.073 | 0.113 |
| (0.1, 0.2] | 3401 | 0.146 | 0.150 | 0.183 |
| (0.2, 0.35] | 3142 | 0.249 | 0.253 | 0.286 |
| (0.35, 0.5] | 1195 | 0.409 | 0.410 | 0.444 |
| (0.5, 0.65] | 1169 | 0.593 | 0.590 | 0.631 |
| (0.65, 0.8] | 3142 | 0.751 | 0.747 | 0.786 |
| (0.8, 0.9] | 3401 | 0.854 | 0.850 | 0.886 |
| (0.9, 0.95] | 1767 | 0.934 | 0.927 | 0.954 |
| (0.95, 1.0] | 1137 | 0.975 | 0.967 | 0.986 |
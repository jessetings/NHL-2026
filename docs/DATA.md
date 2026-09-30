# Data Catalog

Everything is pulled by the scripts in `src/ingest/`. Each fetch is **resumable**: files already on disk are skipped.

- Raw data goes to `data/raw/` and curated Parquet to `data/curated/`. Both are git-ignored because of size.
- Query the curated tables with DuckDB, e.g. `duckdb -c "select * from 'data/curated/nhl_skater_game.parquet' limit 5"`.

## Rebuild from scratch (about 25-40 minutes)
```bash
export PYTHONPATH=src/ingest          # plus SGO_API_KEY in env or .env
python src/ingest/moneypuck.py        # ~300 MB, 2 min
python src/ingest/nhl.py              # schedules, boxscores, pbp, shifts, officials, player careers
python src/ingest/sgo_history.py      # SGO NHL odds + results, weekly windows since 2024-09-01
python src/ingest/sgo_history.py --open-close   # re-pull 2025-12-14+ with per-book open/close odds
python src/ingest/snapshot.py --interval 300    # LIVE: run on game days (alt lines + movement; no history exists)
python src/ingest/dailyfaceoff.py     # snapshot NOW (run on every build; there is no history)
python src/ingest/curate.py all       # raw -> data/curated/*.parquet
python src/ingest/idmap.py            # SGO <-> NHL id maps
```
To refresh the SGO history for recent days, first delete the newest `data/raw/sgo_history/*.json.gz`. That window may have been fetched before its games finished.

## Scope decisions
| Source | Window | Why |
|---|---|---|
| MoneyPuck season summaries (skaters, goalies, teams, lines; regular and playoffs) | 2015-16 → now | Career context, aging curves, priors |
| MoneyPuck shot-level (xG, shot context) | 2022-23 → now | Recent enough for current game style |
| MoneyPuck team game-by-game | 2015-16 → now | Team form, rest, pace |
| NHL boxscores (player-game TOI, SOG, G, A, hits, blocks, PPG, shifts) | 2022-23 → now | Game logs for rolling features and backtests |
| NHL play-by-play, shift charts, officials | 2023-24 → now | Strength states, PP/PK TOI, penalties, referees, blocked shots |
| NHL player landing pages (bio plus **full career season-by-season, all leagues**) | Every player who dressed since 2022-23 | Career stats, junior/AHL/European history for rookies |
| SportsGameOdds odds + results | 2024-09 → now | **SGO NHL history starts with the 2024-25 season.** Nothing earlier exists. |
| DailyFaceoff lines, PP units, goalies, injuries | Snapshots from 2026-09-30 onward | No history available, so we archive going forward |

## Curated tables (`data/curated/`)
| Table | Grain | Notes |
|---|---|---|
| `mp_skaters_seasons`, `mp_goalies_seasons`, `mp_teams_seasons`, `mp_lines_seasons` | season × situation (all / 5on5 / 5on4 / 4on5 / other) × player/team/line | `game_type` = regular or playoffs |
| `mp_shots_<season>` | one row per unblocked shot attempt | xGoal, shooter, goalie, coordinates, rebound/rush flags, strength |
| `mp_team_games` | team × game × situation | 2015+ |
| `mp_players` | MoneyPuck player bio lookup | |
| `nhl_games` | game | Scores, start time, venue, OT/SO flag |
| `nhl_skater_game`, `nhl_goalie_game` | player × game | TOI seconds, SOG, G, A, PPG, hits, blocks, shifts; goalie saves by strength, starter flag |
| `nhl_pbp_<season>` | event | situationCode, coordinates, shooter/goalie/penalty ids, score |
| `nhl_shifts_<season>` | shift | Combine with pbp situationCode to get EV/PP/PK TOI |
| `nhl_officials` | game | Referees and linesmen |
| `nhl_players`, `nhl_player_seasons` | player; player × season × league | Career stats incl. AHL/CHL/Europe |
| `sgo_events` | event | SGO eventID, teams, status |
| `sgo_odds` | event × oddID × book × line | Per-book odds and line, `updated`, `pregame` flag, SGO open/close/fair fields |
| `sgo_results` | event × period × entity × stat | Box-score results per player and team (grading) |
| `map_sgo_event`, `map_sgo_player` | id maps | SGO eventID → NHL game_id; SGO playerID → NHL playerId |

## SGO history facts (M0 audit, see docs/PLAN_v3.md)
- Per-book historical `odds` = last tick, usually **in-game**. Do not use as bet-time prices.
- Per-book `book_open_odds` / `book_close_odds` (close = price at puck drop) are available **from 2026-01-17** (pulled with `--open-close`).
- Alt lines never have open/close. Use our own `data/raw/snapshots/` archive (`src/ingest/snapshot.py`).
- Consensus `close_fair_odds` covers ~95-100% of main-line contracts from 2025-02.

## Known caveats
- **SGO per-book historical `odds` can be in-game updates.** Filter with `pregame = true` (`updated < startsAt`). For closing lines prefer SGO's `close_*` consensus fields.
- **Early 2024-25 SGO coverage is thin** (few DK/FD prop rows). Check coverage per book and month before backtesting.
- **MoneyPuck season summaries are end-of-season aggregates**, so they leak into any backtest of that season. Use game-level tables (`nhl_skater_game`, shots, pbp) to build as-of features.
- **Historical lineups and PP units are not available pre-2026** except as actual deployment (shifts) = hindsight. Estimate the degradation versus projected lineups.

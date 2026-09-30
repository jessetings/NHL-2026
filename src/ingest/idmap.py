"""Map SGO playerIDs (e.g. SIDNEY_CROSBY_1_NHL) and team IDs to NHL playerId / team abbrev.

Match on normalized full name within the same team; fall back to unique name league-wide.
Writes data/curated/map_sgo_player.parquet and map_sgo_event.parquet (SGO eventID -> NHL game_id).
"""
import re
import unicodedata

import duckdb
import pandas as pd

CUR = "data/curated"

SGO_TEAM = {
    "ANAHEIM_DUCKS_NHL": "ANA", "ARIZONA_COYOTES_NHL": "ARI", "BOSTON_BRUINS_NHL": "BOS", "BUFFALO_SABRES_NHL": "BUF",
    "CALGARY_FLAMES_NHL": "CGY", "CAROLINA_HURRICANES_NHL": "CAR", "CHICAGO_BLACKHAWKS_NHL": "CHI",
    "COLORADO_AVALANCHE_NHL": "COL", "COLUMBUS_BLUE_JACKETS_NHL": "CBJ", "DALLAS_STARS_NHL": "DAL",
    "DETROIT_RED_WINGS_NHL": "DET", "EDMONTON_OILERS_NHL": "EDM", "FLORIDA_PANTHERS_NHL": "FLA",
    "LOS_ANGELES_KINGS_NHL": "LAK", "MINNESOTA_WILD_NHL": "MIN", "MONTREAL_CANADIENS_NHL": "MTL",
    "NASHVILLE_PREDATORS_NHL": "NSH", "NEW_JERSEY_DEVILS_NHL": "NJD", "NEW_YORK_ISLANDERS_NHL": "NYI",
    "NEW_YORK_RANGERS_NHL": "NYR", "OTTAWA_SENATORS_NHL": "OTT", "PHILADELPHIA_FLYERS_NHL": "PHI",
    "PITTSBURGH_PENGUINS_NHL": "PIT", "SAN_JOSE_SHARKS_NHL": "SJS", "SEATTLE_KRAKEN_NHL": "SEA",
    "ST_LOUIS_BLUES_NHL": "STL", "TAMPA_BAY_LIGHTNING_NHL": "TBL", "TORONTO_MAPLE_LEAFS_NHL": "TOR",
    "UTAH_HOCKEY_CLUB_NHL": "UTA", "UTAH_MAMMOTH_NHL": "UTA", "VANCOUVER_CANUCKS_NHL": "VAN",
    "VEGAS_GOLDEN_KNIGHTS_NHL": "VGK", "WASHINGTON_CAPITALS_NHL": "WSH", "WINNIPEG_JETS_NHL": "WPG"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def main():
    con = duckdb.connect()
    ev = con.execute(f"select * from '{CUR}/sgo_events.parquet'").df()
    ev["home_abbr"] = ev.home.map(SGO_TEAM)
    ev["away_abbr"] = ev.away.map(SGO_TEAM)
    ev["date_utc"] = pd.to_datetime(ev.startsAt, utc=True)
    games = con.execute(f"select game_id, date, start_utc, home, away, game_type from '{CUR}/nhl_games.parquet'").df()
    games["start"] = pd.to_datetime(games.start_utc, utc=True)
    m = ev.merge(games, left_on=["home_abbr", "away_abbr"], right_on=["home", "away"], suffixes=("", "_nhl"))
    m = m[(m.start - m.date_utc).abs() < pd.Timedelta(hours=12)]
    evmap = m[["eventID", "game_id", "game_type", "date"]].drop_duplicates("eventID")
    evmap.to_parquet(f"{CUR}/map_sgo_event.parquet", index=False)
    print("events mapped", len(evmap), "of", len(ev), "(unmapped are mostly preseason/future)")

    # SGO players with team per event
    sp = con.execute(f"""select r.eventID, r.entity as sgo_player, r.value as sgo_team
                         from '{CUR}/sgo_results.parquet' r where r.period='_meta'""").df()
    names = con.execute(f"""select distinct entity, player from '{CUR}/sgo_odds.parquet' where player is not null""").df()
    sp = sp.merge(names, left_on="sgo_player", right_on="entity", how="left").merge(evmap, on="eventID")
    sp["team"] = sp.sgo_team.map(SGO_TEAM)
    sp["key"] = sp.player.fillna(sp.sgo_player.str.replace(r"_\d+_NHL$", "", regex=True).str.replace("_", " "))\
        .map(norm)
    # NHL: who dressed for which team in each game (full names from player landing pages)
    pl = con.execute(f"""select s.game_id, s.playerId as player_id, s.team, p.first, p.last
                         from (select game_id, playerId, team from '{CUR}/nhl_skater_game.parquet'
                               union all select game_id, playerId, team from '{CUR}/nhl_goalie_game.parquet') s
                         left join '{CUR}/nhl_players.parquet' p on p.player_id = s.playerId""").df()
    pl["key"] = (pl["first"].fillna("") + pl["last"].fillna("")).map(norm)
    j = sp.merge(pl, on=["game_id", "team", "key"], how="left")
    mp = j.dropna(subset=["player_id"]).groupby("sgo_player").player_id.agg(lambda s: s.mode().iloc[0]).reset_index()
    # fallback: last-name + team match for nicknames (e.g. Mitch/Mitchell)
    miss = sp[~sp.sgo_player.isin(mp.sgo_player)].drop_duplicates("sgo_player")
    pl["last_key"] = pl["last"].fillna("").map(norm)
    miss = miss.assign(last_key=miss.key.str[-8:])
    fb = []
    for r in miss.itertuples():
        cand = pl[(pl.game_id == r.game_id) & (pl.team == r.team)]
        cand = cand[cand.last_key.map(lambda k: len(k) > 2 and r.key.endswith(k))]
        if cand.player_id.nunique() == 1:
            fb.append((r.sgo_player, int(cand.player_id.iloc[0])))
    mp = pd.concat([mp, pd.DataFrame(fb, columns=["sgo_player", "player_id"])], ignore_index=True)
    mp["player_id"] = mp.player_id.astype("int64")
    mp.to_parquet(f"{CUR}/map_sgo_player.parquet", index=False)
    total = sp.sgo_player.nunique()
    print(f"players mapped {len(mp)} of {total} ({len(mp) / total:.1%}); fallback {len(fb)}")
    unm = sp[~sp.sgo_player.isin(mp.sgo_player)].sgo_player.value_counts().head(15)
    print("top unmapped:", unm.to_dict())


if __name__ == "__main__":
    main()

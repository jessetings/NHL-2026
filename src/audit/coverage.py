"""M0 coverage audit: what SGO history actually contains, before fixing any backtest window.

Outputs reports/coverage_*.csv and prints a summary.
"""
import os

import duckdb

CUR = "data/curated"
OUT = "reports"
BOOKS = ("draftkings", "fanduel", "pinnacle")

FAMILY = """case
  when stat='points' and entity in ('home','away','all') and bt='ml' then 'ML'
  when stat='points' and entity in ('home','away','all') and bt='sp' then 'PL'
  when stat='points' and entity='all' and bt='ou' then 'TOTAL'
  when stat='points' and entity in ('home','away') and bt='ou' then 'TEAM_TOTAL'
  when stat='shots_onGoal' then 'P_SOG'
  when stat='points' then 'P_GOALS'
  when stat='assists' then 'P_AST'
  when stat='goals+assists' then 'P_PTS'
  when stat='goalie_saves' then 'G_SAVES'
  else 'OTHER' end"""


def main():
    os.makedirs(OUT, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"create view o as select *, {FAMILY} fam, strftime(cast(startsAt as timestamp), '%Y-%m') ym "
                f"from '{CUR}/sgo_odds/*.parquet' where period='game'")
    con.execute(f"create view m as select * from '{CUR}/map_sgo_event.parquet'")
    # 1. events per month, and how many map to regular/playoff NHL games
    ev = con.execute(f"""
        select strftime(cast(e.startsAt as timestamp), '%Y-%m') ym, count(*) events,
               count(m.game_id) mapped, sum(case when m.game_type=2 then 1 else 0 end) reg,
               sum(case when m.game_type=3 then 1 else 0 end) playoff
        from '{CUR}/sgo_events/*.parquet' e left join m using(eventID) group by 1 order by 1""").df()
    ev.to_csv(f"{OUT}/coverage_events_by_month.csv", index=False)
    print(ev.to_string(index=False))

    # 2. month x book x family: contracts, pregame share, alt share, two-sided share
    cov = con.execute(f"""
        with b as (
          select ym, book, fam, eventID, oddID, line, alt, pregame, side from o
          where book in {BOOKS} and eventID in (select eventID from m where game_type in (2,3))),
        two as (
          select ym, book, fam, eventID, replace(replace(oddID,'-over',''),'-under','') k, line,
                 count(distinct side) ns
          from b where fam not in ('ML','PL') group by all)
        select b.ym, b.book, b.fam,
               count(distinct b.eventID) events,
               count(*) n_rows,
               round(avg(case when b.pregame then 1 else 0 end), 3) pregame_share,
               round(avg(case when b.alt then 1 else 0 end), 3) alt_share,
               (select round(avg(case when ns=2 then 1 else 0 end),3) from two t
                 where t.ym=b.ym and t.book=b.book and t.fam=b.fam) two_sided_share
        from b group by 1,2,3 order by 3,2,1""").df()
    cov.to_csv(f"{OUT}/coverage_month_book_family.csv", index=False)
    piv = cov.pivot_table(index=["fam", "book"], columns="ym", values="events", aggfunc="sum").fillna(0).astype(int)
    print("\nEvents with >=1 priced contract, by family x book x month:")
    print(piv.to_string())
    piv2 = cov.pivot_table(index=["fam", "book"], columns="ym", values="pregame_share", aggfunc="mean").round(2)
    print("\nPregame share (updated < startsAt):")
    print(piv2.to_string())

    # 3. close / fair fields availability
    cl = con.execute(f"""
        select ym, fam, count(distinct oddID||eventID) contracts,
          round(avg(case when close_book_odds is not null then 1 else 0 end),3) has_close_book,
          round(avg(case when close_fair_odds is not null then 1 else 0 end),3) has_close_fair,
          round(avg(case when open_book_odds is not null then 1 else 0 end),3) has_open_book
        from o where eventID in (select eventID from m where game_type in (2,3)) group by 1,2 order by 2,1""").df()
    cl.to_csv(f"{OUT}/coverage_close_fields.csv", index=False)

    # 4. settlement coverage: player SOG results present for mapped games
    rs = con.execute(f"""
        select strftime(cast(e.startsAt as timestamp), '%Y-%m') ym, count(distinct r.eventID) events_with_player_sog
        from '{CUR}/sgo_results/*.parquet' r join '{CUR}/sgo_events/*.parquet' e using(eventID)
        where r.period='game' and r.stat='shots_onGoal' and r.entity not in ('home','away') group by 1 order by 1""").df()
    rs.to_csv(f"{OUT}/coverage_settlement.csv", index=False)
    print("\nSettlement (player SOG results) by month:")
    print(rs.to_string(index=False))

    # 5. exact-rung depth for SOG at DK/FD (pregame only)
    rung = con.execute(f"""
        select book, line, count(*) n from o
        where fam='P_SOG' and side='over' and pregame and book in ('draftkings','fanduel')
          and eventID in (select eventID from m where game_type=2)
        group by 1,2 order by 1,2""").df()
    rung.to_csv(f"{OUT}/coverage_sog_rungs.csv", index=False)
    print("\nPregame SOG over rows by book x line:")
    print(rung.pivot_table(index="line", columns="book", values="n").fillna(0).astype(int).to_string())


if __name__ == "__main__":
    main()

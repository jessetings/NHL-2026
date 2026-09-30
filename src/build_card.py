"""Turn props_all.csv into a tiered card with stakes, ceilings and correlation caps.

Tiers (ledger rules, made explicit):
  CORE : model_p >= implied + 2pt AND market_p >= implied + 1pt AND EV >= 5% AND implied >= 18%
  LEAN : blended edge >= 1.5pt, EV >= 3%, one source may be neutral; implied >= 18%
Stakes: CORE 0.5u, LEAN 0.25u; max 1u per player, 2u per game.
"""
import sys
from datetime import datetime, timezone

import pandas as pd

OUT = "cards/2026-09-30"
MKT_NAME = {"SOG": "shots on goal", "PTS": "points", "A": "assists", "G": "goals"}


def label(r):
    k = int(r.line + 0.5)
    return f"{r.player} {'over' if r.side == 'over' else 'under'} {r.line:g} {MKT_NAME[r.market]}" + \
        (f" ({k}+)" if r.side == "over" else "")


def main():
    pr = pd.read_csv(f"{OUT}/props_all.csv")
    pr = pr[pr.mkt_p.notna() & (pr.implied >= 0.18) & (pr.decision != "data-check")]
    pr["m_edge"] = pr.model_p - pr.implied
    pr["k_edge"] = pr.mkt_p - pr.implied
    core = (pr.m_edge >= 0.02) & (pr.k_edge >= 0.01) & (pr.ev >= 0.05)
    lean = ~core & (pr.edge >= 0.015) & (pr.ev >= 0.03)
    pr["tier"] = None
    pr.loc[core, "tier"] = "CORE"
    pr.loc[lean, "tier"] = "LEAN"
    pr = pr[pr.tier.notna()].sort_values(["tier", "ev"], ascending=[True, False])
    # one selection per player+market (best EV rung/book), then caps
    pr = pr.drop_duplicates(["player", "market"])
    pr["stake"] = pr.tier.map({"CORE": 0.5, "LEAN": 0.25})
    pr["stake"] = pr.groupby("player").stake.transform(lambda s: s * min(1, 1.0 / s.sum()))
    pr["stake"] = pr.groupby("game").stake.transform(lambda s: s * min(1, 2.0 / s.sum()))
    pr["pick"] = pr.apply(label, axis=1)
    pr["src"] = pr.apply(lambda r: "model+market" if r.m_edge >= 0.02 and r.k_edge >= 0.01
                         else ("market (price-shop)" if r.k_edge > r.m_edge else "model"), axis=1)
    cols = ["tier", "game", "pick", "role", "pp", "book", "odds", "implied", "model_p", "mkt_p", "blend_p",
            "ev", "ceiling", "stake", "src"]
    pr[cols].to_csv(f"{OUT}/card.csv", index=False)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"| {r.tier} | {r.game} | {r.pick} | {r.role}/{r.pp} | {r.book} {r.odds:+d} | "
             f"{r.implied:.1%} | {r.model_p:.1%} | {r.mkt_p:.1%} | {r.ev:+.1%} | {int(r.ceiling):+d} | {r.stake:.2f}u | {r.src} |"
             for r in pr.itertuples()]
    hdr = ("| Tier | Game | Pick | Role | Best price | Implied | Model | Market | EV | Ceiling | Stake | Basis |\n"
           "|---|---|---|---|---|---|---|---|---|---|---|---|")
    open(f"{OUT}/card_table.md", "w").write(f"_Generated {ts} from {pr.snapshot.iloc[0]}_\n\n{hdr}\n" + "\n".join(lines) + "\n")
    print(hdr)
    print("\n".join(lines))


if __name__ == "__main__":
    main()

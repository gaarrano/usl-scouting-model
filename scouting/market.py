"""
market.py — "is this a realistic target for a USL Championship club?"

Rule: if the club he plays for NOW is in a stronger league (list below — an editable judgment call), he must
not be an established starter there: he started fewer than MAX_START_SHARE of his team's matches in his latest
season with 8+ team matches. That drops the established starters of MLS and the strongest leagues in our data
(the players a USL club can't sign) and keeps the fringe ones, who do move: in our data 48 players went from
MLS straight to the USL Championship the following season (see arrivals()).
Everyone in the other leagues stays in; age, level and the other filters do the rest.
"""
import pandas as pd

USL = "United States · USL Championship"
STRONGER = {"United States · Major League Soccer", "Argentina · Liga Profesional de Fútbol",
            "Brazil · Serie B", "Colombia · Liga BetPlay", "England · League One"}
MAX_START_SHARE = 0.5


def arrivals(allrows):
    """Players who went from each league to the USL Championship the following season (context)."""
    r = allrows[allrows["minutes_all"] > 0].copy()
    r["s0"] = pd.to_numeric(r["season"].astype(str).str[:4], errors="coerce")
    r["lg"] = r["country"].astype(str) + " · " + r["league"].astype(str)
    r = r.sort_values(["player_id", "s0"])
    r["next_lg"] = r.groupby("player_id")["lg"].shift(-1)
    mv = r[(r["next_lg"] == USL) & (r["lg"] != USL)]
    return mv.groupby("lg")["player_id"].nunique().sort_values(ascending=False)


def realistic(cand):
    """Boolean mask over a fit.rank() candidate table (needs now_league, now_country, now_start_share)."""
    lg = cand["now_country"].astype(str) + " · " + cand["now_league"].astype(str)
    return ~(lg.isin(STRONGER) & cand["now_start_share"].fillna(0).ge(MAX_START_SHARE))


if __name__ == "__main__":
    from sm_features import player_seasons
    print(arrivals(player_seasons()).to_string())

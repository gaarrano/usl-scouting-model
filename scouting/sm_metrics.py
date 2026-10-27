"""
sm_metrics.py — shared definitions for the Sportmonks scouting analyses:
position groups, the per-90 / success-% features, and the possession adjustment.

Used by stability.py and translation.py (cb_fit.py keeps its own frozen v2 copy).
"""
import numpy as np
import pandas as pd

# Sportmonks detailed position -> our position group (goalkeepers left out on purpose)
POSITION_GROUPS = {
    "Centre Back": "CB",
    "Left Back": "FB", "Right Back": "FB", "Left Wing Back": "FB", "Right Wing Back": "FB",
    "Defensive Midfield": "CM", "Central Midfield": "CM",
    "Attacking Midfield": "AM", "Secondary Striker": "AM",
    "Left Wing": "W", "Right Wing": "W", "Left Midfield": "W", "Right Midfield": "W",
    "Centre Forward": "ST",
}
GROUP_LABEL = {"CB": "Centre-backs", "FB": "Full-backs", "CM": "Central/defensive midfielders",
               "AM": "Attacking midfielders", "W": "Wingers", "ST": "Strikers"}

# feature -> (label, kind). kind: 'p90' volume per 90, 'pct' success rate, 'adj' p90 adjusted for
# opponent possession (defensive volume), 'ratio' per-100-touches rate.
FEATURES = {
    "touches_p90": ("Touches/90", "p90"),
    "passes_p90": ("Passes/90", "p90"),
    "pass_pct": ("Pass completion %", "pct"),
    "long_p90": ("Long balls/90", "p90"),
    "long_pct": ("Long-ball completion %", "pct"),
    "key_passes_p90": ("Key passes/90", "p90"),
    "crosses_p90": ("Crosses/90", "p90"),
    "cross_pct": ("Cross completion %", "pct"),
    "dribbles_p90": ("Dribble attempts/90", "p90"),
    "dribble_pct": ("Dribble success %", "pct"),
    "shots_p90": ("Shots/90", "p90"),
    "sot_pct": ("Shots on target %", "pct"),
    "goals_p90": ("Goals/90", "p90"),
    "assists_p90": ("Assists/90", "p90"),
    "fouls_drawn_p90": ("Fouls drawn/90", "p90"),
    "loss_per100": ("Possession lost per 100 touches", "ratio"),
    "duels_p90": ("Duels/90 (poss-adj)", "adj"),
    "duel_pct": ("Duels won %", "pct"),
    "aerial_p90": ("Aerial duels/90 (poss-adj)", "adj"),
    "aerial_pct": ("Aerials won %", "pct"),
    "tackles_p90": ("Tackles/90 (poss-adj)", "adj"),
    "int_p90": ("Interceptions/90 (poss-adj)", "adj"),
    "clear_p90": ("Clearances/90 (poss-adj)", "adj"),
}
# denominators for the % features: a % on 3 attempts is noise, so it needs a minimum
PCT_BASE = {"pass_pct": "passes", "long_pct": "long_balls", "cross_pct": "crosses",
            "dribble_pct": "dribbles", "sot_pct": "shots", "duel_pct": "duels", "aerial_pct": "aerials"}
MIN_ATTEMPTS = 15


def season_start(s):
    return pd.to_numeric(s.astype(str).str[:4], errors="coerce")


def add_rates(df):
    """Per-90 and % features from the season totals produced by sm_features.py."""
    d = df.copy()
    m = d["minutes"] / 90
    safe = lambda x: x.replace(0, np.nan)                          # noqa: E731
    d["aerials"] = d["aerials_won"] + d["aerials_lost"]
    d["touches_p90"] = d["touches"] / m
    d["passes_p90"] = d["passes"] / m
    d["pass_pct"] = d["passes_acc"] / safe(d["passes"])
    d["long_p90"] = d["long_balls"] / m
    d["long_pct"] = d["long_balls_acc"] / safe(d["long_balls"])
    d["key_passes_p90"] = d["key_passes"] / m
    d["crosses_p90"] = d["crosses"] / m
    d["cross_pct"] = d["crosses_acc"] / safe(d["crosses"])
    d["dribbles_p90"] = d["dribbles"] / m
    d["dribble_pct"] = d["dribbles_won"] / safe(d["dribbles"])
    d["shots_p90"] = d["shots"] / m
    d["sot_pct"] = d["shots_on_target"] / safe(d["shots"])
    d["goals_p90"] = d["goals"] / m
    d["assists_p90"] = d["assists"] / m
    d["fouls_drawn_p90"] = d["fouls_drawn"] / m
    d["loss_per100"] = 100 * d["possession_lost"] / safe(d["touches"])
    d["duels_p90"] = d["duels"] / m
    d["duel_pct"] = d["duels_won"] / safe(d["duels"])
    d["aerial_p90"] = d["aerials"] / m
    d["aerial_pct"] = d["aerials_won"] / safe(d["aerials"])
    d["tackles_p90"] = d["tackles"] / m
    d["int_p90"] = d["interceptions"] / m
    d["clear_p90"] = d["clearances"] / m
    for f, base in PCT_BASE.items():                                # % on too few attempts -> unknown
        d.loc[d[base] < MIN_ATTEMPTS, f] = np.nan
    # possession adjustment of defensive volume, relative to the league-season average
    league_opp = d.groupby("season_id")["opp_touches"].transform("mean")
    d["possession_factor"] = (league_opp / d["opp_touches"]).clip(0.7, 1.4).fillna(1.0)
    for f, (_, kind) in FEATURES.items():
        if kind == "adj":
            d[f] = d[f] * d["possession_factor"]
    return d


def outfield_pool(df, min_minutes):
    """Usable league-seasons, outfield players with a known position group, enough minutes."""
    d = df[df["usable_season"] & (df["minutes"] >= min_minutes)].copy()
    d["group"] = d["detailed_position"].map(POSITION_GROUPS)
    d = d[d["group"].notna()]
    d["start"] = season_start(d["season"])
    return add_rates(d)


def zscore_within(d, cols, by=("season_id", "group")):
    """z of each feature within league-season and position group (style relative to peers)."""
    out = d.copy()
    g = out.groupby(list(by))
    for c in cols:
        mu, sd = g[c].transform("mean"), g[c].transform("std")
        out["z_" + c] = (out[c] - mu) / sd.replace(0, np.nan)
    return out

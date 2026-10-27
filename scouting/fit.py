"""
fit.py (v3) — players in our 30 Sportmonks leagues who play like Miami's players in a position,
and do it at least as well as their league. All outfield positions. Built on stability.py.

What changed from cb_fit v2 (each fix comes from a measured result):
  1. WEIGHTS FROM STABILITY. Each stat counts in proportion to its season-to-season r for that
     position (stability.py). Stats with r < 0.4 are dropped: they mostly measure noise or context.
  2. RELIABILITY-BASED SHRINKAGE. A player's z is multiplied by the reliability of the stat at
     HIS minutes (Spearman–Brown): rel(M) = k r / (1 + (k-1) r), k = M / M0, where r was measured
     at M0 minutes (median of the stability sample). Noisy stats with few minutes are pulled to
     the league average; stable stats with many minutes keep their value.
  3. TWO SEASONS COMBINED. Profile = minutes-weighted average of his z in his last two usable
     seasons (any of our leagues; z is relative to his league, so seasons in different leagues
     can be averaged). More minutes -> higher reliability -> less shrinkage.
  4. LEVEL from the success-% stats that passed the stability cut, weighted the same way.
     Still relative to his own league (translation.py: level carries over with r 0.4-0.6).

Usage:
  python scouting/fit.py --position CB
  python scouting/fit.py --position FB --max-age 26 --country Chile --country Colombia
  python scouting/fit.py --position W --domestic --abroad
  positions: CB FB CM AM W ST
Requires: scouting/output/stability_<date>.csv (run stability.py first)
Output: scouting/output/fit_<position>_<date>.csv
"""
import argparse
import glob
import os
import warnings
from datetime import date

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)

from sm_features import player_seasons  # noqa: E402
from sm_metrics import FEATURES, GROUP_LABEL, outfield_pool, zscore_within  # noqa: E402

R_MIN = 0.40
MIN_PEERS = 10
POOL_MINUTES = 600          # seasons below this don't enter a profile
TEMPLATE_MINUTES = 270      # a Miami reference can have less (3 full matches); shrinkage pulls him to average
TEMPLATE_TEAM = "miami fc"
TEMPLATE_LEAGUE = "USL Championship"


def load_stability(group):
    files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "output", "stability_*.csv")))
    if not files:
        raise SystemExit("run scouting/stability.py first (fit.py uses its weights)")
    st = pd.read_csv(files[-1])
    st = st[(st["group"] == group) & (st["r"] >= R_MIN)].set_index("feature")
    return st["r"].to_dict(), files[-1]


def spearman_brown(r, minutes, m0):
    k = np.asarray(minutes, float) / m0
    return k * r / (1 + (k - 1) * r)


def profiles(pool, weights, m0, since):
    """Combined, reliability-shrunk z profile per player from his last two usable seasons.
    Vectorized (same math as the original per-player loop): for each stat, minutes-weighted mean of his z over
    the seasons where it exists, times its Spearman-Brown reliability at those minutes; 0 if never measured."""
    feats = list(weights)
    p = pool.sort_values("minutes").groupby(["player_id", "season_id"]).tail(1)   # main club per season
    peers = p.groupby(["season_id", "group"])["player_id"].transform("size")
    p = zscore_within(p[peers >= MIN_PEERS], feats)
    p = p.sort_values(["player_id", "start", "minutes"]).groupby("player_id").tail(2)  # last two seasons
    p = p[p.groupby("player_id")["start"].transform("max") >= since]
    if p.empty:
        return pd.DataFrame()
    g = p.groupby("player_id", sort=True)
    last = g.tail(1).set_index("player_id").sort_index()
    out = pd.DataFrame({
        "player_id": last.index, "display_name": last["display_name"].values, "group": last["group"].values,
        "team": last["team"].values, "league": last["league"].values, "country": last["country"].values,
        "season": last["season"].values,
        "seasons_used": g["season"].apply(lambda x: " + ".join(x.astype(str))).reindex(last.index).values,
        "minutes_last": last["minutes"].values, "minutes_used": g["minutes"].sum().reindex(last.index).values,
        "dob": last["dob"].values, "height_cm": last["height_cm"].values,
        "us_link": last["us_link"].values if "us_link" in last else None, "team_id": last["team_id"].values})
    m = p["minutes"]
    pid = p["player_id"]
    for f in feats:
        z = p["z_" + f]
        okz = z.notna()
        den = m.where(okz, 0).groupby(pid).sum().reindex(last.index)
        num = (z.fillna(0) * m.where(okz, 0)).groupby(pid).sum().reindex(last.index)
        zavg = num / den.replace(0, np.nan)
        shr = spearman_brown(weights[f], den.to_numpy(float), m0)
        out["z_" + f] = np.where(den.to_numpy() > 0, zavg.to_numpy() * shr, 0.0)
        v = p[f]
        okv = v.notna()
        dv = m.where(okv, 0).groupby(pid).sum().reindex(last.index)
        nv = (v.fillna(0) * m.where(okv, 0)).groupby(pid).sum().reindex(last.index)
        out[f] = (nv / dv.replace(0, np.nan)).to_numpy()
    return out.reset_index(drop=True)


def find_players(everyone, names_wanted):
    """Resolve template names to player_ids: exact name first, then 'contains', preferring Miami players."""
    names = everyone["display_name"].fillna("").str.lower()
    miami = everyone["team"].str.lower().str.contains(TEMPLATE_TEAM, na=False)
    tids = []
    for t in names_wanted:
        if isinstance(t, (int, np.integer)):          # a player_id: no name matching needed
            tids.append(int(t))
            continue
        exact = everyone[names == t.lower()]
        hit = exact if not exact.empty else everyone[names.str.contains(t.lower(), regex=False)]
        # a surname matches many players ("Rocha"): prefer the ones who played for Miami
        if hit["player_id"].nunique() > 1 and (miami & names.str.contains(t.lower(), regex=False)).any():
            hit = hit[hit["player_id"].isin(everyone.loc[miami & names.str.contains(t.lower(), regex=False),
                                                         "player_id"])]
        if hit["player_id"].nunique() > 1:
            opts = ", ".join(sorted(hit["display_name"].unique())[:8])
            raise SystemExit(f"'{t}' matches several players ({opts}) — use the full name")
        if hit.empty:
            raise SystemExit(f"'{t}' not found with {POOL_MINUTES}+ min in a usable season")
        tids.append(hit["player_id"].iloc[0])
    return tids


def template_pool(allrows, min_minutes=TEMPLATE_MINUTES):
    """Like outfield_pool but for REFERENCE players: lower minutes, and generic listed positions
    ('Midfielder', 'Attacker'...) kept (the reference is re-labelled to the searched position anyway)."""
    from sm_metrics import POSITION_GROUPS, add_rates, season_start
    generic = {"Defender": "CB", "Midfielder": "CM", "Attacker": "ST"}
    d = allrows[allrows["usable_season"] & (allrows["minutes"] >= min_minutes)
                & allrows["detailed_position"].ne("Goalkeeper")].copy()
    d["group"] = d["detailed_position"].map(lambda v: POSITION_GROUPS.get(v, generic.get(v)))
    d = d[d["group"].notna()]
    d["start"] = season_start(d["season"])
    return add_rates(d)


def miami_players(allrows=None):
    """Every Miami player with a usable season (for the app's template picker)."""
    allrows = player_seasons() if allrows is None else allrows
    everyone = template_pool(allrows)
    m = everyone[everyone["team"].str.lower().str.contains(TEMPLATE_TEAM, na=False)]
    return (m.groupby(["player_id", "display_name"])
             .agg(group=("group", "last"), seasons=("season", lambda x: ", ".join(sorted(set(map(str, x))))),
                  minutes=("minutes", "sum"), best_season=("minutes", "max"))
             .reset_index().sort_values("minutes", ascending=False))


def rank(g, template_seasons=None, template_players=None, allrows=None):
    """Score every player in position group g against the template. No filters applied.
    Returns dict: cand (distance, level, age, now_*), tprof, template (z per stat), weights, stab_file."""
    seasons = template_seasons or ["2026"]
    weights, stab_file = load_stability(g)
    if not weights:
        raise SystemExit(f"no stat reached r >= {R_MIN} for {g}")
    success = [f for f in weights if FEATURES[f][1] == "pct"]
    allrows = player_seasons() if allrows is None else allrows
    pool = outfield_pool(allrows, POOL_MINUTES)
    pool = pool[pool["group"] == g]
    m0 = float(pool["minutes"].median())
    prof = profiles(pool, weights, m0, since=2000)            # everyone; filters come later
    zc = ["z_" + f for f in weights]
    w = np.array([weights[f] for f in weights])

    # template: Miami's players in this position, chosen seasons, combined the same way
    if template_players:
        # chosen players, profiled in THIS position's frame (their own position may differ)
        everyone = template_pool(allrows)
        tids = find_players(everyone, template_players)
        extra = everyone[everyone["player_id"].isin(tids)].assign(group=g)
        tprof = profiles(pd.concat([pool, extra[~extra["player_id"].isin(pool["player_id"])]]),
                         weights, m0, since=2000)
        tprof = tprof[tprof["player_id"].isin(tids)]
    else:
        tpool = pool[pool["team"].str.lower().str.contains(TEMPLATE_TEAM, na=False)
                     & pool["league"].eq(TEMPLATE_LEAGUE) & pool["season"].isin(seasons)]
        if tpool.empty:
            raise SystemExit(f"no Miami {GROUP_LABEL[g].lower()} with {POOL_MINUTES}+ min in {seasons}")
        tids = tpool["player_id"].unique()
        tprof = prof[prof["player_id"].isin(tids)]
    template = pd.Series(np.average(tprof[zc], axis=0, weights=tprof["minutes_used"]), index=zc)

    cand = prof[~prof["player_id"].isin(tids) & ~prof["team"].str.lower().str.contains(TEMPLATE_TEAM, na=False)].copy()
    cand["distance"] = np.sqrt((w * (cand[zc] - template) ** 2).sum(axis=1) / w.sum())
    if success:
        sw = np.array([weights[f] for f in success])
        cand["level"] = (cand[["z_" + f for f in success]] * sw).sum(axis=1) / sw.sum()
    else:
        cand["level"] = 0.0
    cand["age"] = ((pd.Timestamp(date.today()) - pd.to_datetime(cand["dob"], errors="coerce")).dt.days / 365.25).round(1)
    cand["start_last"] = pd.to_numeric(cand["season"].astype(str).str[:4], errors="coerce")
    # where is he NOW (latest row anywhere in our leagues, any minutes): bench roles and moves show up
    ar = allrows.assign(s0=pd.to_numeric(allrows["season"].astype(str).str[:4], errors="coerce"))
    ar["team_games"] = ar.groupby(["team_id", "season_id"])["apps"].transform("max")   # proxy: most apps in squad
    ar = ar.sort_values(["player_id", "s0", "minutes_all"])
    last = (ar.groupby("player_id").tail(1)
            [["player_id", "team", "season", "minutes_all", "league", "country", "team_games"]]
            .rename(columns={"team": "now_team", "season": "now_season", "minutes_all": "now_min",
                             "league": "now_league", "country": "now_country"}))
    # share of his team's minutes he played this season (team matches x 90)
    last["now_min_share"] = (last["now_min"] / (90 * last["team_games"].where(last["team_games"] > 0))).clip(0, 1)
    last = last.drop(columns="team_games")
    # starter share on his latest season with 8+ team matches (a season that just started says nothing)
    ss = ar[ar["team_games"] >= 8].groupby("player_id").tail(1)
    ss = ss.assign(now_start_share=(ss["starts"] / ss["team_games"]).clip(0, 1),
                   share_season=ss["season"])[["player_id", "now_start_share", "share_season"]]
    cand = cand.merge(last, on="player_id", how="left").merge(ss, on="player_id", how="left")
    # similarity as a 0-100 percentile among all candidates in this position (100 = closest)
    cand["similarity"] = (100 * (1 - cand["distance"].rank(pct=True)) + 100 / len(cand)).clip(0, 100).round(0)
    return {"cand": cand, "tprof": tprof, "template": template, "weights": weights, "stab_file": stab_file,
            "tids": tids, "template_label": "chosen players" if template_players else f"Miami {', '.join(seasons)}"}


def apply_filters(cand, since=2025, min_minutes=1200, max_age=30, min_level=0.0, excluded=("Major League Soccer",),
                  min_height=None, countries=None, domestic=False, abroad=False, sort="fit", closest=25, active=0):
    c = cand[(cand["start_last"] >= since) & (cand["minutes_used"] >= min_minutes) & (cand["age"] <= max_age)
             & (cand["level"] >= min_level) & ~cand["league"].isin(list(excluded))
             & ~cand["now_league"].isin(list(excluded))]          # excluded where he played OR where he is now
    if min_height:
        c = c[c["height_cm"] >= min_height]
    if countries:
        c = c[c["country"].isin(countries)]
    if domestic:
        c = c[c["us_link"].notna()]
    if abroad:
        c = c[c["country"] != "United States"]
    if active:
        c = c[c["now_min"] >= active]
    if sort == "level":
        cut = c["distance"].quantile(closest / 100)
        c = c[c["distance"] <= cut].sort_values("level", ascending=False)
    else:
        c = c.sort_values("distance")
    c = c.copy()
    c.insert(0, "rank", range(1, len(c) + 1))
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--position", required=True, choices=list(GROUP_LABEL))
    ap.add_argument("--template-season", action="append", help="Miami seasons for the template (default 2026)")
    ap.add_argument("--max-age", type=float, default=30)
    ap.add_argument("--min-height", type=int)
    ap.add_argument("--min-level", type=float, default=0.0)
    ap.add_argument("--min-minutes", type=int, default=1200, help="minutes over the seasons used")
    ap.add_argument("--country", action="append")
    ap.add_argument("--exclude-league", action="append", default=None)
    ap.add_argument("--since", type=int, default=2025)
    ap.add_argument("--domestic", action="store_true")
    ap.add_argument("--abroad", action="store_true")
    ap.add_argument("--template-player", action="append",
                    help="build the template from these players instead (name contains; repeatable), "
                         "e.g. --template-player Rocha --template-player Tunbridge")
    ap.add_argument("--sort", choices=["fit", "level"], default="fit",
                    help="fit: closest style first. level: among the closest --closest %% in style, best level first")
    ap.add_argument("--closest", type=float, default=25, help="with --sort level: style cut, in %% of the pool")
    ap.add_argument("--active", type=int, default=0,
                    help="drop players with fewer than N minutes in their latest season (careful early in a season)")
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()
    g = a.position
    excluded = a.exclude_league if a.exclude_league is not None else ["Major League Soccer"]

    res = rank(g, a.template_season, a.template_player)
    weights, tprof, template = res["weights"], res["tprof"], res["template"]
    print(f"{GROUP_LABEL[g]} · template = {res['template_label']} · weights from {os.path.basename(res['stab_file'])}")
    if len(tprof) == 1:
        print("   ⚠ template is ONE player: the list means 'players like him', not 'like Miami's position'")
    for r in tprof.sort_values("minutes_used", ascending=False).itertuples():
        print(f"   {r.display_name:24s} {int(r.minutes_used):5d} min ({r.seasons_used})")
    print(f"\nStats used (r >= {R_MIN}) and Miami's profile (shrunk z vs league peers):")
    for f in sorted(weights, key=lambda x: -weights[x]):
        v = template["z_" + f]
        print(f"   {FEATURES[f][0]:34s} weight {weights[f]:.2f}   {v:+.2f} {'█' * int(round(abs(v) * 10))}")
    dropped = [FEATURES[f][0] for f in FEATURES if f not in weights]
    print(f"   dropped (unstable for this position): {', '.join(dropped)}")

    n_all = len(res["cand"])
    cand = apply_filters(res["cand"], a.since, a.min_minutes, a.max_age, a.min_level, excluded, a.min_height,
                         a.country, a.domestic, a.abroad, a.sort, a.closest, a.active)
    zc = ["z_" + f for f in weights]

    od = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(od, exist_ok=True)
    out = os.path.join(od, f"fit_{g}_{date.today().isoformat()}.csv")
    cols = ["rank", "display_name", "age", "height_cm", "team", "country", "league", "season", "seasons_used",
            "minutes_used", "distance", "level", "us_link", "now_team", "now_season", "now_min"] + list(weights) + zc
    cand[cols].to_csv(out, index=False)

    print(f"\n{len(cand)} of {n_all} {GROUP_LABEL[g].lower()} pass the filters · top {a.top} "
          f"{'by similarity' if a.sort == 'fit' else f'by level among the closest {a.closest:g}% in style'}")
    print(f"{'#':>3s} {'player':24s} {'age':>4s} {'cm':>4s} {'team':22s} {'league':26s} {'seasons':18s} "
          f"{'min':>5s} {'dist':>5s} {'level':>6s}  now")
    for r in cand.head(a.top).itertuples():
        h = f"{r.height_cm:4.0f}" if pd.notna(r.height_cm) else "   -"
        print(f"{r.rank:3d} {str(r.display_name)[:24]:24s} {r.age:4.0f} {h} {str(r.team)[:22]:22s} "
              f"{(str(r.country) + ' ' + str(r.league))[:26]:26s} {r.seasons_used[:18]:18s} "
              f"{int(r.minutes_used):5d} {r.distance:5.2f} {r.level:+6.2f}  "
              f"{'same' if (r.now_team == r.team and r.now_season == r.season) else f'{str(r.now_team)[:18]} {r.now_season} · {int(r.now_min)} min'}")
    print(f"\n-> {out}")
    print("dist = weighted distance to Miami's profile (smaller = more similar). level = reliable success-% "
          "stats vs his own league, shrunk by reliability (0 = league average).")


if __name__ == "__main__":
    main()

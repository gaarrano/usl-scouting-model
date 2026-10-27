"""
translation.py — what happens to a player's numbers when he moves INTO a target league
(default: USL Championship)? Two questions, for every outfield position:

1. LEAGUE FACTORS — "a Chilean centre-back's 5.0 aerial duels/90 become how many in the USL?"
   Naive approach (USL value / origin value) is biased: players get signed after a GOOD season,
   and a good season tends to be followed by a more normal one anyway (regression to the mean),
   plus a year of ageing. So for every origin league we first learn, from players who STAYED,
   what their next season looks like given this one:   next = a + b * this   (per stat, position).
   For a mover we predict "his next season had he stayed", and the league factor is
        actual USL value / predicted stay value        (volume stats, geometric mean)
        actual USL %     - predicted stay %            (success %, in points)
   Factor 1.00 = no change from the move itself; 0.80 = the stat drops 20% in the USL.

2. LEVEL TRANSFER — "does being good in your league predict being good in the USL?"
   Correlation between a mover's z in his origin league (vs same-position peers) and his z in the
   target league. This is the closest thing to testing whether the fit model's 'level' predicts.

Bootstrap CIs over movers. Leagues with fewer than MIN_MOVERS movers are pooled as "other".

Usage:  python scouting/translation.py [--to "USL Championship"] [--min-minutes 900]
Output: scouting/output/translation_factors_<date>.csv, level_transfer_<date>.csv
"""
import argparse
import os
import warnings
from datetime import date

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)   # constant columns -> NaN r, handled
warnings.filterwarnings("ignore", message="Polyfit may be poorly conditioned")

from sm_features import player_seasons
from sm_metrics import FEATURES, GROUP_LABEL, outfield_pool, zscore_within

N_BOOT = 2000
MIN_MOVERS = 8
MIN_STAYERS = 30
MIN_PEERS = 10
KEY_STATS = ["passes_p90", "pass_pct", "duels_p90", "duel_pct", "aerial_p90", "aerial_pct",
             "dribbles_p90", "shots_p90", "key_passes_p90", "int_p90"]


def prepare(min_minutes):
    p = outfield_pool(player_seasons(), min_minutes)
    p = p.sort_values("minutes").groupby(["player_id", "league_id", "start"]).tail(1)
    peers = p.groupby(["season_id", "group"])["player_id"].transform("size")
    p = zscore_within(p, list(FEATURES))
    for f in FEATURES:                                  # no z where the peer group is too small
        p.loc[peers < MIN_PEERS, "z_" + f] = np.nan
    return p


def find_movers(p, target):
    tgt = p[p["league"] == target]
    org = p[p["league"] != target]
    m = org.merge(tgt, on="player_id", suffixes=("_o", "_t"))
    m = m[(m["start_t"] - m["start_o"]).isin([0, 1])]
    # closest origin season before the move; one pair per player
    m = m.sort_values(["player_id", "start_o", "start_t"]).groupby("player_id").tail(1)
    return m


def stayer_models(p, target):
    """next = a + b*this, per origin league and position group (fallback: league-wide)."""
    nxt = p.copy()
    nxt["start"] -= 1
    s = p.merge(nxt, on=["player_id", "league_id", "start"], suffixes=("_1", "_2"))
    s = s[s["league_1"] != target]
    models = {}
    for f in FEATURES:
        for (lg, g), d in list(s.groupby(["league_id", "group_1"])) + [((lg, None), d) for lg, d in s.groupby("league_id")]:
            d = d[[f + "_1", f + "_2"]].dropna()
            if len(d) >= MIN_STAYERS and d[f + "_1"].std() > 0:
                b, a = np.polyfit(d[f + "_1"], d[f + "_2"], 1)
                models[(f, lg, g)] = (a, b, len(d))
    return models


def predict_stay(models, f, lg, g, x):
    m = models.get((f, lg, g)) or models.get((f, lg, None))
    if m is None:
        return np.nan
    a, b, _ = m
    return a + b * x


def factor(actual, pred, kind, rng):
    ok = ~(np.isnan(actual) | np.isnan(pred))
    if kind == "pct":
        v = (actual - pred)[ok] * 100                     # percentage points
        agg = np.mean
    else:
        ok &= (actual > 0) & (pred > 0)
        v = np.log(actual[ok] / pred[ok])
        agg = lambda z, axis=None: np.exp(np.mean(z, axis=axis))     # noqa: E731
    n = len(v)
    if n < MIN_MOVERS:
        return n, np.nan, np.nan, np.nan
    boot = v[rng.integers(0, n, size=(N_BOOT, n))]
    est = agg(v)
    bs = agg(boot, axis=1) if kind != "pct" else boot.mean(1)
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return n, est, lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", default="USL Championship")
    ap.add_argument("--min-minutes", type=int, default=900)
    a = ap.parse_args()
    rng = np.random.default_rng(0)

    p = prepare(a.min_minutes)
    movers = find_movers(p, a.to)
    models = stayer_models(p, a.to)
    if movers.empty:
        raise SystemExit(f"no players moved into {a.to} with {a.min_minutes}+ minutes on both sides")
    counts = movers.groupby("league_o").size()
    movers["origin"] = np.where(movers["league_o"].map(counts) >= MIN_MOVERS,
                                movers["country_o"] + " " + movers["league_o"], "Other leagues (pooled)")

    # 1) league factors
    rows = []
    for origin, d in list(movers.groupby("origin")) + [("ALL ORIGINS", movers)]:
        for f, (label, kind) in FEATURES.items():
            pred = np.array([predict_stay(models, f, lg, g, x)
                             for lg, g, x in zip(d["league_id_o"], d["group_o"], d[f + "_o"])], float)
            n, est, lo, hi = factor(d[f + "_t"].to_numpy(float), pred, kind, rng)
            rows.append({"origin": origin, "feature": f, "label": label, "kind": kind,
                         "n_movers": n, "factor": est, "ci_low": lo, "ci_high": hi})
    fac = pd.DataFrame(rows)
    # shrunk factor: origin league -> ALL ORIGINS by n/(n+N0); ALL ORIGINS -> no change by n/(n+N0)
    N0 = 10
    to_log = lambda v, k: v if k == "pct" else np.log(v)             # noqa: E731
    from_log = lambda v, k: v if k == "pct" else np.exp(v)           # noqa: E731
    allf = fac[fac["origin"] == "ALL ORIGINS"].set_index("feature")
    shr = []
    for r in fac.itertuples():
        if np.isnan(r.factor):
            shr.append(np.nan)
            continue
        a_n, a_v = allf.loc[r.feature, "n_movers"], allf.loc[r.feature, "factor"]
        pooled = to_log(a_v, r.kind) * a_n / (a_n + N0) if not np.isnan(a_v) else 0.0
        own = to_log(r.factor, r.kind)
        shr.append(from_log(pooled if r.origin == "ALL ORIGINS" else (r.n_movers * own + N0 * pooled) / (r.n_movers + N0), r.kind))
    fac["factor_shrunk"] = shr

    # 2) level transfer: does origin z predict target z?
    lt = []
    for g in [None] + list(GROUP_LABEL):
        d = movers if g is None else movers[movers["group_o"] == g]
        for f, (label, kind) in FEATURES.items():
            x, y = d["z_" + f + "_o"].to_numpy(float), d["z_" + f + "_t"].to_numpy(float)
            ok = ~(np.isnan(x) | np.isnan(y))
            n = int(ok.sum())
            if n < 25:
                continue
            x, y = x[ok], y[ok]
            r = np.corrcoef(x, y)[0, 1]
            idx = rng.integers(0, n, size=(N_BOOT, n))
            rb = [np.corrcoef(x[i], y[i])[0, 1] for i in idx[:500]]
            lo, hi = np.nanpercentile(rb, [2.5, 97.5])
            lt.append({"group": g or "ALL", "feature": f, "label": label, "n_movers": n, "r": r,
                       "ci_low": lo, "ci_high": hi})
    lev = pd.DataFrame(lt)

    od = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(od, exist_ok=True)
    today = date.today().isoformat()
    fac.round(3).to_csv(os.path.join(od, f"translation_factors_{today}.csv"), index=False)
    lev.round(3).to_csv(os.path.join(od, f"level_transfer_{today}.csv"), index=False)

    print(f"Players who moved into {a.to} ({a.min_minutes}+ min both sides): {len(movers)}")
    for lg, n in counts.sort_values(ascending=False).items():
        print(f"   {n:4d}  from {lg}")
    print(f"\nLEAGUE FACTORS (move effect, after removing regression to the mean; shrunk toward the pooled "
          f"factor when a league has few movers) — key stats")
    print("   volume stats: x factor (0.80 = drops 20% in the USL) · success %: points of change")
    hdr = "".join(f"{FEATURES[f][0][:12]:>13s}" for f in KEY_STATS)
    print(f"   {'origin':40s} {'n':>4s}{hdr}")
    for origin, d in fac.groupby("origin"):
        d = d.set_index("feature")
        vals = ""
        for f in KEY_STATS:
            v = d.loc[f, "factor_shrunk"]
            vals += f"{'':>13s}" if np.isnan(v) else (f"{v:+12.1f}p" if d.loc[f, "kind"] == "pct" else f"{v:12.2f}x")
        print(f"   {origin[:40]:40s} {int(d['n_movers'].max()):4d}{vals}")
    print("\nLEVEL TRANSFER — does a player's level in his league (z vs same-position peers) carry into "
          f"{a.to}? (all positions pooled)")
    print(f"   {'stat':34s} {'n':>4s} {'r':>6s}  95% CI")
    for r in lev[lev["group"] == "ALL"].sort_values("r", ascending=False).itertuples():
        print(f"   {r.label:34s} {r.n_movers:4d} {r.r:6.2f}  [{r.ci_low:.2f}, {r.ci_high:.2f}]")
    print(f"\n-> {od}/translation_factors_{today}.csv, level_transfer_{today}.csv (also by position group)")


if __name__ == "__main__":
    main()

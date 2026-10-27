"""
stability.py — which stats describe the PLAYER, and which are noise or team context?

For every outfield position group, take players with >= MIN_MINUTES in two consecutive
seasons of the same league and correlate each stat between season 1 and season 2.
Stats are z-scored within league-season and position group first, so leagues are comparable
and league-wide trends drop out.

  r >= 0.6   strong   — a trait of the player: weight it fully
  0.4–0.6    moderate — usable, with caution
  < 0.4      weak     — mostly noise or context: drop it or weight it little

Two diagnostic splits:
  same team  vs  new team (same league): if r falls a lot when the player changes club,
  the stat depends on the team's system more than on the player.

Confidence intervals: bootstrap over players (2,000 resamples).
This is test-retest reliability (bootstrap CIs over players).

Usage:  python scouting/stability.py [--min-minutes 900]
Output: scouting/output/stability_<date>.csv
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
MIN_PEERS = 10          # league-season-group needs this many players for a meaningful z
MIN_PAIRS = 25          # below this, r is not reported


def season_pairs(pool):
    # one row per player-league-season (the club where he played most, if he moved mid-season)
    p = pool.sort_values("minutes").groupby(["player_id", "league_id", "start"]).tail(1)
    peers = p.groupby(["season_id", "group"])["player_id"].transform("size")
    p = zscore_within(p[peers >= MIN_PEERS], list(FEATURES))
    nxt = p.copy()
    nxt["start"] = nxt["start"] - 1                  # align season t+1 with season t
    return p.merge(nxt, on=["player_id", "league_id", "start"], suffixes=("_1", "_2"))


def corr_ci(x, y, rng):
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    n = len(x)
    if n < MIN_PAIRS:
        return n, np.nan, np.nan, np.nan
    r = np.corrcoef(x, y)[0, 1]
    idx = rng.integers(0, n, size=(N_BOOT, n))
    xb, yb = x[idx], y[idx]
    xb = xb - xb.mean(1, keepdims=True)
    yb = yb - yb.mean(1, keepdims=True)
    rb = (xb * yb).sum(1) / np.sqrt((xb ** 2).sum(1) * (yb ** 2).sum(1))
    lo, hi = np.nanpercentile(rb, [2.5, 97.5])
    return n, r, lo, hi


def verdict(r):
    if np.isnan(r):
        return "too few"
    return "strong" if r >= 0.6 else "moderate" if r >= 0.4 else "weak"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-minutes", type=int, default=900)
    a = ap.parse_args()
    rng = np.random.default_rng(0)

    pairs = season_pairs(outfield_pool(player_seasons(), a.min_minutes))
    rows = []
    for g in GROUP_LABEL:
        pg = pairs[pairs["group_1"] == g]
        same = pg["team_id_1"] == pg["team_id_2"]
        for f, (label, kind) in FEATURES.items():
            x, y = pg[f"z_{f}_1"].to_numpy(float), pg[f"z_{f}_2"].to_numpy(float)
            n, r, lo, hi = corr_ci(x, y, rng)
            ns, rs, _, _ = corr_ci(x[same.to_numpy()], y[same.to_numpy()], rng)
            nn, rn, _, _ = corr_ci(x[~same.to_numpy()], y[~same.to_numpy()], rng)
            rows.append({"group": g, "feature": f, "label": label, "kind": kind, "n_pairs": n, "r": r,
                         "ci_low": lo, "ci_high": hi, "verdict": verdict(r),
                         "n_same_team": ns, "r_same_team": rs, "n_new_team": nn, "r_new_team": rn})
    res = pd.DataFrame(rows)
    os.makedirs(os.path.join(os.path.dirname(__file__), "output"), exist_ok=True)
    out = os.path.join(os.path.dirname(__file__), "output", f"stability_{date.today().isoformat()}.csv")
    res.round(3).to_csv(out, index=False)

    print(f"Season-to-season stability · players with {a.min_minutes}+ min in consecutive seasons, same league")
    for g, lab in GROUP_LABEL.items():
        rg = res[res["group"] == g].sort_values("r", ascending=False)
        npairs = int(rg["n_pairs"].max()) if len(rg) else 0
        print(f"\n{lab} ({npairs} player pairs)")
        print(f"   {'stat':34s} {'r':>5s}  {'95% CI':>13s}  {'verdict':9s} {'same team':>9s} {'new team':>9s}")
        for r in rg.itertuples():
            if np.isnan(r.r):
                continue
            rs = f"{r.r_same_team:.2f}" if not np.isnan(r.r_same_team) else "-"
            rn = f"{r.r_new_team:.2f}" if not np.isnan(r.r_new_team) else "-"
            flag = "  <- team-driven?" if (not np.isnan(r.r_same_team) and not np.isnan(r.r_new_team)
                                          and r.r_same_team - r.r_new_team >= 0.2) else ""
            print(f"   {r.label:34s} {r.r:5.2f}  [{r.ci_low:5.2f},{r.ci_high:5.2f}]  {r.verdict:9s} "
                  f"{rs:>9s} {rn:>9s}{flag}")
    print(f"\n-> {out}")
    print("r = correlation between a player's season 1 and season 2 (z within league and position). "
          "'team-driven?' = r drops by 0.2+ when he changes club.")


if __name__ == "__main__":
    main()

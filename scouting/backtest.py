"""
backtest.py — "If we had used the model the day before signing him, what would it have
predicted, and what actually happened?"

For every player who moved INTO the target league (default USL Championship) with enough
minutes on both sides:
  1. start from his last season in the origin league (what we knew before signing)
  2. regression to the mean: what players who STAYED in that league do the next season
  3. league factor: the change other movers from the same league showed in the target league,
     estimated LEAVING HIM OUT (no peeking at his own outcome = leave-one-out validation),
     shrunk toward the all-leagues factor when that league has few movers, and the all-leagues
     factor shrunk toward "no change" (N0 = 10 pseudo-movers; empirical-Bayes idea)
  4. prediction + 80% range (from the errors of the other movers)
  5. compare with his actual season in the target league

Scoreboard: the model must beat the naive guess "same numbers as last season".
  MAE ratio < 1  -> the model helps for that stat;  >= 1 -> it adds nothing.
  Coverage of the 80% range should be close to 80% (too low = overconfident).

Usage:
  python scouting/backtest.py                          # scoreboard, all positions
  python scouting/backtest.py --player Milesi          # one player's card
  python scouting/backtest.py --team "Miami"           # every arrival at one club
Output: scouting/output/backtest_<date>.csv (every mover x stat: before, predicted, range, actual)
"""
import argparse
import os
import warnings
from datetime import date

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", message="Polyfit may be poorly conditioned")

from sm_metrics import FEATURES  # noqa: E402
from translation import find_movers, predict_stay, prepare, stayer_models  # noqa: E402

MIN_SAME_ORIGIN = 7      # minimum movers (excluding him) to make any prediction
N0 = 10                  # shrinkage strength: a league with 10 movers gets half its own factor, half the pooled one
Z80 = 1.2816


def residuals(actual, pred, kind):
    if kind == "pct":
        return actual - pred
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(actual / pred)


def run(movers, models):
    rows = []
    movers = movers.reset_index(drop=True)
    for f, (label, kind) in FEATURES.items():
        stay = np.array([predict_stay(models, f, lg, g, x)
                         for lg, g, x in zip(movers["league_id_o"], movers["group_o"], movers[f + "_o"])], float)
        actual = movers[f + "_t"].to_numpy(float)
        before = movers[f + "_o"].to_numpy(float)
        res = residuals(actual, stay, kind)
        ok = np.isfinite(res)
        for i in range(len(movers)):
            if not (ok[i] and np.isfinite(before[i])):
                continue
            others = ok.copy()
            others[i] = False                                         # leave him out
            same = others & (movers["league_id_o"].to_numpy() == movers.at[i, "league_id_o"])
            if others.sum() < MIN_SAME_ORIGIN:
                continue
            # empirical-Bayes style shrinkage: few movers -> trust the estimate less
            n_all, n_lg = others.sum(), same.sum()
            pooled = res[others].mean() * n_all / (n_all + N0)                  # pooled -> 0 (no effect)
            shift = ((res[same].sum() + N0 * pooled) / (n_lg + N0)) if n_lg else pooled   # league -> pooled
            spread = res[others].std(ddof=1)
            if kind == "pct":
                pred, lo, hi = stay[i] + shift, stay[i] + shift - Z80 * spread, stay[i] + shift + Z80 * spread
            else:
                pred = stay[i] * np.exp(shift)
                lo, hi = pred * np.exp(-Z80 * spread), pred * np.exp(Z80 * spread)
            rows.append({"player_id": movers.at[i, "player_id"], "player": movers.at[i, "display_name_o"],
                         "group": movers.at[i, "group_o"], "from_team": movers.at[i, "team_o"],
                         "from_league": f"{movers.at[i, 'country_o']} {movers.at[i, 'league_o']}",
                         "from_season": movers.at[i, "season_o"], "to_team": movers.at[i, "team_t"],
                         "to_season": movers.at[i, "season_t"], "feature": f, "label": label, "kind": kind,
                         "before": before[i], "predicted": pred, "low80": lo, "high80": hi, "actual": actual[i],
                         "movers_same_league": int(same.sum())})
    bt = pd.DataFrame(rows)
    bt["inside80"] = bt["actual"].between(bt["low80"], bt["high80"])
    bt["verdict"] = np.where(bt["inside80"], "as expected",
                             np.where(bt["actual"] > bt["high80"], "above", "below"))
    bt["err_model"] = (bt["actual"] - bt["predicted"]).abs()
    bt["err_naive"] = (bt["actual"] - bt["before"]).abs()
    return bt


def fmt(v, kind):
    return f"{100 * v:5.1f}%" if kind == "pct" else f"{v:6.2f}"


def card(bt, mask, title):
    sub = bt[mask]
    if sub.empty:
        print(f"\n{title}: no player found (needs {'900'}+ min before and after the move, both in our leagues)")
        return
    for pid, d in sub.groupby("player_id"):
        r0 = d.iloc[0]
        n_in = int(d["inside80"].sum())
        print(f"\n{r0.player} · {r0.group} · {r0.from_team} ({r0.from_league} {r0.from_season}) "
              f"-> {r0.to_team} ({r0.to_season})")
        print(f"   {n_in}/{len(d)} stats inside the predicted 80% range")
        print(f"   {'stat':34s} {'before':>8s} {'predicted':>9s} {'80% range':>17s} {'actual':>8s}  verdict")
        for r in d.itertuples():
            rng = f"{fmt(r.low80, r.kind)}–{fmt(r.high80, r.kind)}"
            print(f"   {r.label:34s} {fmt(r.before, r.kind):>8s} {fmt(r.predicted, r.kind):>9s} {rng:>17s} "
                  f"{fmt(r.actual, r.kind):>8s}  {r.verdict}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", default="USL Championship")
    ap.add_argument("--min-minutes", type=int, default=900)
    ap.add_argument("--player", help="name contains (e.g. Milesi)")
    ap.add_argument("--team", help="arrivals at a club whose name contains this (e.g. Miami)")
    a = ap.parse_args()

    p = prepare(a.min_minutes)
    movers = find_movers(p, a.to)
    if movers.empty:
        raise SystemExit(f"no movers into {a.to}")
    bt = run(movers, stayer_models(p, a.to))
    od = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(od, exist_ok=True)
    out = os.path.join(od, f"backtest_{date.today().isoformat()}.csv")
    bt.round(4).to_csv(out, index=False)

    if a.player:
        card(bt, bt["player"].str.contains(a.player, case=False, na=False), a.player)
    elif a.team:
        card(bt, bt["to_team"].str.contains(a.team, case=False, na=False), a.team)
    else:
        print(f"Backtest: {bt['player_id'].nunique()} players who moved into {a.to}, "
              f"each predicted without his own outcome")
        sb = bt.groupby(["feature", "label"]).agg(n=("player_id", "size"), mae_model=("err_model", "mean"),
                                                  mae_naive=("err_naive", "mean"), coverage=("inside80", "mean"))
        sb["mae_ratio"] = sb["mae_model"] / sb["mae_naive"]
        sb = sb.reset_index().sort_values("mae_ratio")
        print(f"   {'stat':34s} {'n':>4s} {'model err / naive err':>22s} {'inside 80% range':>17s}")
        for r in sb.itertuples():
            tag = "model helps" if r.mae_ratio < 0.9 else "no better" if r.mae_ratio < 1.05 else "WORSE"
            print(f"   {r.label:34s} {r.n:4d} {r.mae_ratio:16.2f}  {tag:11s} {100 * r.coverage:9.0f}%")
        print("\nmodel err / naive err < 1: the prediction beats 'same as last season'. "
              "Inside 80% range should be ~80%.")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()

"""
position_model.py — "what position does he actually play?" from three sources:
  1. Sportmonks' listed position (one per player, can be outdated)
  2. lineups: the line he started in most often each season (defence / midfield / attack)
  3. his numbers: a multinomial logistic regression trained on every player-season (900+ min) whose
     listed position we know, using his stats as z-scores within his league-season. Output = probability
     for each position group. Validated with 5-fold cross-validation grouped by player (a player never
     appears in training and test at once).

Usage:  python scouting/position_model.py            # prints the cross-validated accuracy
"""
import json
import os
import warnings

import numpy as np
import pandas as pd

from sm_metrics import FEATURES, outfield_pool

warnings.filterwarnings("ignore")

MIN_MINUTES = 900
EXTRA = {"final_third_p90": "final_third_passes", "recov_p90": "recoveries"}
FEATS = list(FEATURES) + list(EXTRA)
LINE_ES = {25: "defensa", 26: "mediocampo", 27: "delantera", 24: "arco"}
DETAILED_ES = {
    "Centre Back": "defensa central", "Left Back": "lateral izquierdo", "Right Back": "lateral derecho",
    "Left Wing Back": "carrilero izquierdo", "Right Wing Back": "carrilero derecho",
    "Defensive Midfield": "mediocentro defensivo", "Central Midfield": "mediocentro",
    "Attacking Midfield": "mediapunta", "Secondary Striker": "segundo delantero",
    "Left Wing": "extremo izquierdo", "Right Wing": "extremo derecho", "Left Midfield": "volante izquierdo",
    "Right Midfield": "volante derecho", "Centre Forward": "delantero centro",
}


def _z(p):
    m = p["minutes"] / 90
    for f, col in EXTRA.items():
        p[f] = p[col] / m
    for f in FEATS:
        g = p.groupby("season_id")[f]
        p["z_" + f] = ((p[f] - g.transform("mean")) / g.transform("std")).fillna(0).clip(-4, 4)
    return p


def train(rows, cv=False):
    """Fit on all labelled player-seasons. Returns (model, classes, cv_accuracy, cv_top2) — cv only if asked."""
    from sklearn.linear_model import LogisticRegression
    p = _z(outfield_pool(rows, MIN_MINUTES))
    X, y = p[["z_" + f for f in FEATS]].to_numpy(), p["group"].to_numpy()
    model = LogisticRegression(max_iter=2000, C=0.5).fit(X, y)
    acc = top2 = None
    if cv:
        from sklearn.model_selection import GroupKFold, cross_val_predict
        pr = cross_val_predict(LogisticRegression(max_iter=2000, C=0.5), X, y, groups=p["player_id"],
                               cv=GroupKFold(5), method="predict_proba")
        cls = np.unique(y)
        acc = float((cls[pr.argmax(1)] == y).mean())
        best2 = np.argsort(-pr, 1)[:, :2]
        top2 = float(np.mean([y[i] in cls[best2[i]] for i in range(len(y))]))
    return model, list(model.classes_), acc, top2


def scoring_frame(rows):
    """All usable player-seasons (600+ min) with z-scores, for prediction (z still vs the full league-season)."""
    return _z(outfield_pool(rows, 600))


def describe(rows, frame, model, player_id):
    """Positions for one player: listed, lineup line per season, and stats-based probabilities
    (minutes-weighted over his last two seasons)."""
    mine = rows[rows["player_id"] == player_id]
    listed = mine["detailed_position"].dropna()
    listed = DETAILED_ES.get(listed.iloc[0], listed.iloc[0]) if len(listed) else None
    lines = (mine[mine["minutes"] > 0].assign(s0=pd.to_numeric(mine["season"].astype(str).str[:4], errors="coerce"))
             .sort_values(["s0", "minutes"]).groupby("season").tail(1).sort_values("s0").tail(3))
    lineup = [(str(r.season), LINE_ES.get(int(r.match_position_id), "—"), int(r.minutes))
              for r in lines.itertuples() if pd.notna(r.match_position_id)]
    f = frame[frame["player_id"] == player_id]
    probs = None
    if len(f):
        last2 = f.sort_values("start")[["season_id", "start"]].drop_duplicates().tail(2)["season_id"]
        f = f[f["season_id"].isin(last2)]
        pr = model.predict_proba(f[["z_" + c for c in FEATS]].to_numpy())
        probs = pd.Series(np.average(pr, axis=0, weights=f["minutes"]), index=model.classes_).sort_values(ascending=False)
    return {"listed": listed, "lineup": lineup, "probs": probs}


CV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "position_model_cv.json")


def saved_cv():
    """Cross-validated accuracy saved by `python scouting/position_model.py` (so the app doesn't redo the CV)."""
    try:
        with open(CV_FILE) as f:
            d = json.load(f)
        return d["accuracy"], d["top2"]
    except (OSError, ValueError, KeyError):
        return None, None


if __name__ == "__main__":
    from datetime import date
    from sm_features import player_seasons
    _, cls, acc, top2 = train(player_seasons(), cv=True)
    os.makedirs(os.path.dirname(CV_FILE), exist_ok=True)
    with open(CV_FILE, "w") as f:
        json.dump({"accuracy": acc, "top2": top2, "classes": cls, "date": date.today().isoformat()}, f, indent=1)
    print(f"position model · classes {cls} · cross-validated accuracy {acc:.1%} · right position in top 2: {top2:.1%}"
          f" -> {CV_FILE}")

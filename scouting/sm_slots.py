"""
sm_slots.py — where each player STARTED on the team sheet (Sportmonks formation_field "row:col"), turned into
Football Manager-style positions: POR, LI, DFC, LD, CAI, MCD, CAD, MI, MC, MD, EI, MCO, ED, DC.

Starters only (substitutes have no slot). One row per player, season, team and slot with starts and minutes,
saved to data/sm_player_slots.pkl so the app can run without Postgres.

How a slot is named (rows counted from the goalkeeper; the formation is read from the eleven itself):
  defence row  — 4: LI DFC DFC LD · 5: CAI DFC DFC DFC CAD · 2-3: DFC
  last row     — 1-2: DC · 3+: EI DC ... ED
  rows between — ends of a row of 4+: CAI/CAD with a back three (first midfield row), EI/ED in the top midfield
                 row, MI/MD otherwise; top midfield row of 3 with one striker (4-2-3-1): EI MCO ED;
                 centre: MCD in the first of several midfield rows (a row of 3: only the middle one), MCO in the top one (if 3 or fewer), MC otherwise

Which end of a row is the left depends on the side of the pitch: Sportmonks numbers the columns from the
AWAY team's left, so column 1 is the left for the away team and the right for the home team (checked against
players listed as Left Back / Right Back: 9,873 of 10,218 home LB starts in column 4; 8,814 of 9,711 away in column 1).

Rebuild (on the Mac, Postgres running):   python scouting/sm_slots.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "database", "ingest"))

CACHE = os.environ.get("SM_SLOTS") or os.path.join(os.path.dirname(__file__), "..", "data", "sm_player_slots.pkl")
SLOT_GROUP = {"LI": "FB", "LD": "FB", "CAI": "FB", "CAD": "FB", "DFC": "CB", "MCD": "CM", "MC": "CM",
              "MCO": "AM", "MI": "W", "MD": "W", "EI": "W", "ED": "W", "DC": "ST", "POR": "GK"}
# column 1 = left for the AWAY team, right for the HOME team (see the check in __main__)


def build():
    import db
    with db.transaction() as cur:
        cur.execute("""
            WITH s AS (
                SELECT pm.fixture_id, pm.team_id, pm.player_id, pm.minutes, f.season_id,
                       (pm.team_id = f.home_team_id) AS home,
                       split_part(pm.formation_field, ':', 1)::int AS r,
                       split_part(pm.formation_field, ':', 2)::int AS c
                FROM sm_player_match pm JOIN sm_fixtures f USING (fixture_id)
                WHERE pm.starter AND pm.formation_field ~ '^[0-9]+:[0-9]+$'),
            rc AS (SELECT fixture_id, team_id, r, count(*) AS n FROM s GROUP BY 1, 2, 3),
            fm AS (SELECT fixture_id, team_id, string_agg(n::text, '-' ORDER BY r) AS formation,
                          sum(n) AS n_players FROM rc GROUP BY 1, 2)
            SELECT s.player_id, s.season_id, s.team_id, s.home, fm.formation, s.r, s.c,
                   count(*) AS starts, coalesce(sum(s.minutes), 0) AS minutes
            FROM s JOIN fm USING (fixture_id, team_id)
            WHERE fm.n_players = 11
            GROUP BY 1, 2, 3, 4, 5, 6, 7""")
        df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
        cur.execute("SELECT count(*) FILTER (WHERE formation_field IS NOT NULL), count(*) "
                    "FROM sm_player_match WHERE starter")
        with_ff, total = cur.fetchone()
    print(f"starters with a slot: {with_ff} of {total} ({with_ff / max(total, 1):.0%})")
    for c in ("starts", "minutes", "r", "c"):
        df[c] = pd.to_numeric(df[c]).astype(int)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    df.to_pickle(CACHE)
    return df


def slot_name(formation, r, c, home):
    """FM position of row r, column c in a formation like '1-4-2-3-1'."""
    rows = [int(x) for x in formation.split("-")]
    R = len(rows)
    if r < 1 or r > R:
        return None
    n = rows[r - 1]
    if c < 1 or c > n:
        return None
    pos = n + 1 - c if home else c                  # 1 = leftmost
    end = "L" if pos == 1 else ("R" if pos == n else None)
    side = lambda left, right: left if end == "L" else right   # noqa: E731
    if r == 1:
        return "POR"
    back = rows[1]
    if r == 2:
        if n == 4 and end:
            return side("LI", "LD")
        if n >= 5 and end:
            return side("CAI", "CAD")
        return "DFC"
    if r == R:
        if n >= 3 and end:
            return side("EI", "ED")
        return "DC"
    k = R - 3                                          # midfield rows
    j = r - 2                                          # 1 = lowest midfield row
    if end and n >= 4:
        if back <= 3 and j == 1:
            return side("CAI", "CAD")
        if j == k and k >= 2:
            return side("EI", "ED")
        return side("MI", "MD")
    if end and n == 3 and j == k and k >= 2 and rows[-1] == 1:
        return side("EI", "ED")
    if k >= 2 and j == 1:                              # 2: both MCD · 3 (diamond): MCD in the middle
        return "MCD" if n <= 2 or (n == 3 and not end) else "MC"
    if k >= 2 and j == k:
        return "MCO" if n <= 3 else "MC"
    return "MC"


def player_slots(slots=None):
    """Slot rows with the FM name added."""
    s = pd.read_pickle(CACHE) if slots is None else slots
    key = s[["formation", "r", "c", "home"]].drop_duplicates()
    key["slot"] = [slot_name(f, r, c, h) for f, r, c, h in key.itertuples(index=False)]
    return s.merge(key, on=["formation", "r", "c", "home"], how="left")


def check(slots, rows):
    """Is column 1 the left? Compare listed Left/Right Backs in a back four, home and away separately."""
    listed = rows.drop_duplicates("player_id").set_index("player_id")["detailed_position"]
    s = slots.assign(listed=slots["player_id"].map(listed))
    b4 = s[(s["r"] == 2) & s["formation"].str.split("-").str[1].eq("4") & s["c"].isin([1, 4])]
    t = b4[b4["listed"].isin(["Left Back", "Right Back"])].pivot_table(
        index=["home", "listed"], columns="c", values="starts", aggfunc="sum").fillna(0)
    print("starts of listed full-backs in a back four, by column (1 vs 4):")
    print(t.astype(int).to_string())
    wing = s[s["listed"].isin(["Left Wing", "Right Wing"])]
    wing = player_slots(wing)
    print("\nlisted wingers -> slot (starts):")
    print(wing[wing["slot"].isin(["EI", "ED", "MI", "MD"])].pivot_table(
        index="listed", columns="slot", values="starts", aggfunc="sum").fillna(0).astype(int).to_string())
    away_lb = t.loc[(False, "Left Back")] if (False, "Left Back") in t.index else pd.Series(dtype=float)
    return away_lb.get(1, 0) >= away_lb.get(4, 0)


if __name__ == "__main__":
    from sm_features import player_seasons
    s = build()
    print(f"{len(s)} player-season-slot rows -> {CACHE}")
    left1 = check(s, player_seasons())
    print(f"\naway team: column 1 is the {'LEFT' if left1 else 'RIGHT'} side"
          + ("" if left1 else "  <-- Sportmonks changed the convention; update slot_name()"))
    print("\nformations seen (top 12):")
    f = s.groupby("formation")["starts"].sum().sort_values(ascending=False) / 11
    print(f.head(12).round(0).astype(int).to_string())

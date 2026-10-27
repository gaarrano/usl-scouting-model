"""
sm_features.py — Sportmonks player-match rows -> one row per player, season and team,
with the per-90 rates and success percentages the scouting models use.

Two data-quality rules applied here, once, so every model inherits them:
  1. Sportmonks omits a stat when its value is zero, so a missing key in a TRACKED row
     counts as 0. A row is "tracked" when it has Passes (the stat every tracked league
     records for anyone who played). Untracked rows (Uruguay-type gaps) are ignored:
     their minutes are not counted, so they don't dilute the per-90 rates.
  2. opp_touches = the opponents' average touches per match while he was on the pitch
     (minutes-weighted). Used to adjust defensive volume for possession: a CB on a team
     that keeps the ball faces fewer attacks, so he makes fewer duels and clearances.
  3. A league-season is usable only if >= 85% of players who played are tracked
     (see the summary of sportmonks_ingest.py). `season_tracked_share` carries it.

Usage (from other scripts):  from sm_features import player_seasons
Standalone:                  python scouting/sm_features.py   (rebuilds the cache)
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "database", "ingest"))

CACHE = os.environ.get("SM_CACHE") or os.path.join(os.path.dirname(__file__), "..", "data", "sm_player_season.pkl")
MIN_TRACKED_SHARE = 0.85

# Sportmonks stat names (sm_types.name) -> our column names
STATS = {
    "Minutes Played": "minutes", "Touches": "touches", "Passes": "passes",
    "Accurate Passes": "passes_acc", "Long Balls": "long_balls", "Long Balls Won": "long_balls_acc",
    "Total Duels": "duels", "Duels Won": "duels_won", "Aerials Won": "aerials_won",
    "Aerials Lost": "aerials_lost", "Clearances": "clearances", "Interceptions": "interceptions",
    "Possession Lost": "possession_lost", "Tackles": "tackles", "Fouls": "fouls",
    "Ball Recovery": "recoveries", "Goals": "goals", "Assists": "assists", "Key Passes": "key_passes",
    "Dribble Attempts": "dribbles", "Successful Dribbles": "dribbles_won", "Total Crosses": "crosses",
    "Accurate Crosses": "crosses_acc", "Shots Total": "shots", "Shots On Target": "shots_on_target",
    "Fouls Drawn": "fouls_drawn", "Dispossessed": "dispossessed", "Passes In Final Third": "final_third_passes",
}


def stat_ids(cur):
    """Map each stat name to the type_id that actually appears in the player rows
    (some names exist more than once in sm_types for other models)."""
    cur.execute("SELECT DISTINCT jsonb_object_keys(stats)::int FROM sm_player_match")
    present = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT type_id, name FROM sm_types WHERE name = ANY(%s)", (list(STATS),))
    ids = {}
    for tid, name in cur.fetchall():
        if tid in present:
            ids.setdefault(name, tid)
    missing = [n for n in STATS if n not in ids]
    if missing:
        print("not found in the loaded data (column will be NaN):", ", ".join(missing))
    return ids


def build():
    import db  # only needed to rebuild the cache from Postgres
    with db.transaction() as cur:
        ids = stat_ids(cur)
        passes = ids["Passes"]
        sums = ",\n".join(
            f"sum(CASE WHEN jsonb_typeof(pm.stats->'{tid}') = 'number' THEN (pm.stats->>'{tid}')::numeric ELSE 0 END)"
            f" FILTER (WHERE pm.stats ? '{passes}') AS {STATS[name]}"
            for name, tid in ids.items() if STATS[name] != "minutes")
        touches = ids.get("Touches")
        opp = ("NULL::numeric" if touches is None else
               f"sum(pm.minutes * ot.touches) FILTER (WHERE pm.stats ? '{passes}') "
               f"/ nullif(sum(pm.minutes) FILTER (WHERE pm.stats ? '{passes}' AND ot.touches IS NOT NULL), 0)")
        cur.execute(f"""
            WITH team_touches AS (            -- each team's total touches per match (possession proxy)
                SELECT fixture_id, team_id,
                       sum(CASE WHEN jsonb_typeof(stats->'{touches}') = 'number'
                                THEN (stats->>'{touches}')::numeric ELSE 0 END) AS touches
                FROM sm_player_match WHERE stats ? '{passes}' GROUP BY 1, 2)
            SELECT pm.player_id, f.season_id, pm.team_id,
                   max(CASE WHEN f.home_team_id = pm.team_id THEN f.home_team ELSE f.away_team END) AS team,
                   count(*) FILTER (WHERE pm.minutes > 0)                       AS apps,
                   count(*) FILTER (WHERE pm.starter)                           AS starts,
                   coalesce(sum(pm.minutes), 0)                                 AS minutes_all,
                   coalesce(sum(pm.minutes) FILTER (WHERE pm.stats ? '{passes}'), 0) AS minutes,
                   mode() WITHIN GROUP (ORDER BY pm.position_id)                AS match_position_id,
                   {opp}                                                        AS opp_touches,
                   {sums}
            FROM sm_player_match pm JOIN sm_fixtures f USING (fixture_id)
            LEFT JOIN team_touches ot ON ot.fixture_id = pm.fixture_id AND ot.team_id <> pm.team_id
            GROUP BY 1, 2, 3""")
        cols = [d[0] for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
        cur.execute(f"""
            SELECT f.season_id,
                   avg((pm.stats ? '{passes}')::int) FILTER (WHERE pm.minutes > 0) AS season_tracked_share
            FROM sm_player_match pm JOIN sm_fixtures f USING (fixture_id) GROUP BY 1""")
        q = pd.DataFrame(cur.fetchall(), columns=["season_id", "season_tracked_share"])
        cur.execute("SELECT season_id, league_id, league_name, country, season_name FROM sm_seasons")
        se = pd.DataFrame(cur.fetchall(), columns=["season_id", "league_id", "league", "country", "season"])
        cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'sm_players' AND column_name = 'us_link'")
        us_col = "p.us_link" if cur.fetchone() else "NULL::text"
        cur.execute(f"""SELECT p.player_id, p.display_name, p.name, p.date_of_birth, p.height_cm,
                              dp.name AS detailed_position, gp.name AS position, {us_col} AS us_link
                       FROM sm_players p
                       LEFT JOIN sm_types dp ON dp.type_id = p.detailed_position_id
                       LEFT JOIN sm_types gp ON gp.type_id = p.position_id""")
        pl = pd.DataFrame(cur.fetchall(), columns=["player_id", "display_name", "name", "dob", "height_cm",
                                                   "detailed_position", "position", "us_link"])
    df = df.merge(q, on="season_id").merge(se, on="season_id").merge(pl, on="player_id", how="left")
    for col in STATS.values():                  # stats absent from the data -> NaN column, not KeyError
        if col not in df.columns:
            df[col] = float("nan")
    num = sorted(set(STATS.values()) | {"minutes_all", "opp_touches"})
    df[num] = df[num].apply(pd.to_numeric, errors="coerce").astype(float)
    df["season_tracked_share"] = df["season_tracked_share"].astype(float)
    df["usable_season"] = df["season_tracked_share"] >= MIN_TRACKED_SHARE
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    df.to_pickle(CACHE)
    return df


# Team ids whose name can't be read from the fixtures (the lineups use an id the fixtures don't list, so the
# name query falls back to the opponent's name). Checked by hand from the roster: team 856 in 2025 is
# Knutson, Romero, Bonfiglio, Blanco, Hamid, Cardona, Mitrano... = Miami FC, not Tulsa (Tulsa is 1600).
TEAM_NAME_FIX = {856: "Miami FC"}
TEAM_RENAME = {"Miami FC II": "Miami FC"}       # Sportmonks' name for Miami FC's first team


def fix_team_names(df):
    """One name per team and season: hand-checked fixes first, then the most common name in that team-season."""
    df = df.copy()
    df["team"] = df["team"].replace(TEAM_RENAME)
    mode = df.groupby(["team_id", "season_id"])["team"].transform(lambda s: s.value_counts().index[0])
    df["team"] = mode
    fix = df["team_id"].map(TEAM_NAME_FIX)
    df.loc[fix.notna(), "team"] = fix[fix.notna()]
    return df


def player_seasons(rebuild=False):
    if rebuild or not os.path.exists(CACHE):
        return fix_team_names(build())
    return fix_team_names(pd.read_pickle(CACHE))


if __name__ == "__main__":
    d = build()
    print(f"{len(d)} player-season-team rows · {d['usable_season'].sum()} in usable league-seasons -> {CACHE}")

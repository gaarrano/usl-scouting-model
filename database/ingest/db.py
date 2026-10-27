"""
db.py — connection + get-or-create reconciliation helpers.
Project 1 · USL Event Database · Gabriel Arraño
"""
import os
import psycopg2
from contextlib import contextmanager

# Connection string. Set USL_DB_DSN in your environment / .env, e.g.
#   USL_DB_DSN="dbname=usl_db"
DSN = os.environ.get("USL_DB_DSN", "dbname=usl_db")


@contextmanager
def transaction():
    """Yield a cursor inside a single committed transaction.

    `with conn:` commits on clean exit and rolls back on exception, so an
    ingest either lands fully or not at all — no half-loaded matches.
    """
    conn = psycopg2.connect(DSN)
    try:
        with conn:                       # commit / rollback boundary
            with conn.cursor() as cur:
                yield cur
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Reconciliation: map a source identifier to one internal surrogate id,
# creating the dimension row + external-id mapping on first sight.
# ---------------------------------------------------------------------------
def get_or_create_team(cur, name, source="wyscout"):
    cur.execute(
        "SELECT team_id FROM team_external_ids WHERE source=%s AND source_team_id=%s",
        (source, name),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    # New to this source. Reuse the team if the name already exists, else create.
    cur.execute(
        "INSERT INTO teams (name) VALUES (%s) "
        "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (name,),
    )
    team_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO team_external_ids (team_id, source, source_team_id) "
        "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
        (team_id, source, name),
    )
    return team_id


def get_or_create_player(cur, label, source="wyscout"):
    """`label` is the Wyscout form '<number>. <surname>', e.g. '10. Hegardt'.

    LIMITATION (v1): keyed on the label alone. If a player changes shirt
    number between matches they would get two internal ids. Day 4 hardens
    this by resolving against the match roster (lineups) and ASA. Good enough
    to load and validate now.
    """
    cur.execute(
        "SELECT player_id FROM player_external_ids "
        "WHERE source=%s AND source_player_id=%s",
        (source, label),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    surname = label.split(". ", 1)[-1].strip() if ". " in label else label
    cur.execute(
        "INSERT INTO players (full_name, known_name) VALUES (%s, %s) RETURNING id",
        (surname, surname),
    )
    player_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO player_external_ids (player_id, source, source_player_id) "
        "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
        (player_id, source, label),
    )
    return player_id


def ensure_season(cur, name, competition):
    cur.execute(
        "INSERT INTO seasons (name, competition) VALUES (%s, %s) "
        "ON CONFLICT (name, competition) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (name, competition),
    )
    return cur.fetchone()[0]


def ensure_match(cur, season_id, match_date, home_team_id, away_team_id,
                 home_score, away_score, competition):
    """Idempotent on the natural key (date, home, away)."""
    cur.execute(
        "INSERT INTO matches (season_id, match_date, home_team_id, away_team_id, "
        "                     home_score, away_score, competition) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (match_date, home_team_id, away_team_id) DO UPDATE "
        "  SET home_score = EXCLUDED.home_score, away_score = EXCLUDED.away_score "
        "RETURNING id",
        (season_id, match_date, home_team_id, away_team_id,
         home_score, away_score, competition),
    )
    return cur.fetchone()[0]

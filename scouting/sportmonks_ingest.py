"""
sportmonks_ingest.py — load Sportmonks player-match statistics into usl_db (sm_* tables,
migration 004). One API call per finished match returns every player's stats.

Resumable: a match is written in its own transaction and marked lineups_loaded, so a
stopped run (rate limit, laptop closed) continues where it left off on the next run.
Re-running is cheap: loaded matches are skipped without an API call.

Token from the environment, never in code:   export SPORTMONKS_TOKEN="..."

Usage:
  python scouting/sportmonks_ingest.py --list                           # every league the token can see, with ids
  python scouting/sportmonks_ingest.py --leagues 791 663 666            # current season
  python scouting/sportmonks_ingest.py --leagues 791 663 666 --seasons 3  # + 2 previous
  python scouting/sportmonks_ingest.py --all --seasons 3                # every subscribed league
  python scouting/sportmonks_ingest.py --all --seasons 99 --raw-dir data/sportmonks_raw   # EVERYTHING the plan
                                              # allows, keeping each match's full JSON (gzip) for later re-parsing
  python scouting/sportmonks_ingest.py --all --seasons 3 --refetch --raw-dir data/sportmonks_raw
                                              # re-download every match already loaded, keeping the raw JSON
  python scouting/sportmonks_ingest.py --summary                        # what is loaded

Seasons outside the plan (the API answers 403/404 for them) are skipped with a note, not an error.
Each match call also asks for events and team statistics (--no-extras to skip); if the plan doesn't
include them the call is retried with the basic includes.

League ids: 791 USL Championship · 1607 USL League One · 2545 MLS Next Pro · 779 MLS
            663 Chile Primera · 666 Chile Primera B (full list: scouting/sportmonks_coverage.py)
"""
import argparse
import json
import os
import sys
import time

import requests
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "database", "ingest"))
import db  # noqa: E402

API = "https://api.sportmonks.com/v3"
TOKEN = os.environ.get("SPORTMONKS_TOKEN")
FINISHED = 5
STARTER, BENCH = 11, 12
FIXTURE_INCLUDE = "participants;scores;lineups.details;lineups.player"
EXTRA_INCLUDE = "events;statistics"        # goals/cards timeline + team totals: free with the same call
RAW_DIR = None                             # --raw-dir: keep every match's full JSON (gzip)
USE_EXTRAS = True
REFETCH = False                            # --refetch: reload matches already in the database (to get raw/extras)


# ---------------------------------------------------------------- HTTP
def get(path, **params):
    """GET with rate-limit handling. Sportmonks counts calls per entity per hour and
    reports what is left in every response; when the bucket is nearly empty we sleep
    until it resets instead of failing halfway through a season."""
    params["api_token"] = TOKEN
    for _ in range(5):
        r = requests.get(f"{API}/{path}", params=params, timeout=60)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 60))
            tqdm.write(f"   rate limited — sleeping {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        js = r.json()
        rl = js.get("rate_limit") or {}
        if rl.get("remaining") is not None and rl["remaining"] < 5:
            wait = int(rl.get("resets_in_seconds", 60)) + 5
            until = time.strftime("%H:%M", time.localtime(time.time() + wait))
            tqdm.write(f"   hourly {rl.get('requested_entity')} limit reached — paused until {until}")
            time.sleep(wait)
        return js
    sys.exit(f"gave up on {path} after repeated rate limiting")


def all_pages(path, **params):
    page, out = 1, []
    while True:
        js = get(path, page=page, per_page=50, **params)
        out += js.get("data") or []
        if not (js.get("pagination") or {}).get("has_more"):
            return out
        page += 1


# ---------------------------------------------------------------- reference data
def load_types(cur):
    """Every Sportmonks type id -> name (stats, positions, lineup types). Loaded once."""
    cur.execute("SELECT count(*) FROM sm_types")
    if cur.fetchone()[0]:
        return
    types = all_pages("core/types")
    for t in types:
        cur.execute("""INSERT INTO sm_types (type_id, name, code, developer_name, model_type, stat_group)
                       VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (type_id) DO NOTHING""",
                    (t["id"], t["name"], t.get("code"), t.get("developer_name"),
                     t.get("model_type"), t.get("stat_group")))
    print(f"{len(types)} Sportmonks types loaded")


def minutes_type_id(cur):
    cur.execute("SELECT type_id FROM sm_types WHERE developer_name = 'MINUTES_PLAYED'")
    row = cur.fetchone()
    return row[0] if row else None


def seasons_for(league_id, n_seasons):
    """The n most recent seasons of a league (current first). Plans include 3."""
    lg = get(f"football/leagues/{league_id}", include="seasons;country")["data"]
    seasons = sorted(lg.get("seasons") or [], key=lambda s: s.get("starting_at") or "", reverse=True)
    country = (lg.get("country") or {}).get("name")
    return lg["name"], country, seasons[:n_seasons]


# ---------------------------------------------------------------- one match
def scalar(v):
    """Stat values usually arrive as {'value': 7}; keep numbers as numbers."""
    if isinstance(v, dict) and set(v) == {"value"}:
        return v["value"]
    return v


def fetch_fixture(fx_id):
    """Full fixture JSON; extras dropped (for the rest of the run) if the plan rejects them."""
    global USE_EXTRAS
    inc = FIXTURE_INCLUDE + (";" + EXTRA_INCLUDE if USE_EXTRAS else "")
    try:
        js = get(f"football/fixtures/{fx_id}", include=inc)
    except requests.HTTPError as e:
        if USE_EXTRAS and e.response is not None and e.response.status_code in (400, 403):
            tqdm.write(f"   includes '{EXTRA_INCLUDE}' not available on this plan — continuing without them")
            USE_EXTRAS = False
            js = get(f"football/fixtures/{fx_id}", include=FIXTURE_INCLUDE)
        else:
            raise
    if RAW_DIR:
        import gzip
        d = os.path.join(RAW_DIR, str((js.get("data") or {}).get("season_id") or "unknown"))
        os.makedirs(d, exist_ok=True)
        with gzip.open(os.path.join(d, f"{fx_id}.json.gz"), "wt", encoding="utf-8") as fh:
            json.dump(js, fh, ensure_ascii=False)
    return js["data"]


def load_fixture(cur, fx_id, season_id, min_type):
    f = fetch_fixture(fx_id)
    side = {p["id"]: (p.get("meta") or {}).get("location") for p in f.get("participants") or []}
    names = {p["id"]: p["name"] for p in f.get("participants") or []}
    home = next((pid for pid, loc in side.items() if loc == "home"), None)
    away = next((pid for pid, loc in side.items() if loc == "away"), None)
    goals = {}
    for s in f.get("scores") or []:
        if s.get("description") == "CURRENT":
            goals[(s.get("score") or {}).get("participant")] = (s.get("score") or {}).get("goals")

    cur.execute("""INSERT INTO sm_fixtures (fixture_id, season_id, starting_at, home_team_id, home_team,
                                            away_team_id, away_team, home_goals, away_goals, state_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (fixture_id) DO UPDATE SET
                     starting_at = EXCLUDED.starting_at, home_goals = EXCLUDED.home_goals,
                     away_goals = EXCLUDED.away_goals, state_id = EXCLUDED.state_id, loaded_at = now()""",
                (fx_id, season_id, (f.get("starting_at") or None) and f["starting_at"] + "+00",
                 home, names.get(home), away, names.get(away),
                 goals.get("home"), goals.get("away"), f.get("state_id")))

    n = 0
    for lu in f.get("lineups") or []:
        if not lu.get("player_id"):
            continue
        p = lu.get("player") or {}
        cur.execute("""INSERT INTO sm_players (player_id, name, display_name, date_of_birth, height_cm, weight_kg,
                                               nationality_id, position_id, detailed_position_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (player_id) DO UPDATE SET
                         name = EXCLUDED.name, display_name = EXCLUDED.display_name,
                         date_of_birth = COALESCE(EXCLUDED.date_of_birth, sm_players.date_of_birth),
                         height_cm = COALESCE(EXCLUDED.height_cm, sm_players.height_cm),
                         weight_kg = COALESCE(EXCLUDED.weight_kg, sm_players.weight_kg),
                         nationality_id = COALESCE(EXCLUDED.nationality_id, sm_players.nationality_id),
                         position_id = COALESCE(EXCLUDED.position_id, sm_players.position_id),
                         detailed_position_id = COALESCE(EXCLUDED.detailed_position_id, sm_players.detailed_position_id),
                         updated_at = now()""",
                    (lu["player_id"], p.get("name") or lu.get("player_name") or "?", p.get("display_name"),
                     p.get("date_of_birth"), p.get("height"), p.get("weight"), p.get("nationality_id"),
                     p.get("position_id"), p.get("detailed_position_id")))
        stats = {str(d["type_id"]): scalar(d.get("data")) for d in lu.get("details") or [] if d.get("type_id")}
        mins = stats.get(str(min_type)) if min_type else None
        cur.execute("""INSERT INTO sm_player_match (fixture_id, player_id, team_id, starter, position_id,
                                                    formation_field, jersey_number, minutes, stats)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                       ON CONFLICT (fixture_id, player_id) DO UPDATE SET
                         team_id = EXCLUDED.team_id, starter = EXCLUDED.starter, position_id = EXCLUDED.position_id,
                         formation_field = EXCLUDED.formation_field, jersey_number = EXCLUDED.jersey_number,
                         minutes = EXCLUDED.minutes, stats = EXCLUDED.stats""",
                    (fx_id, lu["player_id"], lu.get("team_id"), lu.get("type_id") == STARTER,
                     lu.get("position_id"), lu.get("formation_field"), lu.get("jersey_number"),
                     int(mins) if isinstance(mins, (int, float)) else None, json.dumps(stats)))
        n += 1
    cur.execute("UPDATE sm_fixtures SET lineups_loaded = %s WHERE fixture_id = %s", (n > 0, fx_id))
    return n


# ---------------------------------------------------------------- driver
def ingest(league_ids, n_seasons):
    with db.transaction() as cur:
        load_types(cur)
        min_type = minutes_type_id(cur)

    # 1) plan: list every season's finished matches not loaded yet (cheap: 50 per call),
    #    so the progress bar knows the real total before the long part starts
    plan = []
    for league_id in tqdm(league_ids, desc="listing matches", unit="league"):
        league, country, seasons = seasons_for(league_id, n_seasons)
        for s in seasons:
            with db.transaction() as cur:
                cur.execute("""INSERT INTO sm_seasons (season_id, league_id, league_name, country, season_name,
                                                       starting_at, ending_at, is_current)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (season_id) DO UPDATE SET is_current = EXCLUDED.is_current,
                                 ending_at = EXCLUDED.ending_at""",
                            (s["id"], league_id, league, country, s["name"], s.get("starting_at"),
                             s.get("ending_at"), s.get("is_current")))
                cur.execute("SELECT fixture_id FROM sm_fixtures WHERE season_id = %s AND lineups_loaded", (s["id"],))
                done = set() if REFETCH else {r[0] for r in cur.fetchall()}
                if REFETCH and RAW_DIR:          # resumable: a match whose raw file exists is already re-fetched
                    d = os.path.join(RAW_DIR, str(s["id"]))
                    if os.path.isdir(d):
                        done = {int(x.split(".")[0]) for x in os.listdir(d) if x.endswith(".json.gz")}
            try:
                fixtures = all_pages("football/fixtures", filters=f"fixtureSeasons:{s['id']}")
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else "?"
                tqdm.write(f"   {country} {league} {s['name']}: not in the plan (HTTP {code}) — skipped")
                continue
            todo = [f["id"] for f in fixtures if f.get("state_id") == FINISHED and f["id"] not in done]
            plan.append((f"{country} {league} {s['name']}", s["id"], todo))
    total = sum(len(t) for _, _, t in plan)
    print(f"{total} matches to load across {len(plan)} league-seasons")

    # 2) load: one bar for the whole run; ETA includes the hourly-limit pauses
    empty = 0
    with tqdm(total=total, unit="match", smoothing=0.05,
              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed} elapsed, ~{remaining} left]") as bar:
        for label, season_id, todo in plan:
            bar.set_description(label[:38])
            for fx in todo:
                with db.transaction() as cur:          # one match = one transaction (resumable)
                    empty += load_fixture(cur, fx, season_id, min_type) == 0
                bar.update(1)
    if empty:
        print(f"{empty} finished matches came back without lineups (left unflagged; retried next run)")


def summary():
    with db.transaction() as cur:
        cur.execute("""SELECT se.country, se.league_name, se.season_name,
                              count(DISTINCT f.fixture_id) FILTER (WHERE f.lineups_loaded) AS matches,
                              count(pm.*) AS player_rows,
                              round(100.0 * avg((pm.stats ? (SELECT type_id::text FROM sm_types
                                                              WHERE developer_name = 'PASSES'))::int)
                                    FILTER (WHERE pm.minutes > 0), 0) AS pct_played_with_passes
                       FROM sm_seasons se
                       LEFT JOIN sm_fixtures f ON f.season_id = se.season_id
                       LEFT JOIN sm_player_match pm ON pm.fixture_id = f.fixture_id
                       GROUP BY 1, 2, 3 ORDER BY 1, 2, 3 DESC""")
        print(f"{'country':20s} {'league':28s} {'season':10s} {'matches':>7s} {'rows':>7s} {'%passes':>8s}")
        for c, lg, se, m, rows, pct in cur.fetchall():
            print(f"{c or '':20s} {lg:28s} {se:10s} {m:7d} {rows:7d} {str(pct):>8s}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", type=int, nargs="*", default=[])
    ap.add_argument("--all", action="store_true", help="every league the token can see")
    ap.add_argument("--seasons", type=int, default=1, help="most recent N seasons (plan includes 3)")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--list", action="store_true", help="leagues the token can see (id, country, name, seasons)")
    ap.add_argument("--raw-dir", default=None, help="folder to keep every match's full JSON (gzip)")
    ap.add_argument("--no-extras", action="store_true", help="don't ask for events/statistics")
    ap.add_argument("--refetch", action="store_true", help="reload matches already in the database (with --raw-dir, "
                                                            "matches whose raw file exists are skipped, so it resumes)")
    a = ap.parse_args()
    if a.summary:
        summary()
        sys.exit()
    if not TOKEN:
        sys.exit('set the token first:  export SPORTMONKS_TOKEN="..."')
    RAW_DIR = a.raw_dir
    USE_EXTRAS = not a.no_extras
    REFETCH = a.refetch
    if a.list:
        lgs = all_pages("football/leagues", include="country;seasons")
        print(f"{len(lgs)} leagues visible to this token\n{'id':>6s}  {'country':22s} {'league':34s} seasons")
        for lg in sorted(lgs, key=lambda x: ((x.get('country') or {}).get('name') or '', x['name'])):
            ss = sorted((s.get("name") or "" for s in lg.get("seasons") or []), reverse=True)
            print(f"{lg['id']:6d}  {((lg.get('country') or {}).get('name') or '')[:22]:22s} {lg['name'][:34]:34s} "
                  f"{len(ss)}: {', '.join(ss[:6])}{'…' if len(ss) > 6 else ''}")
        sys.exit()
    ids = a.leagues or ([lg["id"] for lg in all_pages("football/leagues")] if a.all else [])
    if not ids:
        sys.exit("give --leagues <ids> or --all")
    ingest(ids, a.seasons)
    summary()

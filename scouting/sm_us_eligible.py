"""
sm_us_eligible.py — find players in our 30 Sportmonks leagues with a link to the USA
(likely domestic for USL roster rules: they wouldn't use one of the 7 international slots).

Two signals Sportmonks gives (per its docs):
  country_id      = country of BIRTH. Born in the US => US citizen by birth.
  nationality_id  = the national team the player has chosen to represent.
So a player born in Miami who plays for Chile shows up via country_id; one born in England
who chose the USA (e.g. a US youth international) shows up via nationality_id.

NOT covered: US citizens born abroad to American parents, naturalised players and green-card
holders who represent another country. Transfermarkt's "Citizenship" line and the club's
roster office are the final word — this is a search tool, not an eligibility ruling.

Usage:
  python scouting/sm_us_eligible.py                 # fetch + flag + list
  python scouting/sm_us_eligible.py --position "Centre Back" --max-age 27
Output: scouting/output/us_linked_<date>.csv
API cost: one call per 50 US-born players (Player bucket, separate from Fixture).
"""
import argparse
import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "database", "ingest"))
import db  # noqa: E402
from sportmonks_ingest import TOKEN, all_pages, get  # noqa: E402


def usa_id():
    rows = get("core/countries/search/United States")["data"]
    exact = [c for c in rows if c["name"] in ("United States", "USA", "United States of America")]
    if not exact:
        sys.exit(f"could not identify the USA country id; candidates: {[(c['id'], c['name']) for c in rows]}")
    return exact[0]["id"]


def flag(us):
    born = all_pages(f"football/players/countries/{us}", select="id,country_id,nationality_id")
    with db.transaction() as cur:
        cur.execute("UPDATE sm_players SET us_link = NULL")
        ids = [p["id"] for p in born]
        cur.execute("UPDATE sm_players SET country_id = %s, us_link = 'born_us' WHERE player_id = ANY(%s)", (us, ids))
        n_born = cur.rowcount
        cur.execute("UPDATE sm_players SET us_link = coalesce(us_link || '+', '') || 'usa_national_team' "
                    "WHERE nationality_id = %s", (us,))
        n_nat = cur.rowcount
    print(f"USA id {us}: {len(born)} US-born players in Sportmonks · {n_born} of them in our leagues · "
          f"{n_nat} in our leagues represent the USA")


def listing(a, us):
    with db.transaction() as cur:
        cur.execute("""
            WITH last AS (
                SELECT DISTINCT ON (pm.player_id) pm.player_id, se.league_name, se.country, se.season_name,
                       CASE WHEN f.home_team_id = pm.team_id THEN f.home_team ELSE f.away_team END AS team
                FROM sm_player_match pm JOIN sm_fixtures f USING (fixture_id) JOIN sm_seasons se USING (season_id)
                WHERE pm.minutes > 0
                ORDER BY pm.player_id, f.starting_at DESC)
            SELECT p.player_id, p.display_name, p.date_of_birth, p.height_cm, dp.name AS position, p.us_link,
                   l.team, l.country AS league_country, l.league_name, l.season_name,
                   (SELECT coalesce(sum(pm.minutes), 0) FROM sm_player_match pm JOIN sm_fixtures f USING (fixture_id)
                     JOIN sm_seasons s2 USING (season_id)
                     WHERE pm.player_id = p.player_id AND s2.season_name = l.season_name) AS minutes_latest_season
            FROM sm_players p
            JOIN last l USING (player_id)
            LEFT JOIN sm_types dp ON dp.type_id = p.detailed_position_id
            WHERE p.us_link IS NOT NULL""")
        cols = [d[0] for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    df["age"] = ((pd.Timestamp(date.today()) - pd.to_datetime(df["date_of_birth"], errors="coerce"))
                 .dt.days / 365.25).round(1)
    if not a.include_us_leagues:     # the point is finding them OUTSIDE the US pyramid
        df = df[df["league_country"] != "United States"]
    df = df[df["season_name"].str[:4].astype(int) >= a.since]
    if a.position:
        df = df[df["position"].fillna("").str.lower() == a.position.lower()]
    if a.max_age:
        df = df[df["age"] <= a.max_age]
    df = df.sort_values(["minutes_latest_season"], ascending=False)
    os.makedirs(os.path.join(os.path.dirname(__file__), "output"), exist_ok=True)
    out = os.path.join(os.path.dirname(__file__), "output", f"us_linked_{date.today().isoformat()}.csv")
    df.to_csv(out, index=False)
    print(f"\n{len(df)} US-linked players{'' if a.include_us_leagues else ' outside US leagues'} "
          f"(born_us = born in the US; usa_national_team = represents the USA)")
    print(f"{'player':24s} {'age':>4s} {'pos':18s} {'link':22s} {'team':22s} {'league':28s} {'season':9s} {'min':>5s}")
    for r in df.head(a.top).itertuples():
        print(f"{(r.display_name or '')[:24]:24s} {r.age:4.0f} {str(r.position or '-')[:18]:18s} {r.us_link[:22]:22s} "
              f"{str(r.team)[:22]:22s} {(r.league_country + ' ' + r.league_name)[:28]:28s} {r.season_name:9s} "
              f"{int(r.minutes_latest_season):5d}")
    print(f"\n-> {out}\nVerify citizenship on Transfermarkt before treating anyone as domestic.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--position", help='Sportmonks detailed position, e.g. "Centre Back", "Left Back"')
    ap.add_argument("--max-age", type=float)
    ap.add_argument("--include-us-leagues", action="store_true")
    ap.add_argument("--no-fetch", action="store_true", help="skip the API, just list from the database")
    ap.add_argument("--since", type=int, default=2025, help="latest season must start this year or later")
    ap.add_argument("--top", type=int, default=50)
    a = ap.parse_args()
    if not TOKEN and not a.no_fetch:
        sys.exit('set the token first:  export SPORTMONKS_TOKEN="..."')
    us = None
    if not a.no_fetch:
        us = usa_id()
        flag(us)
    listing(a, us)

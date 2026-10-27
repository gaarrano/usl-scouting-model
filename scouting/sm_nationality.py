"""
sm_nationality.py — each player's nationality (the national team he chose, per Sportmonks) as a country name,
saved to data/sm_player_nationality.pkl so the app can filter by it without Postgres.

Countries come from the Sportmonks API (core/countries, about 5 calls); players' nationality_id from sm_players.

Run on the Mac (Postgres running, SPORTMONKS_TOKEN set):   python scouting/sm_nationality.py
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "database", "ingest"))

CACHE = os.environ.get("SM_NATIONALITY") or os.path.join(os.path.dirname(__file__), "..", "data",
                                                          "sm_player_nationality.pkl")


def build():
    import db
    from sportmonks_ingest import TOKEN, all_pages
    if not TOKEN:
        sys.exit("SPORTMONKS_TOKEN is not set (export it or load your .env first)")
    countries = {c["id"]: c["name"] for c in all_pages("core/countries", select="id,name")}
    with db.transaction() as cur:
        cur.execute("SELECT player_id, nationality_id FROM sm_players WHERE nationality_id IS NOT NULL")
        df = pd.DataFrame(cur.fetchall(), columns=["player_id", "nationality_id"])
    df["nationality"] = df["nationality_id"].map(countries)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    df.to_pickle(CACHE)
    return df, len(countries)


if __name__ == "__main__":
    d, n = build()
    print(f"{n} countries · {len(d)} players with a nationality · {d['nationality'].isna().sum()} unmatched -> {CACHE}")
    print(d["nationality"].value_counts().head(15).to_string())

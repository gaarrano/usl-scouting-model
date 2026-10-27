"""
shortlist_store.py — where the shortlist lives.

  * With a Google Sheet configured in Streamlit secrets, it is durable and shared (survives restarts and
    redeploys on Streamlit Cloud, and everyone who opens the app sees the same list).
  * Without it, it is a local JSON file (scouting/output/shortlist.json): fine on the Mac, NOT durable on
    Streamlit Cloud (wiped on every restart).

Secrets format (.streamlit/secrets.toml locally, or the app's Secrets box on Streamlit Cloud):

    [gsheets]
    sheet_url = "https://docs.google.com/spreadsheets/d/.../edit"
    [gsheets.service_account]
    type = "service_account"
    project_id = "..."
    private_key_id = "..."
    private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
    client_email = "...@....iam.gserviceaccount.com"
    client_id = "..."
    token_uri = "https://oauth2.googleapis.com/token"

Setup (once, ~10 minutes): see SHORTLIST_SETUP.md next to this file.
"""
import json
import os

import streamlit as st

LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "shortlist.json")
COLS = ["player_id", "name", "team", "position", "added", "status", "note"]
STATUSES = ["por ver", "visto", "descartado"]


def configured():
    try:
        return "gsheets" in st.secrets and "sheet_url" in st.secrets["gsheets"]
    except Exception:            # no secrets file at all
        return False


@st.cache_resource(show_spinner=False)
def _sheet():
    import gspread
    from google.oauth2.service_account import Credentials
    sa = dict(st.secrets["gsheets"]["service_account"])
    creds = Credentials.from_service_account_info(
        sa, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    gc = gspread.authorize(creds)
    book = gc.open_by_url(st.secrets["gsheets"]["sheet_url"])
    try:
        ws = book.worksheet("shortlist")
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet("shortlist", rows=200, cols=len(COLS))
        ws.append_row(COLS)
    if ws.row_values(1) != COLS:
        ws.update("A1", [COLS])
    return ws


def backend():
    """'gsheets' or 'local' — and, when the sheet is configured but unreachable, 'local' plus an error string."""
    if not configured():
        return "local", None
    try:
        _sheet()
        return "gsheets", None
    except Exception as e:    # noqa: BLE001 — any failure falls back to the local file, the page says why
        return "local", f"{type(e).__name__}: {e}"


def load():
    kind, _ = backend()
    if kind == "gsheets":
        rows = _sheet().get_all_records()
        out = {}
        for r in rows:
            try:
                pid = int(r["player_id"])
            except (KeyError, ValueError, TypeError):
                continue
            out[pid] = {k: ("" if r.get(k) is None else str(r.get(k))) for k in COLS if k != "player_id"}
            out[pid].setdefault("status", "por ver")
        return out
    try:
        with open(LOCAL) as f:
            d = {int(k): v for k, v in json.load(f).items()}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    for v in d.values():
        v.setdefault("status", "por ver")
    return d


def save(sl):
    kind, _ = backend()
    if kind == "gsheets":
        ws = _sheet()
        body = [COLS] + [[pid] + [str(v.get(k, "")) for k in COLS[1:]] for pid, v in sl.items()]
        ws.clear()
        ws.update("A1", body)
        return
    os.makedirs(os.path.dirname(LOCAL), exist_ok=True)
    with open(LOCAL, "w") as f:
        json.dump({str(k): v for k, v in sl.items()}, f, ensure_ascii=False, indent=1)

"""
app_v2.py — Miami FC scouting app, version 2 (player card + shortlist). app.py stays as it was.

Pages:
  Inicio        — front door: three tasks (replace a Miami player / search by position / shortlist), recent searches
  Buscar        — whole-database search by position (pitch) with filters; clicking a player opens his card
  Ficha         — player card: who he is now, where he plays (pitch), his numbers by block coloured vs
                  his position, radar vs a Miami player, similar players, season history; add to shortlist
  Comparar      — position radar for up to four players
  Lista corta   — saved players with notes (scouting/output/shortlist.json), exportable

Run (from the repo root), next to app.py:
  python -m streamlit run scouting/app_v2.py --server.port 8502
Local only: never deploy (licensed data, private repo).
"""
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import es_names as es  # noqa: E402
import i18n  # noqa: E402
import export  # noqa: E402
import market  # noqa: E402
import position_model  # noqa: E402
import radar  # noqa: E402
import sm_nationality  # noqa: E402
import sm_slots  # noqa: E402
from fit import apply_filters, miami_players, rank  # noqa: E402
import sm_features  # noqa: E402
from sm_features import player_seasons  # noqa: E402
from sm_metrics import outfield_pool  # noqa: E402

import shortlist_store  # noqa: E402
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8983", "#e4e3df", "#fcfcfb"
BLUE = "#2a78d6"                 # OUR player (Miami / reference) everywhere: app radars, cards, PDF
OTHER = "#e8590c"                # the player being looked at (orange: distinguishable from blue for colour-blind readers)
GOOD, BAD = "#0f7b6c", "#d9480f"   # percentile colours (teal / orange) — always paired with ▲ ▼ glyphs
POS_ES = {"ST": "Delantero centro (DC)", "W": "Extremo (EI/ED)", "AM": "Mediapunta (MCO)",
          "CM": "Mediocentro (MED)", "FB": "Lateral (LD/LI)", "CB": "Defensa central (DFC)"}
GROUP_ES = {"ST": "delantero centro", "W": "extremo", "AM": "mediapunta", "CM": "mediocentro",
            "FB": "lateral", "CB": "defensa central"}
PLURAL_ES = {"ST": "delanteros centro", "W": "extremos", "AM": "mediapuntas", "CM": "mediocentros",
             "FB": "laterales", "CB": "defensas centrales"}
BLOCKS = {
    "Ataque": ["goals", "shots", "sot_pct", "fouls_drawn"],
    "Creación": ["assists", "key_passes", "final_third", "dribbles", "dribble_pct", "crosses", "cross_pct"],
    "Pase": ["touches", "passes", "pass_pct", "long", "long_pct"],
    "Duelos": ["duel_pct", "aerials", "aerial_pct"],
    "Defensa": ["tackles", "interceptions", "clearances", "recoveries"],
}
BLOCK_ORDER = {"ST": ["Ataque", "Creación", "Duelos", "Pase", "Defensa"],
               "W": ["Ataque", "Creación", "Pase", "Duelos", "Defensa"],
               "AM": ["Creación", "Ataque", "Pase", "Duelos", "Defensa"],
               "CM": ["Pase", "Defensa", "Creación", "Duelos", "Ataque"],
               "FB": ["Defensa", "Duelos", "Creación", "Pase", "Ataque"],
               "CB": ["Defensa", "Duelos", "Pase", "Creación", "Ataque"]}
PALETTE = [BLUE, OTHER, "#b8860b", "#52514e"]   # reference first, then the others

st.set_page_config(page_title="Miami FC · Scouting", page_icon="⚽", layout="wide", initial_sidebar_state="auto")
i18n.install()                 # English mode: every Streamlit text call is translated when lang == "en"
st.markdown(f"""<style>
  .block-container {{padding-top: 3.2rem; max-width: 1300px;}}
  .note {{color:{INK2}; font-size:0.85rem;}}
  .card {{background:#f4f4f2; border-radius:10px; padding:14px 18px; margin-bottom:10px;}}
  .hname {{font-size:2.3rem !important; font-weight:800; color:{INK}; line-height:1.15; margin:0;}}
  .hsub {{color:{INK2}; font-size:0.95rem; margin-top:4px;}}
  .chips span {{display:inline-block; background:#ffffff; border:1px solid {GRID}; border-radius:999px;
               padding:3px 10px; margin:6px 6px 0 0; font-size:0.82rem; color:{INK};}}
  .blk h4 {{margin:0 0 6px 0; font-size:0.78rem; letter-spacing:.06em; text-transform:uppercase; color:{INK2};}}
  .row {{display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid {GRID}; padding:4px 0;
         font-size:0.9rem;}}
  .row span {{color:{INK2};}}
  .blk {{margin-bottom:14px;}}
  .row b {{font-variant-numeric: tabular-nums;}}
  [data-testid="stSidebar"] [data-testid="stElementToolbar"] {{display:none;}}
  .hi {{color:{GOOD};}} .lo {{color:{BAD};}} .mid {{color:{INK};}} .na {{color:{MUTED};}}
  [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {{display:none;}}
  .fsec {{font-size:0.74rem; letter-spacing:.08em; text-transform:uppercase; color:{INK2}; font-weight:700;
          margin:18px 0 2px 0; border-bottom:1px solid {GRID}; padding-bottom:3px;}}
  .rk {{font-size:1.5rem; font-weight:800; color:{MUTED}; padding-top:6px; text-align:center;}}
  .cname {{font-size:1.25rem; font-weight:800; color:{INK}; line-height:1.2; margin:0;}}
  .csub {{color:{INK2}; font-size:0.86rem; margin:2px 0 0 0;}}
  .simnum {{font-size:1.9rem; font-weight:800; color:{BLUE}; line-height:1; font-variant-numeric:tabular-nums;}}
  .simnum small {{font-size:0.8rem; color:{INK2}; font-weight:600;}}
  .simlab {{font-size:0.72rem; letter-spacing:.06em; text-transform:uppercase; color:{INK2}; margin-bottom:4px;}}
  .bar {{height:7px; border-radius:99px; background:{GRID}; margin-top:6px; overflow:hidden;}}
  .bar i {{display:block; height:100%; background:linear-gradient(90deg,#9cc3f0,{BLUE}); border-radius:99px;}}
  .lvl {{display:inline-block; border-radius:999px; padding:4px 11px; font-size:0.85rem; font-weight:700;}}
  .lvl.up {{background:#e0f2ef; color:{GOOD};}} .lvl.eq {{background:#eeeeec; color:{INK2};}}
  .lvl.dn {{background:#fbe9e0; color:{BAD};}}
  .headline {{font-size:1.05rem; color:{INK}; background:#f4f4f2; border-left:4px solid {BLUE}; padding:10px 14px;
              border-radius:0 8px 8px 0; margin:8px 0 6px 0; line-height:1.45;}}
  .why {{font-size:0.84rem; color:{INK2}; margin-top:6px;}} .why b {{color:{INK};}}
  .home h3 {{margin:0 0 4px 0;}} .home p {{color:{INK2}; margin:0 0 10px 0;}}
  .navlink a {{text-decoration:none;}}
  @media (max-width: 640px) {{
    .block-container {{padding-top: 2.4rem; padding-left:0.9rem; padding-right:0.9rem;}}
    .hname {{font-size:1.6rem !important;}} .simnum {{font-size:1.5rem;}}
    .cname {{font-size:1.05rem;}} .rk {{text-align:left; padding-top:0;}}
  }}
</style>""", unsafe_allow_html=True)


def data_date():
    """When the Sportmonks cache was last rebuilt (shown on every page: 'actualizado 20 oct 2026')."""
    try:
        t = os.path.getmtime(sm_features.CACHE)
    except OSError:
        return "—"
    from datetime import datetime
    d = datetime.fromtimestamp(t)
    meses = (["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] if i18n.lang() == "en"
             else ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"])
    return f"{d.day} {meses[d.month - 1]} {d.year}"


# ─────────────────────────────── data ───────────────────────────────
@st.cache_data(show_spinner="Cargando la base: 30 ligas, 3 temporadas, ~55.000 temporadas de jugador (solo demora la "
                              "primera vez)…")
def load_rows():
    return player_seasons()            # team names already fixed in sm_features.fix_team_names


@st.cache_data(show_spinner="Comparando el perfil con todos los jugadores de la posición…")
def cached_rank(g, players):
    return rank(g, None, list(players), allrows=load_rows())


@st.cache_data(show_spinner="Cargando jugadores…")
def player_index():
    pool = outfield_pool(load_rows(), 600)
    last = pool.sort_values(["start", "minutes"]).groupby("player_id").tail(1)
    last = last[last["start"] >= 2024].sort_values("minutes", ascending=False)
    lab = (last["display_name"].astype(str) + " — " + last["team"].astype(str) + " (" +
           last["country"].map(es.country) + ", " + last["season"].astype(str) + ")")
    return dict(zip(last["player_id"], lab))


@st.cache_resource(show_spinner="Preparando el modelo de posiciones (solo la primera vez)…")
def position_classifier():
    rows = load_rows()
    model, _, _, _ = position_model.train(rows, cv=False)       # CV numbers come from the saved file
    acc, top2 = position_model.saved_cv()
    if acc is None:
        _, _, acc, top2 = position_model.train(rows, cv=True)
    return model, position_model.scoring_frame(rows), acc, top2


@st.cache_data(show_spinner=False)
def values(ids, n_seasons=2):
    return radar.two_season_values(load_rows(), list(ids), n_seasons=n_seasons)


@st.cache_data(show_spinner="Calculando referencias por posición…")
def group_values(g):
    """Two-season values of every active player whose listed position is in group g (for colouring)."""
    pool = outfield_pool(load_rows(), 600)
    ids = pool[(pool["group"] == g) & (pool["start"] >= 2024)]["player_id"].unique()
    return radar.two_season_values(load_rows(), list(ids))


@st.cache_data(show_spinner=False)
def axis_ranges(g):
    """Fixed radar scale for position g (5th-95th percentile of the position's players)."""
    return radar.ranges(group_values(g), g)


@st.cache_data(show_spinner=False)
def now_info(pid):
    """Current club (latest row, any minutes), share of the team's minutes this season."""
    r = load_rows()
    r = r.assign(s0=pd.to_numeric(r["season"].astype(str).str[:4], errors="coerce"))
    r["team_games"] = r.groupby(["team_id", "season_id"])["apps"].transform("max")
    me = r[r["player_id"] == pid].sort_values(["s0", "minutes_all"])
    if me.empty:
        return None
    last = me.iloc[-1]
    share = last["minutes_all"] / (90 * last["team_games"]) if last["team_games"] > 0 else np.nan
    return {"team": last["team"], "league": es.league(last["league"]), "country": es.country(last["country"]),
            "league_raw": last["league"], "country_raw": last["country"],
            "season": last["season"], "minutes": last["minutes_all"], "share": min(share, 1.0),
            "apps": last["apps"], "starts": last["starts"], "dob": last["dob"], "height": last["height_cm"],
            "us_link": last.get("us_link"), "name": last["display_name"], "listed": last["detailed_position"]}


@st.cache_data(show_spinner=False)
def miami_roster():
    """Miami players with a usable season (needed for the model), their seasons at the club, and whether they
    were in the current season's squad. Former players are labelled as such."""
    rows = load_rows()
    mp = miami_players(rows).copy()
    m = rows[rows["team"].eq("Miami FC") & rows["minutes_all"].gt(0)]
    seasons = m.groupby("player_id")["season"].apply(lambda x: sorted(set(map(str, x))))
    cur = max(map(str, m["season"]))
    mp["seasons"] = mp["player_id"].map(seasons).apply(lambda v: v if isinstance(v, list) else [])
    mp["current"] = mp["seasons"].apply(lambda v: cur in v)
    mp["label"] = np.where(mp["current"], mp["display_name"] + " · Miami " + mp["seasons"].str.join(", "),
                           mp["display_name"] + " · ex Miami (" + mp["seasons"].str.join(", ") + ")")
    few = mp["best_season"] < 600
    mp.loc[few, "label"] = mp.loc[few, "label"] + " · pocos minutos (" + \
        mp.loc[few, "best_season"].round(0).astype(int).astype(str) + ")"
    return mp.sort_values(["current", "minutes"], ascending=[False, False]), cur


def miami_picker(label, key, default_name=None, multi=True, group=None, default_id=None):
    """Selector of Miami players: current squad by default, former players only if asked."""
    mp, cur = miami_roster()
    ex = st.toggle("Incluir ex jugadores de Miami", value=False, key=f"{key}_ex",
                   help=f"Por defecto solo el plantel {cur}.")
    opts = mp if ex else mp[mp["current"]]
    if default_id is not None and default_id not in set(opts["player_id"]):
        opts = pd.concat([mp[mp["player_id"] == default_id], opts])
    if group is not None and (opts["group"] == group).any():
        opts = pd.concat([opts[opts["group"] == group], opts[opts["group"] != group]])
    if default_id is not None and (opts["player_id"] == default_id).any():
        opts = pd.concat([opts[opts["player_id"] == default_id], opts[opts["player_id"] != default_id]])
    labels = opts.set_index("player_id")["label"].to_dict()
    ids = list(labels)
    if multi:
        dflt = [i for i in ids if default_name and default_name.lower() in labels[i].lower()][:1]
        return st.multiselect(label, ids, default=dflt, format_func=labels.get, key=key), labels
    return st.selectbox(label, ids, format_func=labels.get, key=key), labels


def load_shortlist():
    try:
        return shortlist_store.load()
    except Exception as e:     # noqa: BLE001
        st.session_state["sl_error"] = str(e)
        return {}


def save_shortlist(sl):
    shortlist_store.save(sl)


def why_similar(row, template, weights, ref_short, n_same=3, n_diff=2):
    """'Se parece en: remates, toques · Más que Locadia: regates · Menos: asistencias' from the per-stat z gaps."""
    gaps = []
    for f, w in weights.items():
        z, t = row.get("z_" + f), template.get("z_" + f)
        if z is None or t is None or pd.isna(z) or pd.isna(t) or f not in es.FEATURE_ES:
            continue
        gaps.append((abs(z - t) * np.sqrt(w), z - t, f))
    if not gaps:
        return ""
    gaps.sort()
    top_w = sorted(weights.values(), reverse=True)[:max(6, len(weights) // 2)]
    important = [x for x in gaps if weights[x[2]] >= top_w[-1]]      # the position's most stable stats
    same = [es.FEATURE_ES[f] for _, _, f in (important or gaps)[:n_same]]
    diff = sorted(gaps, reverse=True)[:n_diff]
    more = [es.FEATURE_ES[f] for _, d, f in diff if d > 0.35]
    less = [es.FEATURE_ES[f] for _, d, f in diff if d < -0.35]
    out = f"<b>Se parece en:</b> {', '.join(same)}"
    if more:
        out += f" · <b>Más que {ref_short}:</b> {', '.join(more)}"
    if less:
        out += f" · <b>Menos que {ref_short}:</b> {', '.join(less)}"
    return out


def headline(row, ref, g):
    """One plain sentence for the top of the card, from his percentiles among the position's players."""
    many, few = [], []
    for k in radar.RADAR[g]:
        v, ok = row.get(k), ref[k].dropna()
        if v is None or pd.isna(v) or len(ok) < 30:
            continue
        pct = (ok < v).mean()
        if pct >= 0.8:
            many.append((pct, k))
        elif pct <= 0.2:
            few.append((pct, k))
    many = [es.many(k) for _, k in sorted(many, reverse=True)[:3]]
    few = [es.few(k) for _, k in sorted(few)[:2]]
    pos = GROUP_ES[g].capitalize()
    if many and few:
        return f"{pos} con {', '.join(many)} (entre el 20% más alto de los {PLURAL_ES[g]}); {', '.join(few)}."
    if many:
        return f"{pos} con {', '.join(many)} (entre el 20% más alto de los {PLURAL_ES[g]})."
    if few:
        return f"{pos} sin estadísticas en las que destaque frente a los {PLURAL_ES[g]}; {', '.join(few)}."
    return f"{pos} de números parejos: nada muy por encima ni muy por debajo de los {PLURAL_ES[g]}."


def candidate_card(i, r, g, refs, ref_short, why, nat, sl, compact=False, origin=None):
    """One result card (Parecidos page and the card's 'parecidos' tab)."""
    sim = int(min(r.similarity, 100))
    lv = r.level
    lvl = (("up", "Por encima") if lv >= 0.3 else ("dn", "Por debajo") if lv <= -0.3 else ("eq", "En el promedio"))
    chips = [f"{r.age:.0f} años" if pd.notna(r.age) else None,
             f"{r.height_cm:.0f} cm" if pd.notna(r.height_cm) else None,
             es.country(nat.get(r.player_id)) if nat is not None and nat.get(r.player_id) else None,
             f"{100 * r.now_min_share:.0f}% de los minutos en {r.now_season}" if pd.notna(r.now_min_share) else None,
             None if compact else f"{int(r.minutes_used):,} min analizados".replace(",", "."),
             "vínculo con EE.UU." if isinstance(r.us_link, str) else None]
    star = "★ " if r.player_id in sl else ""
    with st.container(border=True):
        c0, c1, c2, c3, c4 = st.columns([0.5, 3.8, 1.5, 1.4, 1.8], vertical_alignment="center")
        c0.markdown(f"<div class='rk'>#{i}</div>", unsafe_allow_html=True)
        c1.markdown(f"<p class='cname'>{star}{r.display_name}</p>"
                    f"<p class='csub'>{r.now_team} · {es.country(r.now_country)} · {es.league(r.now_league)}</p>"
                    "<div class='chips'>" + "".join(f"<span>{c}</span>" for c in chips if c) + "</div>"
                    + (f"<p class='why'>{why}</p>" if why else ""), unsafe_allow_html=True)
        c2.markdown(f"<div class='simlab'>Parecido a {ref_short}</div>"
                    f"<div class='simnum'>{sim}<small> / 100</small></div>"
                    f"<div class='bar'><i style='width:{sim}%'></i></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='simlab'>Nivel en su liga</div><span class='lvl {lvl[0]}'>{lvl[1]}</span>",
                    unsafe_allow_html=True)
        if c4.button("📊 Comparar", key=f"cmp_{g}_{refs[0]}_{r.player_id}", type="primary", width="stretch",
                     help=f"Radar lado a lado con {ref_short}, listo para descargar"):
            if origin:
                remember_back(*origin)
            open_compare(list(refs) + [r.player_id], g)
        if c4.button("Ver ficha", key=f"card_{g}_{refs[0]}_{r.player_id}", width="stretch"):
            if origin:
                remember_back(*origin)
            open_card(r.player_id, ref=refs[0], g=g)


BACK_LABELS = {"buscar": "Buscar jugadores", "parecidos": "Parecidos a Miami FC", "lista": "Lista corta",
               "ficha": "Ficha", "comparar": "Comparar", "inicio": "Inicio"}


def remember_back(here, pid=None):
    """Called by the page a player is opened FROM. List pages (Parecidos, Buscar, Lista) are roots: they reset the
    trail; a Ficha that opens another Ficha / Comparar is pushed on top, so '← Volver' can walk back."""
    entry = {"page": here, "pid": pid}
    if here in ("parecidos", "buscar", "lista"):
        st.session_state["back_stack"] = [entry]
    else:
        stack = st.session_state.get("back_stack", [])
        if not stack or stack[-1] != entry:
            stack.append(entry)
        st.session_state["back_stack"] = stack[-6:]


def back_button():
    """'← Volver a …' to the page the player was opened from (Streamlit has no back button)."""
    stack = st.session_state.get("back_stack", [])
    if not stack or stack[-1]["page"] not in PAGES:
        return
    b = stack[-1]
    if b["page"] == "ficha" and b.get("pid") == st.session_state.get("player_id") and nav_current() == "ficha":
        return                                   # we are already on that card
    who = (now_info(b["pid"]) or {}).get("name") if b.get("pid") else None
    label = f"← Volver a {BACK_LABELS[b['page']]}" + (f" de {who}" if who else "")
    if st.button(label, key="back_btn"):
        st.session_state["back_stack"] = stack[:-1]
        if b.get("pid"):
            st.session_state["player_id"] = int(b["pid"])
            st.session_state["card_ref"] = None
        st.switch_page(PAGES[b["page"]])


def nav_current():
    return st.session_state.get("_current_page")


def open_card(pid, ref=None, g=None):
    """Open a player's card. With ref (a Miami player) and g, the card's radar starts on that comparison."""
    st.session_state["player_id"] = int(pid)
    st.session_state["card_ref"] = {"pid": int(pid), "ref": int(ref), "g": g} if ref is not None else None
    st.switch_page(PAGE_CARD)


def open_compare(ids, g):
    """Open Comparar with exactly these players (first = reference) on position g's radar."""
    st.session_state["cmp_preset"] = {"ids": [int(i) for i in ids], "g": g}
    st.switch_page(PAGE_COMPARE)


def add_recent(kind, label, payload):
    """Keep the last three searches (this session) for the Inicio page."""
    rec = [r for r in st.session_state.get("recent", []) if r["label"] != label]
    st.session_state["recent"] = ([{"kind": kind, "label": label, "payload": payload}] + rec)[:3]


def age_of(dob):
    d = pd.to_datetime(dob, errors="coerce")
    return None if pd.isna(d) else int((pd.Timestamp(date.today()) - d).days // 365.25)


def fmt(v, kind):
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.0f}%" if kind == "pct" else f"{v:.2f}"


# ─────────────────────────────── pitch ───────────────────────────────
def pitch_positions(probs, listed):
    """Mini vertical pitch: one circle per position group, size and opacity by probability."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Arc, Circle, Rectangle

    left = isinstance(listed, str) and listed.startswith("Left")
    spots = {"ST": (34, 92), "W": (10 if left else 58, 80), "AM": (34, 74), "CM": (34, 56),
             "FB": (8 if left else 60, 30), "CB": (34, 18)}
    fig, ax = plt.subplots(figsize=(3.0, 4.3), dpi=160)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor("#eef4ee")
    lc = "#b9c8b9"
    ax.add_patch(Rectangle((0, 0), 68, 105, fill=False, ec=lc, lw=1.2))
    ax.plot([0, 68], [52.5, 52.5], color=lc, lw=1)
    ax.add_patch(Circle((34, 52.5), 9.15, fill=False, ec=lc, lw=1))
    for y0, d in ((0, 1), (105, -1)):
        ax.add_patch(Rectangle((13.85, y0 if d == 1 else y0 - 16.5), 40.3, 16.5, fill=False, ec=lc, lw=1))
        ax.add_patch(Rectangle((24.85, y0 if d == 1 else y0 - 5.5), 18.3, 5.5, fill=False, ec=lc, lw=1))
    ax.add_patch(Arc((34, 11), 18.3, 18.3, theta1=37, theta2=143, ec=lc, lw=1))
    ax.add_patch(Arc((34, 94), 18.3, 18.3, theta1=217, theta2=323, ec=lc, lw=1))
    for g, (x, y) in spots.items():
        p = float(probs.get(g, 0)) if probs is not None else 0.0
        if p < 0.03:
            ax.add_patch(Circle((x, y), 2.2, color="#c9cfc9", zorder=3))
            continue
        ax.add_patch(Circle((x, y), 3 + 7 * p, color=BLUE, alpha=0.25 + 0.7 * p, zorder=3, lw=0))
        ax.text(x, y, f"{100 * p:.0f}%", ha="center", va="center", fontsize=7.5,
                color="white" if p > 0.35 else INK, fontweight="bold", zorder=4)
    ax.set_xlim(-2, 70)
    ax.set_ylim(-2, 107)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.annotate("", xy=(71, 100), xytext=(71, 70), arrowprops=dict(arrowstyle="->", color=MUTED, lw=1),
                annotation_clip=False)
    fig.subplots_adjust(0, 0, 1, 1)
    return fig


# ─────────────────────────────── shared widgets ───────────────────────────────
LEVEL_OPTS = {"any": ("Cualquiera", -9.0), "avg": ("Promedio de su liga o más", 0.0),
              "up": ("Por encima de su liga", 0.3), "top": ("Muy por encima", 0.6)}
SHARE_OPTS = {10: "A veces", 30: "Habitualmente", 70: "Casi siempre"}
MARKET_HELP = ("Saca a los titulares habituales de clubes en ligas más fuertes (MLS, primera de Argentina, Serie B "
               "de Brasil, primera de Colombia, League One): en principio no vendrían a la USL. Los suplentes de "
               "esas ligas sí aparecen.")
US_HELP = "Nacido en EE.UU. o seleccionado de EE.UU.: en principio no ocuparía plaza de extranjero. Confirmar caso a caso."


def fsec(title):
    st.markdown(f"<div class='fsec'>{title}</div>", unsafe_allow_html=True)


def reset_button(prefix, keep=(), label="Restablecer filtros"):
    """Clears every widget whose key starts with `prefix_` (except those starting with one of `keep`)."""
    if st.button(label, key=f"{prefix}__reset", width="stretch"):
        for k in list(st.session_state):
            if k.startswith(prefix + "_") and not any(k.startswith(x) for x in keep):
                del st.session_state[k]
        st.rerun()


def player_filters(prefix, level=True, seasons_note="de sus dos últimas temporadas"):
    """The sidebar filters every search page shares. Each control says in words what it does.
    Returns dict(age, height, minutes, level, realista, us, chips)."""
    f = {}
    fsec("Jugador")
    f["age"] = st.slider("Edad", 16, 40, (18, 30), key=f"{prefix}_age", format="%d años")
    a, b = f["age"]
    st.caption("Cualquier edad" if (a, b) == (16, 40) else f"De {a} a {b} años")
    f["height"] = st.slider("Estatura mínima", 150, 200, 150, key=f"{prefix}_h", format="%d cm")
    st.caption("Sin mínimo de estatura" if f["height"] == 150 else f"{f['height']} cm o más")
    fsec("Cuánto ha jugado")
    f["minutes"] = st.slider("Minutos jugados (mínimo)", 600, 4000, 1200, step=100, key=f"{prefix}_min",
                             format="%d min")
    st.caption(f"Al menos {f['minutes']:,} minutos {seasons_note} (≈ {f['minutes'] // 90} partidos completos)"
               .replace(",", "."))
    if level:
        fsec("Nivel")
        lv = st.segmented_control("Nivel en su liga", list(LEVEL_OPTS), default="avg", key=f"{prefix}_lvl",
                                  format_func=lambda k: LEVEL_OPTS[k][0],
                                  help="Qué tan bien hace las cosas (% de pases, duelos, regates…) comparado con "
                                       "los jugadores de su posición en su propia liga.") or "avg"
        f["level"] = LEVEL_OPTS[lv][1]
        f["level_key"] = lv
    fsec("Mercado")
    f["realista"] = st.toggle("Solo fichajes realistas para la USL", value=True, key=f"{prefix}_real",
                              help=MARKET_HELP)
    f["us"] = st.toggle("Solo con vínculo con EE.UU.", value=False, key=f"{prefix}_us", help=US_HELP)
    chips = ["Cualquier edad" if (a, b) == (16, 40) else f"{a}–{b} años",
             f"{f['height']}+ cm" if f["height"] > 150 else None,
             f"{f['minutes']:,}+ min".replace(",", "."),
             (LEVEL_OPTS[f["level_key"]][0] if level and f["level_key"] != "any" else None),
             "mercado realista" if f["realista"] else "todos los mercados",
             "vínculo con EE.UU." if f["us"] else None]
    f["chips"] = [c for c in chips if c]
    return f


def show_chips(items, prefix="Filtros: "):
    st.markdown(f"<p class='note' style='margin-bottom:2px'>{prefix}</p><div class='chips' style='margin-top:-6px'>"
                + "".join(f"<span>{c}</span>" for c in items if c) + "</div>", unsafe_allow_html=True)


def sidebar_search():
    idx = player_index()
    with st.sidebar:
        cur = i18n.lang()
        choice = st.segmented_control("Idioma", list(i18n.LANGS), default=cur, format_func=i18n.LANGS.get,
                                      key=f"lang_w_{cur}", label_visibility="collapsed")
        if choice and choice != cur:
            st.session_state["lang"] = choice
            st.query_params["lang"] = choice
            st.rerun()
        st.page_link(PAGES["inicio"], label="Inicio", icon="🏠")
        st.page_link(PAGES["parecidos"], label="Parecidos a Miami FC", icon="🧬")
        st.page_link(PAGES["buscar"], label="Buscar por posición", icon="🔎")
        st.page_link(PAGES["comparar"], label="Comparar", icon="📊")
        st.page_link(PAGES["lista"], label="Lista corta", icon="⭐")
        cur = st.session_state.get("player_id")
        if cur is not None and (now_info(cur) or {}).get("name"):
            st.page_link(PAGES["ficha"], label=f"Ficha: {now_info(cur)['name']}", icon="🪪")
        st.caption(f"Datos: Sportmonks · actualizado {data_date()} · Gabriel Arraño")
        st.markdown("**Buscar jugador**")
        pid = st.selectbox("Buscar jugador", [None] + list(idx), index=0, label_visibility="collapsed",
                           format_func=lambda i: "Escribe un nombre…" if i is None else idx[i], key="global_search")
        if pid is not None and pid != st.session_state.get("_last_search"):
            st.session_state["_last_search"] = pid
            open_card(pid)
        n = len(load_shortlist())
        st.caption(f"⭐ Lista corta: {n} jugador{'es' if n != 1 else ''}")


def radar_block(ids, g, colors, names=None, n_seasons=2):
    vals = values(tuple(int(i) for i in ids), n_seasons)
    if vals.empty:
        st.info("Sin temporadas con 600+ minutos.")
        return vals
    names = names or vals["name"].tolist()
    names = [f"{n} ({int(r.apps)} PJ · {int(r.minutes):,} min)".replace(",", ".") for n, r in zip(names, vals.itertuples())]
    nxp = [n.split(" (")[0] for n, lg in zip(names, vals["league"]) if lg == "MLS Next Pro"]
    if nxp:
        st.warning(f"{', '.join(nxp)}: Sportmonks tiene incompleta la MLS Next Pro (faltan partidos, por ejemplo 6 de "
                   "24 de Richmond en 2026). Para mandar estos números, usa Wyscout.")
    c1, c2 = st.columns([3, 2]) if len(names) <= 2 else (st.container(), st.container())
    with c1:
        st.pyplot(radar.draw(vals, g, colors, names, axis_ranges(g), i18n.lang()), width="stretch")
    with c2:
        t = radar.table(vals, g, names, i18n.lang())
        kinds = [radar.STATS[a][1] for a in radar.RADAR[g]]
        best = t.apply(lambda r: r == r.max(), axis=1) if len(names) > 1 else t.isna() & False
        shown = pd.DataFrame([[fmt(v, kinds[i]) if pd.notna(v) else "sin dato*" for v in t.iloc[i]]
                              for i in range(len(t))], index=t.index, columns=t.columns)
        if len(names) > 1:
            shown = pd.DataFrame([["▲ " + shown.iloc[i, j] if best.iloc[i, j] else shown.iloc[i, j]
                                   for j in range(shown.shape[1])] for i in range(len(shown))],
                                 index=shown.index, columns=shown.columns)
        sty = shown.style.apply(lambda col: [f"color:{GOOD}; font-weight:700" if b else "" for b in best[col.name]],
                                axis=0)
        st.dataframe(sty, width="stretch", height=35 * (len(t) + 1) + 3)
        st.caption(f"Temporadas usadas: {' · '.join(f'{n}: {r.seasons} ({int(r.minutes)} min)' for n, r in zip(names, vals.itertuples()))}. "
                   "Valores tal cual (sin ajustar por liga). ▲ = el mejor del grupo en esa estadística. Radar con "
                   "escala fija para la posición: centro = el 5% más bajo de la base, borde = el 5% más alto.")
        note = radar.missing_note(vals, radar.RADAR[g], names)
        if note:
            st.caption(note)
    return vals


# ─────────────────────────────── page: card ───────────────────────────────
def page_card():
    sidebar_search()
    st.session_state["_current_page"] = "ficha"
    q = st.query_params.get("pid")
    if q and str(q).isdigit():
        st.session_state["player_id"] = int(q)
    pid = st.session_state.get("player_id")
    if pid is None:
        mp = miami_players(load_rows())
        pid = int(mp[mp["display_name"].str.contains("Locadia", na=False)]["player_id"].iloc[0])
        st.session_state["player_id"] = pid
    info = now_info(pid)
    if info is None:
        st.error("Jugador sin datos.")
        return
    model, frame, acc, top2 = position_classifier()
    d = position_model.describe(load_rows(), frame, model, pid)
    probs = d["probs"]
    guess = probs.index[0] if probs is not None else "ST"
    ctx = st.session_state.get("card_ref")
    ctx = ctx if ctx and ctx.get("pid") == pid else None
    if ctx and ctx.get("g"):
        guess = ctx["g"]

    back_button()
    # header
    sl = load_shortlist()
    h1, h2 = st.columns([5, 1.3])
    with h1:
        age = age_of(info["dob"])
        nat = nationality()
        chips = [f"{age} años" if age else None,
                 f"{info['height']:.0f} cm" if pd.notna(info["height"]) else None,
                 es.country(nat.get(pid)) if nat is not None and nat.get(pid) else None,
                 f"{info['team']} · {info['country']} · {info['league']}",
                 f"{100 * info['share']:.0f}% de los minutos de su equipo en {info['season']}"
                 if pd.notna(info["share"]) else None,
                 "vínculo con EE.UU." if isinstance(info["us_link"], str) else None]
        from sm_metrics import POSITION_GROUPS
        listed_g = POSITION_GROUPS.get(info["listed"]) if isinstance(info["listed"], str) else None
        sub = GROUP_ES.get(guess, "").capitalize()
        if listed_g and listed_g != guess:
            sub += (f" según sus números · en su ficha figura como "
                    f"{position_model.DETAILED_ES.get(info['listed'], info['listed'])}")
        st.markdown(f"<div class='hname'>{info['name']}</div><p class='hsub'>{sub}</p>"
                    "<div class='chips'>" + "".join(f"<span>{c}</span>" for c in chips if c) + "</div>",
                    unsafe_allow_html=True)
    with h2:
        st.write("")
        if pid in sl:
            if st.button("★ En la lista corta", width="stretch", help="Clic para sacarlo"):
                sl.pop(pid)
                save_shortlist(sl)
                st.rerun()
        elif st.button("☆ Agregar a lista corta", type="primary", width="stretch"):
            sl[pid] = {"name": info["name"], "team": info["team"], "position": GROUP_ES.get(guess, ""),
                       "added": date.today().isoformat(), "status": "por ver", "note": ""}
            save_shortlist(sl)
            st.rerun()

    g = st.segmented_control("Posición del radar", list(POS_ES), default=guess,
                             format_func=lambda k: GROUP_ES[k].capitalize(), key=f"card_pos_{pid}",
                             help="Con qué posición se comparan sus números. Se elige sola según cómo juega; "
                                  "cámbiala si quieres verlo como otra cosa.") or guess
    me_h = values((int(pid),))
    if not me_h.empty:
        st.markdown(f"<div class='headline'>{headline(me_h.iloc[0], group_values(g), g)}</div>"
                    f"<p class='note'>Según sus números de {me_h.iloc[0]['seasons']}, comparado con los {PLURAL_ES[g]} "
                    "de nuestras 30 ligas, sin ajustar por nivel de liga.</p>", unsafe_allow_html=True)

    # positions + numbers by block
    c1, c2 = st.columns([1, 3])
    with c1:
        st.markdown("<div class='blk'><h4>Dónde juega</h4></div>", unsafe_allow_html=True)
        st.pyplot(pitch_positions(probs, info["listed"]), width="stretch")
        if d["lineup"]:
            st.markdown("<p class='note'><b>Alineaciones:</b> " +
                        ", ".join(f"{s} {l}" for s, l, _ in d["lineup"]) + "</p>", unsafe_allow_html=True)
        st.caption(f"% = probabilidad según sus números (modelo que acierta la posición el {100 * acc:.0f}% de "
                   f"las veces; la tiene entre sus dos primeras el {100 * top2:.0f}%).")
    with c2:
        me = values((int(pid),))
        ref = group_values(g)
        if me.empty:
            st.info("Sin temporadas con 600+ minutos para mostrar números.")
        else:
            row = me.iloc[0]
            st.markdown(f"<div class='blk'><h4>Sus números · {row['seasons']} · {int(row['minutes'])} min</h4></div>",
                        unsafe_allow_html=True)
            cols = st.columns(3)
            for i, blk in enumerate(BLOCK_ORDER[g]):
                col = cols[i % 3]
                html = f"<div class='blk'><h4>{blk}</h4>"
                for k in BLOCKS[blk]:
                    lab, kind, _, _ = radar.STATS[k]
                    v = row[k]
                    ok = ref[k].dropna()
                    if pd.isna(v) or len(ok) < 30:
                        cls, glyph = "na", ""
                    else:
                        pct = (ok < v).mean()
                        cls, glyph = (("hi", "▲ ") if pct >= 0.7 else ("lo", "▼ ") if pct <= 0.3 else ("mid", ""))
                    short = lab.replace(" por 90 min", "/90").replace(" — % de éxito", " %").replace(
                        " — % del total", " %").replace("Regates intentados", "Regates")
                    shown_v = "sin dato*" if pd.isna(v) else fmt(v, kind)
                    html += f"<div class='row'><span>{short}</span><b class='{cls}'>{glyph}{shown_v}</b></div>"
                col.markdown(html + "</div>", unsafe_allow_html=True)
            st.caption(f"▲ entre el 30% más alto de los {PLURAL_ES[g]} de nuestras ligas · ▼ entre el 30% más bajo. "
                       "Valores reales de sus dos últimas temporadas, sin ajustar por nivel de liga. "
                       "* su liga no registra ese dato, o tiene muy pocos intentos.")

    tab_r, tab_s, tab_h = st.tabs(["Radar vs Miami", "Jugadores parecidos a él", "Temporadas"])
    with tab_r:
        ref_pid, _ = miami_picker("Comparar con (Miami)", key=f"card_ref_{pid}_{g}_{ctx['ref'] if ctx else 0}",
                                  multi=False, group=g, default_id=ctx["ref"] if ctx else None)
        ids = [pid] if ref_pid == pid else [ref_pid, pid]
        radar_block(ids, g, [BLUE, OTHER][-len(ids):])
        if ref_pid != pid and st.button("📊 Abrir en Comparar (para exportar)", key=f"card_cmp_{pid}"):
            remember_back("ficha", int(pid))
            open_compare([ref_pid, pid], g)
    with tab_s:
        try:
            res = cached_rank(g, (int(pid),))
        except SystemExit as e:
            st.error(str(e))
            res = None
        if res is not None:
            f1, f2, f3 = st.columns(3)
            age_r = f1.slider("Edad", 16, 40, (18, 30), key=f"sim_age_{pid}", format="%d años")
            realista = f2.toggle("Solo fichajes realistas para la USL", value=True, key=f"sim_real_{pid}",
                                 help=MARKET_HELP)
            us_only = f3.toggle("Solo con vínculo con EE.UU.", key=f"sim_us_{pid}", help=US_HELP)
            cand = apply_filters(res["cand"], 2025, 1200, age_r[1], 0.0, (), None, None, us_only)
            cand = cand[cand["age"].fillna(0) >= age_r[0]]
            if realista:
                cand = cand[market.realistic(cand)]
            st.caption(f"Los más parecidos a {info['name']} como {GROUP_ES[g]}, con 1.200+ minutos y nivel al menos "
                       "el promedio de su liga. Parecido: 100 = el más parecido de todos los de la posición.")
            short = info["name"].split()[-1]
            for i, r in enumerate(cand.head(8).itertuples(), 1):
                candidate_card(i, r, g, [int(pid)], short, why_similar(r._asdict(), res["template"], res["weights"], short),
                               nationality(), sl, compact=True, origin=("ficha", int(pid)))
    with tab_h:
        r = load_rows()
        h = r[(r["player_id"] == pid) & (r["minutes_all"] > 0)].copy()
        h["s0"] = pd.to_numeric(h["season"].astype(str).str[:4], errors="coerce")
        h = h.sort_values(["s0", "minutes_all"], ascending=[False, False])
        h["Competencia"] = [es.league_full(c, lg) for c, lg in zip(h["country"], h["league"])]
        st.dataframe(h[["season", "team", "Competencia", "apps", "starts", "minutes_all", "goals", "assists"]].rename(
            columns={"season": "Temporada", "team": "Club", "apps": "PJ", "starts": "Titular",
                     "minutes_all": "Minutos", "goals": "Goles", "assists": "Asist."}),
            hide_index=True, width="stretch",
            column_config={c: st.column_config.NumberColumn(format="%d")
                           for c in ["PJ", "Titular", "Minutos", "Goles", "Asist."]})
        st.caption("Solo competencias de nuestras 30 ligas en Sportmonks (sin copas ni selecciones).")


# ─────────────────────────────── page: search ───────────────────────────────
def page_similar():
    sidebar_search()
    remember_back("parecidos")
    st.title("Parecidos a Miami FC")
    mp = miami_players(load_rows())
    with st.sidebar:
        fsec("Jugador de referencia")
        names = mp.set_index("player_id")["display_name"].to_dict()
        refs, _ = miami_picker("Jugador de Miami", key="s_refs", default_name="Locadia",)
        model, frame, _, _ = position_classifier()
        ref_pos = {}
        for r in refs:
            dd = position_model.describe(load_rows(), frame, model, r)
            ref_pos[r] = (dd["probs"].index[0] if dd["probs"] is not None
                          else mp.set_index("player_id")["group"].get(r, "ST"))
        guess = ref_pos[refs[0]] if refs else "ST"
        g = st.selectbox("Buscar entre…", list(POS_ES), index=list(POS_ES).index(guess), format_func=POS_ES.get,
                         key=f"s_pos_{'-'.join(map(str, refs)) or 0}",
                         help="La posición se elige sola según los números del jugador de Miami; la puedes cambiar.")
        if len(set(ref_pos.values())) > 1:
            st.warning("Según sus números juegan en posiciones distintas (" +
                       ", ".join(f"{names.get(r, r)}: {GROUP_ES[v]}" for r, v in ref_pos.items()) +
                       "). Mejor buscar con uno a la vez.")
        F = player_filters("s")
    if not refs:
        st.info("Elige al menos un jugador de Miami como referencia.")
        return
    try:
        res = cached_rank(g, tuple(int(r) for r in refs))
    except SystemExit as e:
        st.error(str(e))
        return
    cand = apply_filters(res["cand"], 2025, F["minutes"], F["age"][1], F["level"], (), None, None, F["us"])
    cand = cand[cand["age"].fillna(0) >= F["age"][0]]
    if F["height"] > 150:
        cand = cand[cand["height_cm"].fillna(0) >= F["height"]]
    if F["realista"]:
        cand = cand[market.realistic(cand)]
    with st.sidebar:
        fsec("Club y nacionalidad")
        cand = club_filters(cand, "s")
        st.write("")
        reset_button("s", keep=("s_refs",))
    roster, _ = miami_roster()
    lab = roster.set_index("player_id")["label"].to_dict()
    thin = roster[roster["player_id"].isin(refs) & (roster["best_season"] < 600)]["display_name"].tolist()
    if thin:
        st.warning(f"{', '.join(thin)}: menos de 600 minutos en una temporada. Su perfil se acerca al promedio de "
                   "la posición (con pocos minutos sus números todavía no son confiables), así que los parecidos "
                   "son más genéricos.")
    st.markdown("<div class='card'><div class='blk'><h4>Referencia</h4></div>" +
                "".join(f"<div class='hname' style='font-size:1.7rem !important'>{lab.get(r, names[r])}</div>"
                        for r in refs) +
                f"<p class='hsub'>Buscando {PLURAL_ES[g]} que juegan como "
                f"{'él' if len(refs) == 1 else 'ellos'} · {len(cand)} pasan los filtros</p></div>", unsafe_allow_html=True)
    ref_names = [mp.set_index("player_id")["display_name"].get(r, str(r)) for r in refs]
    ref_short = " / ".join(n.split()[-1] for n in ref_names)
    add_recent("parecidos", f"Parecidos a {' y '.join(ref_names)} · {GROUP_ES[g]}", {"refs": [int(r) for r in refs], "g": g})
    with st.expander("¿Cómo leer esta lista?", icon="ℹ️"):
        st.markdown(
            f"- **#1, #2…**: su lugar en la lista, según el orden que elijas.\n"
            f"- **Parecido a {ref_short}** (0 a 100): cuánto se parece su forma de jugar a la de {ref_short}, "
            f"comparado con todos los {PLURAL_ES[g]} de la base. 100 = de los más parecidos; 50 = en la mitad. "
            "Mide estilo (cuánto remata, toca, disputa duelos aéreos…), no si es mejor o peor.\n"
            "- **Nivel en su liga**: qué tan bien hace las cosas: sus porcentajes de acierto (pases, duelos, "
            "regates…) comparados con los jugadores de su posición en su propia liga. *Por encima*: mejores "
            "porcentajes que la mayoría de su liga. *En el promedio*: parecidos al resto. *Por debajo*: peores.\n"
            "- **% de los minutos**: qué parte de los minutos de su equipo jugó esta temporada (100% = jugó todo).\n"
            "- **min analizados**: los minutos de sus dos últimas temporadas que se usaron para calcular todo esto.\n"
            f"- **Se parece en / Más que {ref_short} / Menos que {ref_short}**: en qué estadísticas su perfil está más "
            f"cerca del de {ref_short}, y en cuáles se despega hacia arriba o hacia abajo (todo medido contra su "
            "propia liga).\n"
            f"- **Comparar** abre el radar lado a lado con {ref_short}, listo para descargar en PDF. **Ver ficha**: todos sus "
            "números.")
    show_chips(F["chips"] + st.session_state.get("s__clubchips", []))
    order = st.segmented_control("Ordenar por", ["Parecido", "Nivel", "Edad"], default="Parecido",
                                 key=f"s__order_{g}", format_func={"Parecido": "Más parecidos primero",
                                 "Nivel": "Mejor nivel primero", "Edad": "Más jóvenes primero"}.get) or "Parecido"
    if order == "Nivel":
        cand = cand.sort_values("level", ascending=False)
    elif order == "Edad":
        cand = cand.sort_values("age")
    nkey = f"s__show_{g}_{'-'.join(map(str, refs))}"
    n_show = st.session_state.get(nkey, 10)
    sl = load_shortlist()
    nat = nationality()
    for i, r in enumerate(cand.head(n_show).itertuples(), 1):
        candidate_card(i, r, g, [int(x) for x in refs], ref_short,
                       why_similar(r._asdict(), res["template"], res["weights"], ref_short), nat, sl)
    if len(cand) > n_show:
        if st.button(f"Ver 10 más ({len(cand) - n_show} restantes)", width="stretch"):
            st.session_state[nkey] = n_show + 10
            st.rerun()


SLOT_NAMES = {"LI": "Lateral izquierdo", "DFC": "Defensa central", "LD": "Lateral derecho",
              "CAI": "Carrilero izquierdo", "MCD": "Mediocentro defensivo", "CAD": "Carrilero derecho",
              "MI": "Volante izquierdo", "MC": "Mediocentro", "MD": "Volante derecho",
              "EI": "Extremo izquierdo", "MCO": "Mediapunta", "ED": "Extremo derecho", "DC": "Delantero centro"}
ALL_SLOTS = list(SLOT_NAMES)
LISTED_SLOT = {"Left Back": "LI", "Right Back": "LD", "Left Wing Back": "CAI", "Right Wing Back": "CAD",
               "Centre Back": "DFC", "Defensive Midfield": "MCD", "Central Midfield": "MC",
               "Attacking Midfield": "MCO", "Secondary Striker": "MCO", "Left Midfield": "MI",
               "Right Midfield": "MD", "Left Wing": "EI", "Right Wing": "ED", "Centre Forward": "DC"}


@st.cache_data(show_spinner=False)
def nationality():
    """player_id -> nationality (country name), or None if the file hasn't been built yet."""
    try:
        d = pd.read_pickle(sm_nationality.CACHE)
    except (OSError, FileNotFoundError):
        return None
    return d.dropna(subset=["nationality"]).set_index("player_id")["nationality"]


def club_filters(d, key):
    """Football Manager-style filters on the CURRENT club: league, team, nationality. Returns the filtered frame."""
    d = d.assign(_liga=[es.league_full(c, lg) for c, lg in zip(d["now_country"], d["now_league"])])
    nat = nationality()
    ligas = st.multiselect("Liga actual", sorted(d["_liga"].dropna().unique()), key=f"{key}_liga",
                           placeholder="Todas")
    pool = d[d["_liga"].isin(ligas)] if ligas else d
    equipos = st.multiselect("Equipo actual", sorted(pool["now_team"].dropna().astype(str).unique()),
                             key=f"{key}_eq", placeholder="Todos")
    if nat is not None:
        d = d.assign(_nat=d["player_id"].map(nat).map(lambda v: es.country(v) if isinstance(v, str) else v))
        nats = st.multiselect("Nacionalidad", sorted(d["_nat"].dropna().unique()), key=f"{key}_nat",
                              placeholder="Todas", help="La selección que eligió representar, según Sportmonks.")
    else:
        nats = []
        st.caption("Nacionalidad: falta cargar el dato (scouting/sm_nationality.py).")
    if ligas:
        d = d[d["_liga"].isin(ligas)]
    if equipos:
        d = d[d["now_team"].astype(str).isin(equipos)]
    if nats:
        d = d[d["_nat"].isin(nats)]
    st.session_state[f"{key}__clubchips"] = [", ".join(ligas) if ligas else None, ", ".join(equipos) if equipos else None,
                                             ("nacionalidad: " + ", ".join(nats)) if nats else None]
    return d.drop(columns=[c for c in ("_liga", "_nat") if c in d.columns])


@st.cache_data(show_spinner=False)
def slot_shares():
    """Share of each player's starts in every FM position, last two seasons with starts (from the lineups)."""
    try:
        s = sm_slots.player_slots()
    except (OSError, FileNotFoundError):
        return None
    s = s[s["slot"].isin(ALL_SLOTS)]
    se = load_rows()[["season_id", "season"]].drop_duplicates("season_id")
    se["start"] = pd.to_numeric(se["season"].astype(str).str[:4], errors="coerce")
    s = s.merge(se[["season_id", "start"]], on="season_id")
    last2 = (s[["player_id", "season_id", "start"]].drop_duplicates()
             .sort_values("start").groupby("player_id").tail(2))
    s = s.merge(last2[["player_id", "season_id"]], on=["player_id", "season_id"])
    t = s.pivot_table(index="player_id", columns="slot", values="starts", aggfunc="sum", fill_value=0)
    return t.reindex(columns=ALL_SLOTS, fill_value=0).div(t.sum(axis=1), axis=0)


SEASON_MODES = {"dos": "Actual + anterior", "actual": "Solo la actual", "anterior": "Solo la anterior"}


def season_ids(rows, mode):
    """Season ids allowed by mode, counted PER LEAGUE: 'actual' = each league's latest season (2026 in Chile,
    2026/27 in England), 'anterior' = the one before (2025 / 2025/26), 'dos' = both."""
    se = rows[["league_id", "season_id", "season"]].drop_duplicates("season_id")
    se["s0"] = pd.to_numeric(se["season"].astype(str).str[:4], errors="coerce")
    se["rk"] = se.groupby("league_id")["s0"].rank(ascending=False, method="dense")
    keep = {"actual": [1], "anterior": [2], "dos": [1, 2]}[mode]
    return set(se.loc[se["rk"].isin(keep), "season_id"])


@st.cache_data(show_spinner="Preparando la tabla de toda la base para esas temporadas (solo la primera vez)…")
def universe(mode="dos"):
    """One row per player in the whole database: values from the chosen seasons (600+ min each; mode, see
    season_ids), position by his numbers, current club and share of minutes this season."""
    rows = load_rows()
    model, frame, _, _ = position_classifier()
    f = frame.sort_values("start")
    last2 = f[["player_id", "season_id", "start"]].drop_duplicates().groupby("player_id").tail(2)
    f = f.merge(last2[["player_id", "season_id"]], on=["player_id", "season_id"])
    pr = pd.DataFrame(model.predict_proba(f[["z_" + c for c in position_model.FEATS]].to_numpy()),
                      columns=model.classes_, index=f.index).mul(f["minutes"], axis=0)
    pr["player_id"] = f["player_id"].values
    pr = pr.groupby("player_id").sum()
    pos = pr.idxmax(axis=1).rename("pos")
    pos_p = (pr.max(axis=1) / pr.sum(axis=1)).rename("pos_p")
    vals = radar.two_season_values(rows[rows["season_id"].isin(season_ids(rows, mode))], list(pos.index),
                                   tracked=radar.tracked_seasons(rows))
    ar = rows.assign(s0=pd.to_numeric(rows["season"].astype(str).str[:4], errors="coerce"))
    ar["team_games"] = ar.groupby(["team_id", "season_id"])["apps"].transform("max")
    ar = ar.sort_values(["player_id", "s0", "minutes_all"])
    now = ar.groupby("player_id").tail(1).set_index("player_id")
    ss = ar[ar["team_games"] >= 8].groupby("player_id").tail(1).set_index("player_id")
    u = vals.join(pos).join(pos_p)
    u["now_team"], u["now_country"] = now["team"], now["country"]
    u["now_league"], u["now_season"] = now["league"], now["season"]
    u["now_min_share"] = (now["minutes_all"] / (90 * now["team_games"].where(now["team_games"] > 0))).clip(0, 1)
    u["now_start_share"] = (ss["starts"] / ss["team_games"]).clip(0, 1)
    u["age"] = ((pd.Timestamp(date.today()) - pd.to_datetime(now["dob"], errors="coerce")).dt.days / 365.25)
    u["height"], u["us_link"] = now["height_cm"], now["us_link"]
    u["last_start"] = pd.to_numeric(u["seasons"].str.split(" + ", regex=False).str[-1].str[:4], errors="coerce")
    # FM positions: where he started (lineups); if his league has no lineup slots, his listed position
    sh = slot_shares()
    sh = (sh.reindex(u.index) if sh is not None else pd.DataFrame(index=u.index, columns=ALL_SLOTS, dtype=float))
    from_lineups = sh.notna().any(axis=1)
    listed = now["detailed_position"].reindex(u.index).map(LISTED_SLOT)
    for sl in ALL_SLOTS:
        u["slot_" + sl] = sh[sl].where(from_lineups, (listed == sl).astype(float)).fillna(0.0)

    def txt(row, lineups):
        top = sorted(((row["slot_" + k], k) for k in ALL_SLOTS if row["slot_" + k] >= 0.1), reverse=True)
        if not top:
            return "—"
        return " · ".join(f"{k} {v:.0%}" for v, k in top) if lineups else f"{top[0][1]} (ficha)"
    u["pos_txt"] = [txt(r, f) for (_, r), f in zip(u.iterrows(), from_lineups)]
    return u.reset_index().rename(columns={"index": "player_id"})


# Football Manager grid: label, x (0-68, left to right), y (0-105, own goal at the bottom)
FM_GRID = [("POR", 34, 6), ("LI", 9, 22), ("DFC", 34, 20), ("LD", 59, 22),
           ("CAI", 9, 39), ("MCD", 34, 37), ("CAD", 59, 39), ("MI", 9, 55), ("MC", 34, 54), ("MD", 59, 55),
           ("EI", 9, 72), ("MCO", 34, 70), ("ED", 59, 72), ("DC", 34, 88)]


def pitch_selector(key, default=("DC",)):
    """Clickable FM pitch: each click turns a position on or off (several allowed). Returns the list."""
    import altair as alt
    state, nkey = f"{key}_slots", f"{key}_n"
    if state not in st.session_state:
        st.session_state[state] = list(default)
        st.session_state[nkey] = 0
    cur = st.session_state[state]
    pts = pd.DataFrame([{"lab": l, "x": x, "y": y, "name": SLOT_NAMES.get(l, "Portero (no disponible)"),
                         "sel": "si" if l in cur else ("gk" if l == "POR" else "no")} for l, x, y in FM_GRID])
    lc = "#b9c8b9"
    box = pd.DataFrame([{"x": 0, "x2": 68, "y": 0, "y2": 105}, {"x": 13.85, "x2": 54.15, "y": 0, "y2": 16.5},
                        {"x": 13.85, "x2": 54.15, "y": 88.5, "y2": 105}, {"x": 24.85, "x2": 43.15, "y": 0, "y2": 5.5},
                        {"x": 24.85, "x2": 43.15, "y": 99.5, "y2": 105}])
    t = np.linspace(0, 2 * np.pi, 60)
    circ = pd.DataFrame({"x": 34 + 9.15 * np.cos(t), "y": 52.5 + 9.15 * np.sin(t), "o": range(60)})
    X = alt.X("x:Q", scale=alt.Scale(domain=[-1, 69]), axis=None)
    Y = alt.Y("y:Q", scale=alt.Scale(domain=[-1, 106]), axis=None)
    lines = (alt.Chart(box).mark_rect(fill=None, stroke=lc, strokeWidth=1.2)
             .encode(x=X, x2="x2:Q", y=Y, y2="y2:Q"))
    half = alt.Chart(pd.DataFrame({"x": [0], "x2": [68], "y": [52.5]})).mark_rule(color=lc, strokeWidth=1.2).encode(
        x=X, x2="x2:Q", y=Y)
    center = alt.Chart(circ).mark_line(color=lc, strokeWidth=1.2).encode(x=X, y=Y, order="o:Q")
    pick = alt.selection_point(fields=["lab"], name="pos", on="click", clear=False)
    color = alt.Color("sel:N", scale=alt.Scale(domain=["si", "no", "gk"], range=[BLUE, "#ffffff", "#e4e3df"]),
                      legend=None)
    dots = (alt.Chart(pts).mark_circle(size=760, opacity=1, stroke="#52514e", strokeWidth=1.2, cursor="pointer")
            .encode(x=X, y=Y, color=color, tooltip=[alt.Tooltip("name:N", title="Posición")]).add_params(pick))
    labels = (alt.Chart(pts).mark_text(fontSize=10, fontWeight="bold")
              .encode(x=X, y=Y, text="lab:N",
                      color=alt.condition(alt.datum.sel == "si", alt.value("#ffffff"), alt.value("#0b0b0b"))))
    chart = ((lines + half + center + dots + labels)
             .properties(width=230, height=340, background="#eef4ee")
             .configure_view(strokeWidth=0))
    # a fresh chart key after every click: the old selection never fires twice
    ev = st.altair_chart(chart, on_select="rerun", selection_mode="pos", width="content",
                         key=f"{key}_chart_{st.session_state[nkey]}")
    sel = (ev.selection.get("pos") if ev and ev.selection else None) or []
    if sel and sel[0].get("lab") in SLOT_NAMES:
        lab = sel[0]["lab"]
        new = [x for x in cur if x != lab] if lab in cur else cur + [lab]
        st.session_state[state] = [x for x in ALL_SLOTS if x in new]
        st.session_state[nkey] += 1
        st.rerun()
    shown = ", ".join(SLOT_NAMES[x].lower() for x in cur) if cur else "ninguna"
    st.markdown(f"<p class='note' style='margin-top:-6px'><b>{shown}</b><br>Clic para marcar o desmarcar; "
                "puedes elegir varias.</p>", unsafe_allow_html=True)
    return cur


def page_search():
    sidebar_search()
    remember_back("buscar")
    st.title("Buscar por posición")
    mode = st.session_state.get("b_mode") or "dos"
    u = universe(mode)
    with st.sidebar:
        fsec("Posición")
        slots = pitch_selector("b_pos")
        pos_min = st.segmented_control("Cuánto juega ahí", list(SHARE_OPTS), default=30, key="b_posmin",
                                       format_func=SHARE_OPTS.get,
                                       help="Según dónde fue titular en sus dos últimas temporadas: 'a veces' = al "
                                            "menos el 10% de sus titularidades en esas posiciones, 'habitualmente' "
                                            "= 30%, 'casi siempre' = 70%. Si su liga no trae la posición en la "
                                            "alineación, se usa la de su ficha.") or 30
        st.caption(f"Titular en esas posiciones en el {pos_min}% o más de sus partidos")
        fsec("Temporadas")
        st.segmented_control("Temporadas a usar", list(SEASON_MODES), default="dos", format_func=SEASON_MODES.get,
                             key="b_mode",
                             help="Por liga: 'actual' es 2026 en Chile o la USL y 2026/27 en Inglaterra o México; "
                                  "'anterior' es 2025 o 2025/26. Cada temporada necesita 600+ minutos.")
        if mode == "actual":
            st.caption("Ojo: en las ligas europeas, México y Centroamérica la temporada 2026/27 recién empezó y "
                       "pocos llegan a 600 minutos.")
        F = player_filters("b", level=False, seasons_note="en esas temporadas")
        no_miami = st.toggle("Sin jugadores de Miami", value=True, key="b_nomia")

    if not slots:
        st.info("Marca al menos una posición en la cancha.")
        return
    groups = [sm_slots.SLOT_GROUP[x] for x in slots]
    g = max(dict.fromkeys(groups), key=groups.count)              # radar axes of the most-marked group
    axes = radar.RADAR[g]
    SORT_EXTRA = {"minutes": "Más minutos jugados", "age": "Más jóvenes primero"}
    c1, c2, c3 = st.columns([2, 2, 1])
    sort_by = c1.selectbox("Ordenar por", list(SORT_EXTRA) + axes, key=f"b__sort_{g}",
                           format_func=lambda k: SORT_EXTRA.get(k) or radar.STATS[k][0] + " (mayor primero)")
    thr = None
    if sort_by in axes:
        vals = u[sort_by].dropna()
        kind = radar.STATS[sort_by][1]
        lo, hi = (0.0, 100.0) if kind == "pct" else (0.0, float(np.nanpercentile(vals, 99)) if len(vals) else 1.0)
        thr = c2.slider("Mostrar solo con al menos…", lo, hi, lo, key=f"b__thr_{sort_by}",
                        format="%d%%" if kind == "pct" else "%.2f")
        c2.caption("Sin mínimo" if thr <= lo else
                   f"Solo jugadores con {fmt(thr, kind)} o más en {radar.STATS[sort_by][0].lower()}")
    n_show = c3.selectbox("Mostrar", [25, 50, 100], index=1, key="b__n")

    u = u.assign(pos_share=u[["slot_" + x for x in slots]].sum(axis=1))
    d = u[(u["pos_share"] >= pos_min / 100) & u["age"].between(*F["age"]) & (u["minutes"] >= F["minutes"])]
    if F["height"] > 150:
        d = d[d["height"].fillna(0) >= F["height"]]
    if F["us"]:
        d = d[d["us_link"].notna()]
    if no_miami:
        d = d[~d["now_team"].eq("Miami FC")]
    with st.sidebar:
        fsec("Club y nacionalidad")
        d = club_filters(d, "b")
        st.write("")
        reset_button("b")
    if F["realista"]:
        d = d[market.realistic(d)]
    if thr is not None:
        d = d[d[sort_by].fillna(-1) >= thr].sort_values(sort_by, ascending=False)
    else:
        d = d.sort_values(sort_by, ascending=(sort_by == "age"))
    show_chips([", ".join(slots) + f" ({SHARE_OPTS[pos_min].lower()})", SEASON_MODES[mode].lower()] + F["chips"]
               + (["sin Miami"] if no_miami else []) + st.session_state.get("b__clubchips", []))
    add_recent("buscar", f"Buscar: {', '.join(slots)} · {F['chips'][0]}", {"slots": list(slots)})

    st.markdown(f"<p class='note'><b>{len(d)}</b> jugadores en toda la base (30 ligas) cumplen los filtros. "
                f"Valores de: {SEASON_MODES[mode].lower()} (600+ minutos cada una), tal cual, sin ajustar por nivel de liga. "
                "Para abrir la ficha de uno, marca la casilla al inicio de su fila.</p>", unsafe_allow_html=True)
    top = d.head(n_show).copy()
    sl = load_shortlist()
    top["Jugador"] = np.where(top["player_id"].isin(list(sl)), "★ ", "") + top["name"].astype(str)
    top["Club actual"] = top["now_team"].astype(str)
    top["País"] = top["now_country"].map(es.country)
    top["% minutos"] = (100 * top["now_min_share"]).round(0)
    top["Liga (datos)"] = [es.league_full(c, lg) for c, lg in zip(top["country"], top["league"])]
    show_stats = ([sort_by] if sort_by in axes else []) + [a for a in axes if a != sort_by][:5]
    cfg = {"Jugador": st.column_config.TextColumn(pinned=True),
           "Edad": st.column_config.NumberColumn(format="%.0f"),
           "Minutos": st.column_config.NumberColumn(format="%d"),
           "% minutos": st.column_config.ProgressColumn("% minutos esta temporada", min_value=0, max_value=100,
                                                        format="%d%%")}
    for k in show_stats:
        lab = radar.STATS[k][0].replace(" por 90 min", "/90").replace(" — % de éxito", " %").replace(" — % del total", " %")
        top[lab] = top[k]
        cfg[lab] = st.column_config.NumberColumn(format="%.0f%%" if radar.STATS[k][1] == "pct" else "%.2f")
    stat_cols = [cfg_k for cfg_k in top.columns if cfg_k in cfg and cfg_k not in ("Jugador", "Edad", "Minutos", "% minutos")]
    first = ["minutes"] if sort_by == "minutes" else ["age"] if sort_by == "age" else []
    tail = [c for c in ["age", "Club actual", "País", "% minutos", "Liga (datos)", "minutes"] if c not in first]
    tbl = top[["Jugador", "pos_txt"] + first + stat_cols + tail].rename(
        columns={"age": "Edad", "minutes": "Minutos", "pos_txt": "Posiciones"})
    ev = st.dataframe(tbl, hide_index=True, width="stretch", height=600, on_select="rerun",
                      selection_mode="single-row", key=f"search_all_{'-'.join(slots)}_{sort_by}", column_config=cfg)
    sel = ev.selection.rows if ev and ev.selection else []
    if sel:
        open_card(top.iloc[sel[0]]["player_id"])


# ─────────────────────────────── page: compare ───────────────────────────────
def page_compare():
    sidebar_search()
    st.session_state["_current_page"] = "comparar"
    back_button()
    st.title("Comparar")
    idx = dict(player_index())
    sl = load_shortlist()
    preset = st.session_state.pop("cmp_preset", None)
    if preset:
        for p in preset["ids"]:
            if p not in idx:
                inf = now_info(p) or {}
                idx[p] = f"{inf.get('name', p)} — {inf.get('team', '')} (pocos minutos)"
        st.session_state["cmp_ids"] = preset["ids"]
        st.session_state[f"cmp_pos_{preset['ids'][0]}"] = preset["g"]
    elif "cmp_ids" not in st.session_state:
        st.session_state["cmp_ids"] = [p for p in [st.session_state.get("player_id")] if p in idx]
    for p in st.session_state["cmp_ids"]:
        if p not in idx:
            idx[p] = (now_info(p) or {}).get("name", str(p))
    ids = st.multiselect("Jugadores (hasta 4)", list(idx), format_func=idx.get, max_selections=4, key="cmp_ids")
    if sl:
        add = st.pills("Agregar desde la lista corta", [p for p in sl if p in idx and p not in ids],
                       format_func=lambda p: sl[p]["name"], selection_mode="multi", key="cmp_pills")
        ids = (ids + list(add or []))[:4]
    if not ids:
        st.info("Elige al menos un jugador.")
        return
    model, frame, _, _ = position_classifier()
    dd = position_model.describe(load_rows(), frame, model, ids[0])
    guess = dd["probs"].index[0] if dd["probs"] is not None else "ST"
    c1, c2 = st.columns([3, 2])
    with c1:
        g = st.segmented_control("Posición del radar", list(POS_ES), default=guess,
                                 format_func=lambda k: GROUP_ES[k].capitalize(), key=f"cmp_pos_{ids[0]}",
                                 help="Los ejes del radar son los de esta posición.") or guess
    with c2:
        n_seasons = st.segmented_control("Temporadas", [1, 2], default=1, key="cmp_seasons",
                                         format_func=lambda n: "Temporada actual" if n == 1 else "Últimas dos") or 1
    vals = radar_block(ids, g, PALETTE, n_seasons=n_seasons)
    if vals is None or vals.empty:
        return

    # report export: one-pager in the dark comparison style (PNG for WhatsApp, PDF)
    st.divider()
    st.markdown("**Generar reporte**")
    st.caption("El reporte lleva la fecha, la fuente de los datos y las temporadas usadas. Azul = el primer jugador "
               "de la lista (normalmente el de Miami).")
    e1, e2, e3 = st.columns([1, 1, 1])
    lang = e1.segmented_control("Idioma", ["en", "es"], default=i18n.lang(), key="cmp_lang",
                                format_func=lambda l: "English" if l == "en" else "Español") or "en"
    names = vals["name"].tolist()
    if (vals["league"] == "MLS Next Pro").any():
        st.caption("⚠️ Hay jugadores de la MLS Next Pro: en Sportmonks les faltan partidos. Para un reporte, mejor el "
                   "one-pager con Wyscout.")
    bios = []
    for pid in vals.index:
        inf = now_info(int(pid)) or {}
        bios.append({"age": age_of(inf.get("dob")), "height": inf.get("height"), "club": inf.get("team", "—"),
                     "league": f"{inf.get('country', '')} · {inf.get('league', '')}"})
    fname = "MiamiFC_" + "_vs_".join(n.split()[-1] for n in names) + "_Comparison_SM"
    fig = export.onepager(vals, g, names, bios, lang, axis_ranges(g))
    png = export.to_bytes(fig, "png")
    fig = export.onepager(vals, g, names, bios, lang, axis_ranges(g))
    pdf = export.to_bytes(fig, "pdf")
    e2.download_button("⬇ Imagen (PNG, para WhatsApp)", png, f"{fname}.png", "image/png", width="stretch")
    e3.download_button("⬇ PDF", pdf, f"{fname}.pdf", "application/pdf", width="stretch")
    with st.expander("Vista previa"):
        st.image(png, width=520)


# ─────────────────────────────── page: shortlist ───────────────────────────────
def page_shortlist():
    sidebar_search()
    remember_back("lista")
    st.title("Lista corta")
    kind, err = shortlist_store.backend()
    if kind == "gsheets":
        st.caption("Guardada en la Google Sheet del club: permanente y compartida.")
    else:
        msg = ("Guardada solo en este servidor: en la versión online se borra cada vez que la app se reinicia. "
               "Para que sea permanente, conecta una Google Sheet (scouting/SHORTLIST_SETUP.md).")
        if err:
            msg += f" La Google Sheet configurada no respondió ({err})."
        st.warning(msg)
    sl = load_shortlist()
    if not sl:
        st.info("Todavía no hay jugadores. Abre la ficha de un jugador y toca «☆ Agregar a lista corta».")
        return
    rows = []
    for pid, v in sl.items():
        inf = now_info(pid) or {}
        rows.append({"player_id": pid, "Jugador": v["name"], "Posición": v.get("position", ""),
                     "Estado": v.get("status") or "por ver",
                     "Edad": age_of(inf.get("dob")), "Club actual": inf.get("team", v.get("team")),
                     "% minutos": None if pd.isna(inf.get("share", np.nan)) else round(100 * inf["share"]),
                     "Agregado": v.get("added", ""), "Nota": v.get("note", ""), "Quitar": False})
    df = pd.DataFrame(rows)
    st.markdown("<p class='note'>Cambia el <b>Estado</b> y escribe <b>Notas</b> directamente en la tabla; después toca "
                "«Guardar cambios».</p>", unsafe_allow_html=True)
    ed = st.data_editor(df, hide_index=True, width="stretch", key="sl_editor",
                        disabled=["Jugador", "Posición", "Edad", "Club actual", "% minutos", "Agregado"],
                        column_config={"player_id": None,
                                       "Estado": st.column_config.SelectboxColumn(
                                           options=shortlist_store.STATUSES, required=True, width="small"),
                                       "Nota": st.column_config.TextColumn(width="large"),
                                       "% minutos": st.column_config.ProgressColumn(
                                           "% minutos esta temporada", min_value=0, max_value=100, format="%d%%"),
                                       "Quitar": st.column_config.CheckboxColumn(width="small")})
    c1, c2, c3 = st.columns([1, 1, 3])
    if c1.button("Guardar cambios", type="primary", width="stretch"):
        new = {}
        for r in ed.itertuples():
            if not r.Quitar:
                new[int(r.player_id)] = {**sl[int(r.player_id)], "note": r.Nota or "", "status": r.Estado}
        save_shortlist(new)
        st.rerun()
    c2.download_button("Descargar (CSV)", ed.drop(columns=["player_id", "Quitar"]).to_csv(index=False).encode(),
                       "lista_corta.csv", "text/csv", width="stretch")
    pick = c3.selectbox("Abrir ficha", [None] + list(df["player_id"]),
                        format_func=lambda p: "—" if p is None else sl[p]["name"], key="sl_open")
    if pick is not None:
        open_card(pick)


# ─────────────────────────────── page: home ───────────────────────────────
def page_home():
    sidebar_search()
    st.markdown(f"<div class='hname'>Scouting · Miami FC</div>"
                f"<p class='hsub'>Jugadores de 30 ligas (USL, MLS, Sudamérica, Centroamérica, Inglaterra, "
                f"Escandinavia), temporadas 2024 a 2026 · datos Sportmonks actualizados el {data_date()}</p>",
                unsafe_allow_html=True)
    st.write("")
    c1, c2, c3 = st.columns(3)
    with c1, st.container(border=True):
        st.markdown("<div class='home'><h3>🧬 Reemplazar a un jugador de Miami</h3><p>Elige a uno del plantel y "
                    "mira quién juega parecido en otras ligas, con filtros de edad, minutos y mercado.</p></div>",
                    unsafe_allow_html=True)
        if st.button("Buscar parecidos", type="primary", width="stretch", key="home_sim"):
            st.switch_page(PAGES["parecidos"])
    with c2, st.container(border=True):
        st.markdown("<div class='home'><h3>🔎 Buscar por posición</h3><p>Marca una o varias posiciones en la "
                    "cancha y filtra toda la base por edad, minutos, liga, nacionalidad y estadísticas.</p></div>",
                    unsafe_allow_html=True)
        if st.button("Abrir el buscador", width="stretch", key="home_search"):
            st.switch_page(PAGES["buscar"])
    with c3, st.container(border=True):
        n = len(load_shortlist())
        st.markdown(f"<div class='home'><h3>⭐ Mi lista corta</h3><p>{n} jugador{'es' if n != 1 else ''} guardado"
                    f"{'s' if n != 1 else ''}, con estado y notas. Desde ahí se abre cada ficha y se comparan.</p></div>",
                    unsafe_allow_html=True)
        if st.button("Ver la lista", width="stretch", key="home_list"):
            st.switch_page(PAGES["lista"])
    rec = st.session_state.get("recent", [])
    st.write("")
    st.markdown("**Búsquedas recientes**" if rec else "<p class='note'>Las búsquedas que hagas en esta sesión "
                "quedan aquí para volver a ellas.</p>", unsafe_allow_html=True)
    for i, r in enumerate(rec):
        if st.button(r["label"], key=f"recent_{i}"):
            if r["kind"] == "parecidos":
                st.session_state["s_refs"] = r["payload"]["refs"]
                st.session_state[f"s_pos_{'-'.join(map(str, r['payload']['refs']))}"] = r["payload"]["g"]
                st.switch_page(PAGES["parecidos"])
            else:
                st.session_state["b_pos_slots"] = r["payload"]["slots"]
                st.session_state["b_pos_n"] = st.session_state.get("b_pos_n", 0) + 1
                st.switch_page(PAGES["buscar"])
    with st.expander("¿Qué hay detrás de los números?"):
        st.markdown(
            "- **Datos:** Sportmonks (estadísticas de partido). No es Wyscout. Sin copas ni selecciones.\n"
            "- **Valores tal cual:** no se ajustan por nivel de liga. Un gol en Bolivia y uno en la USL cuentan igual.\n"
            "- **Lo que falta:** algunas ligas no registran pases al último tercio ni recuperaciones; la app lo marca "
            "como «sin dato» en vez de poner cero. En MLS Next Pro faltan partidos.\n"
            "- **Posición:** la que la app calcula por sus números acierta 8 de cada 10 veces (9 de 10 contando su "
            "segunda opción). En «Buscar por posición» se usa además dónde fue titular en las alineaciones.\n"
            "- **Parecido:** compara el estilo (cuánto remata, toca, disputa en el aire…) de cada jugador con el de "
            "la referencia, medido contra su propia liga. No dice si es mejor o peor; para eso está «Nivel».")


PAGE_HOME = st.Page(page_home, title="Inicio", icon="🏠", default=True)
PAGE_SEARCH = st.Page(page_search, title="Buscar por posición", icon="🔎", url_path="buscar")
PAGE_SIMILAR = st.Page(page_similar, title="Parecidos a Miami FC", icon="🧬", url_path="parecidos")
PAGE_CARD = st.Page(page_card, title="Ficha", icon="🪪", url_path="ficha")
PAGE_COMPARE = st.Page(page_compare, title="Comparar", icon="📊", url_path="comparar")
PAGE_LIST = st.Page(page_shortlist, title="Lista corta", icon="⭐", url_path="lista")
PAGES = {"inicio": PAGE_HOME, "buscar": PAGE_SEARCH, "parecidos": PAGE_SIMILAR, "ficha": PAGE_CARD,
         "comparar": PAGE_COMPARE, "lista": PAGE_LIST}
# the menu is drawn by sidebar_search() (st.page_link), so Ficha stays reachable but out of the menu
nav = st.navigation(list(PAGES.values()), position="hidden")
nav.run()

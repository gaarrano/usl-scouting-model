"""
radar.py — position-specific comparison radars (same conventions as the Miami FC comparison PDFs):
  * each position has its own axes, written out in full ("Duelo aéreo — % de éxito"), never codes
  * FIXED scale per position: every axis runs from the 5th to the 95th percentile of all players of that
    position in the database (ranges()), so a player looks the same whoever he is compared with; the
    centre and edge values are written on the axis
  * a stat his league doesn't record is marked "sin dato*" (never drawn as a zero that looks real)
  * no numbers next to the points; real values go in the table beside the radar

Values are the player's last two usable seasons (600+ min each) in our Sportmonks leagues, computed from
summed counts: per-90 = total / (minutes / 90), % = successful / attempted. Raw values, NOT adjusted for
league level — two players from different leagues are compared as they are.
"""
import numpy as np
import pandas as pd

from sm_metrics import outfield_pool

# stat -> (label, kind, numerator, denominator). kind 'p90': numerator per 90; 'pct': numerator / denominator
STATS = {
    "goals": ("Goles por 90 min", "p90", "goals", None),
    "shots": ("Remates por 90 min", "p90", "shots", None),
    "sot_pct": ("Remates al arco — % del total", "pct", "shots_on_target", "shots"),
    "assists": ("Asistencias por 90 min", "p90", "assists", None),
    "key_passes": ("Pases clave por 90 min", "p90", "key_passes", None),
    "final_third": ("Pases al último tercio por 90 min", "p90", "final_third_passes", None),
    "touches": ("Toques por 90 min", "p90", "touches", None),
    "passes": ("Pases por 90 min", "p90", "passes", None),
    "pass_pct": ("Pase — % de éxito", "pct", "passes_acc", "passes"),
    "long": ("Pases largos por 90 min", "p90", "long_balls", None),
    "long_pct": ("Pase largo — % de éxito", "pct", "long_balls_acc", "long_balls"),
    "dribbles": ("Regates intentados por 90 min", "p90", "dribbles", None),
    "dribble_pct": ("Regate — % de éxito", "pct", "dribbles_won", "dribbles"),
    "crosses": ("Centros por 90 min", "p90", "crosses", None),
    "cross_pct": ("Centro — % de éxito", "pct", "crosses_acc", "crosses"),
    "fouls_drawn": ("Faltas recibidas por 90 min", "p90", "fouls_drawn", None),
    "duel_pct": ("Duelos — % de éxito", "pct", "duels_won", "duels"),
    "aerials": ("Duelos aéreos por 90 min", "p90", "aerials", None),
    "aerial_pct": ("Duelo aéreo — % de éxito", "pct", "aerials_won", "aerials"),
    "tackles": ("Entradas por 90 min", "p90", "tackles", None),
    "interceptions": ("Intercepciones por 90 min", "p90", "interceptions", None),
    "clearances": ("Despejes por 90 min", "p90", "clearances", None),
    "recoveries": ("Recuperaciones por 90 min", "p90", "recoveries", None),
}

EN = {
    "goals": "Goals per 90", "shots": "Shots per 90", "sot_pct": "Shots on target %", "assists": "Assists per 90",
    "key_passes": "Key passes per 90", "final_third": "Final-third passes per 90", "touches": "Touches per 90",
    "passes": "Passes per 90", "pass_pct": "Pass accuracy %", "long": "Long balls per 90",
    "long_pct": "Long-ball accuracy %", "dribbles": "Dribbles attempted per 90", "dribble_pct": "Dribble success %",
    "crosses": "Crosses per 90", "cross_pct": "Cross accuracy %", "fouls_drawn": "Fouls drawn per 90",
    "duel_pct": "Duels won %", "aerials": "Aerial duels per 90", "aerial_pct": "Aerial duels won %",
    "tackles": "Tackles per 90", "interceptions": "Interceptions per 90", "clearances": "Clearances per 90",
    "recoveries": "Recoveries per 90",
}


def label(k, lang="es"):
    return EN[k] if lang == "en" else STATS[k][0]


# axes per position group (order = clockwise from the top)
RADAR = {
    "ST": ["goals", "shots", "sot_pct", "assists", "key_passes", "touches", "dribbles", "dribble_pct",
           "fouls_drawn", "aerials", "aerial_pct", "duel_pct"],
    "W": ["goals", "shots", "assists", "key_passes", "final_third", "dribbles", "dribble_pct", "crosses",
          "cross_pct", "fouls_drawn"],
    "AM": ["goals", "shots", "assists", "key_passes", "final_third", "passes", "pass_pct", "dribbles",
           "dribble_pct", "fouls_drawn"],
    "CM": ["passes", "pass_pct", "long", "long_pct", "final_third", "key_passes", "recoveries", "tackles",
           "interceptions", "duel_pct"],
    "FB": ["duel_pct", "aerial_pct", "dribble_pct", "cross_pct", "pass_pct", "crosses", "final_third",
           "tackles", "interceptions", "recoveries"],
    "CB": ["duel_pct", "aerial_pct", "aerials", "tackles", "interceptions", "clearances", "recoveries",
           "pass_pct", "long", "long_pct"],
}
MIN_ATTEMPTS = 15          # a % on fewer attempts is left blank


def tracked_seasons(allrows):
    """Per count column, the league-seasons where Sportmonks actually records it. Sportmonks omits zeros,
    so a stat that a league doesn't track shows up as 0 for everyone: a league-season whose total is 0 for a
    column is treated as NOT measured (NaN), not as zero."""
    counts = sorted({c for _, _, n, d in STATS.values() for c in (n, d) if c and c != "aerials"}
                    | {"aerials_won", "aerials_lost"})
    tot = allrows.groupby("season_id")[counts].sum(min_count=1).fillna(0)
    return {c: set(tot.index[tot[c] > 0]) for c in counts}


def two_season_values(allrows, player_ids, tracked=None, n_seasons=2):
    """One row per player: last `n_seasons` usable seasons (600+ min) combined from summed counts
    (n_seasons=1: his current season only).
    Per-90 uses only the minutes of seasons where that stat is measured."""
    tracked = tracked or tracked_seasons(allrows)
    pool = outfield_pool(allrows, 600)
    pool = pool[pool["player_id"].isin(player_ids)].copy()
    for c, ok in tracked.items():
        pool.loc[~pool["season_id"].isin(ok), c] = np.nan
    pool["aerials"] = pool["aerials_won"] + pool["aerials_lost"].fillna(0)
    last2 = (pool[["player_id", "season_id", "start"]].drop_duplicates()
             .sort_values("start").groupby("player_id").tail(n_seasons))
    pool = pool.merge(last2[["player_id", "season_id"]], on=["player_id", "season_id"])
    counts = sorted({c for _, _, n, d in STATS.values() for c in (n, d) if c} | {"minutes"})
    tot = pool.groupby("player_id")[counts].sum(min_count=1)
    meta = (pool.sort_values("start").groupby("player_id")
            .agg(name=("display_name", "last"), team=("team", "last"), league=("league", "last"),
                 country=("country", "last"),
                 seasons=("season", lambda s: " + ".join(sorted(set(map(str, s)))))))
    out = meta.join(tot["minutes"])
    out["apps"] = pool.groupby("player_id")["apps"].sum()
    for k, (_, kind, num, den) in STATS.items():
        if kind == "p90":
            mins = pool["minutes"].where(pool[num].notna()).groupby(pool["player_id"]).sum(min_count=1)
            out[k] = tot[num] / (mins / 90)
        else:
            out[k] = np.where(tot[den] >= MIN_ATTEMPTS, 100 * tot[num] / tot[den].replace(0, np.nan), np.nan)
    return out.loc[[p for p in player_ids if p in out.index]]


def ranges(pool_values, group):
    """Fixed axis range per stat for a position: 5th-95th percentile of every player of that position
    (pool_values = two_season_values of the position's players). Returns {stat: (lo, hi)}."""
    out = {}
    for a in RADAR[group]:
        v = pool_values[a].dropna().to_numpy(float) if a in pool_values else np.array([])
        if len(v) < 20:
            out[a] = (0.0, 100.0) if STATS[a][1] == "pct" else (0.0, 1.0)
            continue
        lo, hi = np.percentile(v, 5), np.percentile(v, 95)
        out[a] = (float(lo), float(hi if hi > lo else lo + 1e-6))
    return out


def scaled(v, rng):
    """Value -> 0..1 on the axis (5th percentile at the centre, 95th at the edge, clipped)."""
    lo, hi = rng
    return float(np.clip((v - lo) / (hi - lo), 0, 1))


def axis_text(v, kind):
    return f"{v:.0f}" if kind == "pct" or abs(v) >= 10 else f"{v:.2f}".rstrip("0").rstrip(".")


def missing_note(values, axes, names, lang="es"):
    """'* sin dato: X (stat, stat)' for stats a player's league doesn't record; '' if none."""
    parts = []
    for (_, row), nm in zip(values.iterrows(), names):
        miss = [a for a in axes if pd.isna(row[a])]
        if miss:
            labs = ", ".join((EN_SHORT.get(a, a) if lang == "en" else STATS[a][0].split(" —")[0].replace(" por 90 min", ""))
                             for a in miss)
            parts.append(f"{nm.split(' (')[0]} ({labs})")
    if not parts:
        return ""
    return ("* no data (not recorded in his league, or too few attempts): " if lang == "en" else
            "* sin dato (su liga no lo registra o tiene muy pocos intentos): ") + "; ".join(parts)


EN_SHORT = {"goals": "goals", "shots": "shots", "sot_pct": "shots on target %", "assists": "assists",
            "key_passes": "key passes", "final_third": "final-third passes", "touches": "touches", "passes": "passes",
            "pass_pct": "pass %", "long": "long balls", "long_pct": "long-ball %", "dribbles": "dribbles",
            "dribble_pct": "dribble %", "crosses": "crosses", "cross_pct": "cross %", "fouls_drawn": "fouls drawn",
            "duel_pct": "duels %", "aerials": "aerial duels", "aerial_pct": "aerial %", "tackles": "tackles",
            "interceptions": "interceptions", "clearances": "clearances", "recoveries": "recoveries"}


def draw(values, group, colors, names, rngs=None, lang="es"):
    """Matplotlib radar of `values` (rows = players) on the axes of position `group`, fixed scale `rngs`."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    axes = RADAR[group]
    n = len(axes)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    rngs = rngs or {a: ((0.0, 100.0) if STATS[a][1] == "pct" else
                        (0.0, float(np.nanmax(values[a].to_numpy(float))) if values[a].notna().any() else 1.0))
                    for a in axes}

    fig = plt.figure(figsize=(7.2, 7.2), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax = fig.add_subplot(111, polar=True)
    ax.set_facecolor("#fcfcfb")
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels([])
    ax.yaxis.grid(color="#e4e3df", lw=0.8)
    ax.xaxis.grid(color="#e4e3df", lw=0.8)
    ax.spines["polar"].set_color("#d6d5d0")
    ax.set_xticks(ang)
    ax.set_xticklabels([])
    for a, t in zip(axes, ang):
        lab = label(a, lang)
        if "—" in lab:
            lab = lab.replace(" — ", "\n")
        elif " por 90 min" in lab:
            lab = lab.replace(" por 90 min", "\npor 90 min")
        elif " per 90" in lab:
            lab = lab.replace(" per 90", "\nper 90")
        elif lab.endswith(" %"):
            lab = lab[:-2] + "\n%"
        if values[a].isna().any():
            lab += "*"
        ha = "center" if np.isclose(np.sin(t), 0, atol=0.15) else ("left" if np.sin(t) > 0 else "right")
        ax.text(t, 1.13, lab, ha=ha, va="center", fontsize=8.6, color="#2b2b29")
        # scale on the axis: middle and edge (the centre is the position's 5th percentile)
        lo, hi = rngs[a]
        for r in (0.5, 1.0):
            ax.text(t + 0.09 / r, r, axis_text(lo + (hi - lo) * r, STATS[a][1]), ha="center", va="center",
                    fontsize=6.4, color="#8a8983", bbox=dict(boxstyle="round,pad=0.1", fc="#fcfcfb", ec="none", alpha=0.9))
    for (pid, row), c, nm in zip(values.iterrows(), colors, names):
        r = np.array([0 if pd.isna(row[a]) else scaled(row[a], rngs[a]) for a in axes])
        rr, aa = np.append(r, r[0]), np.append(ang, ang[0])
        ax.plot(aa, rr, color=c, lw=2, zorder=3)
        ax.fill(aa, rr, color=c, alpha=0.12, zorder=2)
        ax.scatter(ang, r, s=16, color=c, edgecolor="#fcfcfb", linewidth=1, zorder=4)
    handles = [plt.Line2D([0], [0], color=c, lw=3) for c in colors[:len(names)]]
    fig.legend(handles, names, loc="upper center", ncol=min(len(names), 4), frameon=False, fontsize=9.5,
               bbox_to_anchor=(0.5, 0.99))
    note = missing_note(values, axes, names, lang)
    foot = ("Fixed scale for the position: centre = bottom 5% of the database, edge = top 5%. Real values in the table."
            if lang == "en" else
            "Escala fija para la posición: centro = el 5% más bajo de la base, borde = el 5% más alto. Valores reales en la tabla.")
    fig.text(0.5, 0.015, foot + ("\n" + note if note else ""), ha="center", fontsize=7.2, color="#52514e", wrap=True)
    fig.subplots_adjust(top=0.82, bottom=0.14, left=0.19, right=0.81)
    return fig


def table(values, group, names, lang="es"):
    """Stats x players table with real values; best of each row marked by the caller."""
    axes = RADAR[group]
    t = pd.DataFrame({nm: [values.iloc[i][a] for a in axes] for i, nm in enumerate(names)},
                     index=[label(a, lang) for a in axes])
    return t

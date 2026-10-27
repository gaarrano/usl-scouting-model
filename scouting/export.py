"""
export.py — one-page player comparison (PNG / PDF) from the app, in the dark one-pager style of the
Wyscout comparison reports: title, bio table, position radar, stats table, footer. Spanish or English.
Data: Sportmonks (stated on the page). Values as recorded, not adjusted for league level.
"""
import io
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import radar  # noqa: E402

BG, PANEL, ROW_A, ROW_B = "#0e0e10", "#28282e", "#17171b", "#1e1e23"
TXT, MUT, FAINT, GOOD = "#f2f2f2", "#9aa0a6", "#6b7076", "#2ecc71"
COLORS = ["#4f8fe6", "#f28c38", "#f1c40f", "#bdc3c7"]   # same convention as the app: blue = our/reference player

EN = radar.EN
TXTS = {
    "es": {"sub": "MIAMI FC · Gabriel Arraño · Informe de scouting · COMPARACIÓN DE JUGADORES",
           "bio": ["Edad", "Estatura", "Club actual", "Liga", "Muestra"],
           "stats": "ESTADÍSTICAS", "profile": "PERFIL", "pos": {"ST": "delantero centro", "W": "extremo",
           "AM": "mediapunta", "CM": "mediocentro", "FB": "lateral", "CB": "defensa central"},
           "radar": "Radar de", "foot": "Datos: Sportmonks · valores registrados, sin ajustar por nivel de liga · "
           "escala fija por posición: centro = el 5% más bajo de la base, borde = el 5% más alto · "
           "verde = el mejor del grupo · azul = jugador de referencia", "min": "min", "yrs": "años"},
    "en": {"sub": "MIAMI FC · Gabriel Arraño · Scouting report · PLAYER COMPARISON",
           "bio": ["Age", "Height", "Current club", "League", "Sample"],
           "stats": "STATS", "profile": "PROFILE", "pos": {"ST": "striker", "W": "winger", "AM": "attacking midfielder",
           "CM": "central midfielder", "FB": "full-back", "CB": "center-back"},
           "radar": "Radar as", "foot": "Data: Sportmonks · values as recorded, not adjusted for league level · "
           "fixed scale per position: centre = bottom 5% of the database, edge = top 5% · "
           "green = best of the group · blue = reference player", "min": "min", "yrs": "yrs"},
}


def label(k, lang):
    return EN[k] if lang == "en" else radar.STATS[k][0]


def fmt(v, kind, na="—"):
    if v is None or pd.isna(v):
        return na
    return f"{v:.0f}%" if kind == "pct" else f"{v:.2f}"


def _radar(ax, vals, g, lang, rngs=None):
    axes = radar.RADAR[g]
    n = len(axes)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    rngs = rngs or {a: ((0.0, 100.0) if radar.STATS[a][1] == "pct" else
                        (0.0, (np.nanmax(vals[a].to_numpy(float)) if vals[a].notna().any() else 1.0) or 1.0))
                    for a in axes}
    ax.set_facecolor(BG)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels([])
    ax.grid(color="#3a3a3f", lw=0.7)
    ax.spines["polar"].set_color("#4a4a50")
    ax.set_xticks(ang)
    ax.set_xticklabels([])
    for a, t in zip(axes, ang):
        lab = label(a, lang)
        lab = lab.replace(" per 90", "\nper 90").replace(" por 90 min", "\npor 90 min").replace(" — ", "\n")
        if lab.endswith(" %") and "\n" not in lab:
            lab = lab[:-2] + "\n%"
        if vals[a].isna().any():
            lab += "*"
        ha = "center" if abs(np.sin(t)) < 0.15 else ("left" if np.sin(t) > 0 else "right")
        ax.text(t, 1.16, lab, ha=ha, va="center", fontsize=7.4, color="#e8e8e8")
        lo, hi = rngs[a]
        for r in (0.5, 1.0):
            ax.text(t + 0.09 / r, r, radar.axis_text(lo + (hi - lo) * r, radar.STATS[a][1]), ha="center",
                    va="center", fontsize=5.6, color="#8a8a90")
    for i, (_, row) in enumerate(vals.iterrows()):
        c = COLORS[i]
        rr = np.array([0 if pd.isna(row[a]) else radar.scaled(row[a], rngs[a]) for a in axes])
        ax.plot(np.append(ang, ang[0]), np.append(rr, rr[0]), color=c, lw=2)
        ax.fill(np.append(ang, ang[0]), np.append(rr, rr[0]), color=c, alpha=0.16)
        ax.scatter(ang, rr, s=12, color=c, zorder=5)


def _table(ax, header, rows, colors=None, best=None, first_w=0.42, fs=7.4):
    """Simple dark table drawn with rectangles (rows = list of lists of strings)."""
    ax.axis("off")
    ax.set_xlim(0, 1)
    n = len(rows) + 1
    ax.set_ylim(0, n)
    k = len(header) - 1
    cw = (1 - first_w) / max(k, 1)
    xs = [0] + [first_w + i * cw for i in range(k)]
    ax.add_patch(plt.Rectangle((0, n - 1), 1, 1, color=PANEL))
    for j, h in enumerate(header):
        col = (colors[j - 1] if colors and j > 0 else MUT)
        ax.text(xs[j] + 0.012, n - 0.5, h, va="center", fontsize=fs, color=col, fontweight="bold")
    for i, r in enumerate(rows):
        y = n - 2 - i
        ax.add_patch(plt.Rectangle((0, y), 1, 1, color=ROW_A if i % 2 == 0 else ROW_B))
        for j, v in enumerate(r):
            win = best is not None and j > 0 and best[i][j - 1]
            ax.text(xs[j] + 0.012, y + 0.5, v, va="center", fontsize=fs,
                    color=GOOD if win else (TXT if j > 0 else "#d0d0d0"), fontweight="bold" if win else "normal")


def onepager(vals, g, names, bios, lang="en", rngs=None):
    """vals: radar.two_season_values rows (one per player, same order as names); bios: list of dicts with
    age, height, club, league. Returns a matplotlib Figure (letter size)."""
    T = TXTS[lang]
    fig = plt.figure(figsize=(8.5, 11), dpi=150)
    fig.patch.set_facecolor(BG)
    title = "  vs  ".join(n.upper() for n in names)
    fig.text(0.06, 0.955, title, fontsize=17 if len(names) <= 2 else 13, fontweight="bold", color=TXT)
    x = 0.06
    for i, n in enumerate(names):
        t = fig.text(x, 0.935, n, fontsize=8.5, fontweight="bold", color=COLORS[i])
        x += 0.013 * len(n) + 0.03
    fig.text(0.06, 0.918, T["sub"], fontsize=6.8, color=FAINT)
    fig.text(0.94, 0.918, date.today().strftime("%d.%m.%Y"), fontsize=6.8, color=FAINT, ha="right")

    # bio table
    axb = fig.add_axes([0.06, 0.80, 0.88, 0.10])
    rows = []
    for k, key in enumerate(["age", "height", "club", "league", "sample"]):
        r = [T["bio"][k]]
        for i, b in enumerate(bios):
            v = vals.iloc[i]
            if key == "age":
                r.append(f"{b['age']} {T['yrs']}" if b.get("age") else "—")
            elif key == "height":
                r.append(f"{b['height']:.0f} cm" if b.get("height") and not pd.isna(b["height"]) else "—")
            elif key == "club":
                r.append(str(b.get("club", "—"))[:40])
            elif key == "league":
                r.append(str(b.get("league", "—"))[:40])
            else:
                r.append(f"{v['seasons']} · {int(v['apps'])} {'M' if lang == 'en' else 'PJ'} · {int(v['minutes'])} {T['min']}")
        rows.append(r)
    _table(axb, [T["profile"]] + names, rows, colors=COLORS, first_w=0.18, fs=7.2)

    # radar
    fig.text(0.06, 0.775, f"{T['radar']} {T['pos'][g]}".upper(), fontsize=7.5, color=MUT, fontweight="bold")
    axr = fig.add_axes([0.20, 0.42, 0.60, 0.32], polar=True)
    _radar(axr, vals, g, lang, rngs)

    # stats table
    axes = radar.RADAR[g]
    rows, best = [], []
    for a in axes:
        kind = radar.STATS[a][1]
        col = vals[a].to_numpy(float)
        rows.append([label(a, lang)] + [fmt(v, kind, "no data*" if lang == "en" else "sin dato*") for v in col])
        mx = np.nanmax(col) if np.isfinite(col).any() else np.nan
        best.append([len(names) > 1 and np.isfinite(v) and v == mx for v in col])
    axt = fig.add_axes([0.06, 0.07, 0.88, 0.30])
    _table(axt, [T["stats"]] + names, rows, colors=COLORS, best=best, first_w=0.40, fs=7.4)

    note = radar.missing_note(vals, axes, names, lang)
    fig.text(0.06, 0.035, T["foot"] + ("\n" + note if note else ""), fontsize=5.6, color=FAINT, wrap=True)
    return fig


def to_bytes(fig, fmt_):
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt_, facecolor=BG)
    plt.close(fig)
    return buf.getvalue()

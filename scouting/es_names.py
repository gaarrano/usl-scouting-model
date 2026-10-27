"""
es_names.py — Spanish display names for what Sportmonks gives in English (countries, leagues) and plain
Spanish words for the model's features, used by the app for the "se parece en…" lines and the card headline.
Only DISPLAY: the data keeps the English names (market.py and fit.py match on them).
"""
COUNTRY = {
    "Argentina": "Argentina", "Bolivia": "Bolivia", "Brazil": "Brasil", "Canada": "Canadá", "Chile": "Chile",
    "Colombia": "Colombia", "Costa Rica": "Costa Rica", "Denmark": "Dinamarca", "Ecuador": "Ecuador",
    "England": "Inglaterra", "Finland": "Finlandia", "Guatemala": "Guatemala", "Honduras": "Honduras",
    "Mexico": "México", "Norway": "Noruega", "Paraguay": "Paraguay", "Peru": "Perú",
    "Republic of Ireland": "Irlanda", "Sweden": "Suecia", "United States": "Estados Unidos",
    "Venezuela": "Venezuela",
    # other nationalities that appear in the 30 leagues
    "Uruguay": "Uruguay", "Spain": "España", "France": "Francia", "Germany": "Alemania", "Italy": "Italia",
    "Portugal": "Portugal", "Netherlands": "Países Bajos", "Belgium": "Bélgica", "Scotland": "Escocia",
    "Wales": "Gales", "Northern Ireland": "Irlanda del Norte", "Ireland": "Irlanda", "Jamaica": "Jamaica",
    "Trinidad and Tobago": "Trinidad y Tobago", "Haiti": "Haití", "Panama": "Panamá", "El Salvador": "El Salvador",
    "Nicaragua": "Nicaragua", "Dominican Republic": "República Dominicana", "Puerto Rico": "Puerto Rico",
    "Cuba": "Cuba", "Curaçao": "Curazao", "Suriname": "Surinam", "Guyana": "Guyana", "Nigeria": "Nigeria",
    "Ghana": "Ghana", "Senegal": "Senegal", "Cameroon": "Camerún", "Ivory Coast": "Costa de Marfil",
    "Côte d'Ivoire": "Costa de Marfil", "Mali": "Malí", "Guinea": "Guinea", "Morocco": "Marruecos",
    "Algeria": "Argelia", "Tunisia": "Túnez", "Egypt": "Egipto", "South Africa": "Sudáfrica", "DR Congo": "R.D. del Congo",
    "Congo DR": "R.D. del Congo", "Gambia": "Gambia", "Sierra Leone": "Sierra Leona", "Liberia": "Liberia",
    "Cape Verde": "Cabo Verde", "Cape Verde Islands": "Cabo Verde", "Japan": "Japón", "South Korea": "Corea del Sur",
    "Korea Republic": "Corea del Sur", "Australia": "Australia", "New Zealand": "Nueva Zelanda", "Iceland": "Islandia",
    "Poland": "Polonia", "Croatia": "Croacia", "Serbia": "Serbia", "Bosnia and Herzegovina": "Bosnia",
    "Greece": "Grecia", "Turkey": "Turquía", "Türkiye": "Turquía", "Switzerland": "Suiza", "Austria": "Austria",
    "Czech Republic": "Chequia", "Czechia": "Chequia", "Slovakia": "Eslovaquia", "Hungary": "Hungría",
    "Romania": "Rumania", "Ukraine": "Ucrania", "Russia": "Rusia", "Lithuania": "Lituania", "Latvia": "Letonia",
    "Estonia": "Estonia", "Faroe Islands": "Islas Feroe", "Cyprus": "Chipre", "Israel": "Israel", "Iran": "Irán",
    "Philippines": "Filipinas", "India": "India", "China PR": "China", "China": "China",
}
CODE = {
    "Argentina": "ARG", "Bolivia": "BOL", "Brazil": "BRA", "Canada": "CAN", "Chile": "CHI", "Colombia": "COL",
    "Costa Rica": "CRC", "Denmark": "DIN", "Ecuador": "ECU", "England": "ING", "Finland": "FIN",
    "Guatemala": "GUA", "Honduras": "HON", "Mexico": "MEX", "Norway": "NOR", "Paraguay": "PAR", "Peru": "PER",
    "Republic of Ireland": "IRL", "Sweden": "SUE", "United States": "EE.UU.", "Venezuela": "VEN",
}
LEAGUE = {
    "Liga Profesional de Fútbol": "Primera División", "Primera B Nacional": "Primera B Nacional",
    "Liga De Futbol Prof": "Primera División", "Serie B": "Serie B", "Serie C": "Serie C",
    "Premier League": "Canadian Premier League", "Primera B": "Primera B", "Primera Division": "Primera División",
    "Liga BetPlay": "Primera División (Liga BetPlay)", "First Division": "Segunda División",
    "Liga Pro": "Liga Pro", "Liga Pro Serie B": "Liga Pro Serie B", "League One": "League One (3.ª división)",
    "League Two": "League Two (4.ª división)", "Veikkausliiga": "Veikkausliiga", "Liga Nacional": "Liga Nacional",
    "Liga de Expansión MX": "Liga de Expansión MX", "OBOS Ligaen": "OBOS-ligaen (2.ª división)",
    "Division 1": "Primera División", "Premier Division": "Premier Division", "Superettan": "Superettan (2.ª división)",
    "MLS Next Pro": "MLS Next Pro", "Major League Soccer": "MLS", "USL Championship": "USL Championship",
    "USL League One": "USL League One",
}


def _en():
    try:
        import i18n
        return i18n.lang() == "en"
    except Exception:    # noqa: BLE001
        return False


def country(c):
    return str(c) if _en() else COUNTRY.get(str(c), str(c))


def code(c):
    return CODE.get(str(c), str(c)[:3].upper())


def league(lg):
    return str(lg) if _en() else LEAGUE.get(str(lg), str(lg))


def league_full(c, lg):
    """'Chile · Primera División'."""
    return f"{country(c)} · {league(lg)}"


# fit.py / sm_metrics FEATURES -> plain Spanish (for "se parece en: remates, duelos aéreos")
FEATURE_ES = {
    "touches_p90": "toques", "passes_p90": "volumen de pase", "pass_pct": "precisión de pase",
    "long_p90": "pases largos", "long_pct": "precisión en pase largo", "key_passes_p90": "pases clave",
    "crosses_p90": "centros", "cross_pct": "precisión de centro", "dribbles_p90": "regates",
    "dribble_pct": "éxito en el regate", "shots_p90": "remates", "sot_pct": "remates al arco",
    "goals_p90": "goles", "assists_p90": "asistencias", "fouls_drawn_p90": "faltas recibidas",
    "loss_per100": "pérdidas", "duels_p90": "duelos", "duel_pct": "éxito en duelos",
    "aerial_p90": "duelos aéreos", "aerial_pct": "éxito en el aire", "tackles_p90": "entradas",
    "int_p90": "intercepciones", "clear_p90": "despejes", "recov_p90": "recuperaciones",
    "final_third_p90": "pases al último tercio",
}

# radar.STATS keys -> words for the card headline ("muchos remates", "pocas asistencias")
STAT_WORDS = {
    "goals": ("goles", "m"), "shots": ("remates", "m"), "sot_pct": ("precisión de remate", "f1"),
    "assists": ("asistencias", "f"), "key_passes": ("pases clave", "m"), "final_third": ("pases al último tercio", "m"),
    "touches": ("toques", "m"), "passes": ("pases", "m"), "pass_pct": ("precisión de pase", "f1"),
    "long": ("pases largos", "m"), "long_pct": ("precisión en pase largo", "f1"), "dribbles": ("regates", "m"),
    "dribble_pct": ("éxito en el regate", "m1"), "crosses": ("centros", "m"), "cross_pct": ("precisión de centro", "f1"),
    "fouls_drawn": ("faltas recibidas", "f"), "duel_pct": ("éxito en duelos", "m1"), "aerials": ("duelos aéreos", "m"),
    "aerial_pct": ("éxito en el aire", "m1"), "tackles": ("entradas", "f"), "interceptions": ("intercepciones", "f"),
    "clearances": ("despejes", "m"), "recoveries": ("recuperaciones", "f"),
}


def many(key):
    w, g = STAT_WORDS[key]
    return {"m": f"muchos {w}", "f": f"muchas {w}", "m1": f"mucho {w}", "f1": f"mucha {w}"}[g]


def few(key):
    w, g = STAT_WORDS[key]
    return {"m": f"pocos {w}", "f": f"pocas {w}", "m1": f"poco {w}", "f1": f"poca {w}"}[g]

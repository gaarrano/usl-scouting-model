"""
i18n.py — English mode for the app without touching every string.

The app is written in Spanish for the club's staff. In English mode (sidebar switch, or ?lang=en in the URL) every
text that goes through a Streamlit call (markdown, captions, labels, help, options, column headers…) is passed
through `tr()`, which applies an ordered list of phrase substitutions: whole phrases first, then words, matched
only at word boundaries so player and club names are left alone. Numbers, names and HTML survive untouched.

`install()` wraps the Streamlit functions once per process; `lang()` reads the current session's language.
"""
import re

import streamlit as st

LANGS = {"es": "Español", "en": "English"}


def lang():
    try:
        if not st.session_state.get("lang"):
            q = st.query_params.get("lang")
            st.session_state["lang"] = q if q in LANGS else "es"
        cur = st.session_state["lang"]
        if cur == "en" and st.query_params.get("lang") != "en":
            st.query_params["lang"] = "en"          # keep ?lang=en in the URL across pages (reload-safe, shareable)
        return cur
    except Exception:          # noqa: BLE001 — no script context
        return "es"


# ---------------------------------------------------------------- phrases (longest first; both cases added)
_P = [
    # sidebar / nav / pages
    ("Parecidos a Miami FC", "Similar to Miami FC"), ("Buscar por posición", "Search by position"),
    ("Lista corta", "Shortlist"), ("Inicio", "Home"), ("Ficha", "Player card"), ("Comparar", "Compare"),
    ("Buscar jugador", "Find a player"), ("Escribe un nombre…", "Type a name…"),
    ("Datos: Sportmonks · actualizado", "Data: Sportmonks · updated"),
    ("Jugador de referencia", "Reference player"), ("Jugador de Miami", "Miami player"),
    ("Incluir ex jugadores de Miami", "Include former Miami players"), ("Por defecto solo el plantel", "By default only the"),
    ("ex Miami", "former Miami"), ("pocos minutos", "few minutes"), ("Buscar entre…", "Search among…"),
    ("La posición se elige sola según los números del jugador de Miami; la puedes cambiar.",
     "The position is picked from the Miami player's numbers; you can change it."),
    ("Según sus números juegan en posiciones distintas (", "By their numbers they play different positions ("),
    ("). Mejor buscar con uno a la vez.", "). Better to search with one at a time."),
    ("Elige al menos un jugador de Miami como referencia.", "Pick at least one Miami player as the reference."),
    ("Restablecer filtros", "Reset filters"), ("Club y nacionalidad", "Club and nationality"),
    ("Liga actual", "Current league"), ("Equipo actual", "Current club"), ("Nacionalidad", "Nationality"),
    ("Todas", "All"), ("Todos", "All"), ("La selección que eligió representar, según Sportmonks.",
                                        "The national team he chose to represent, per Sportmonks."),
    ("Nacionalidad: falta cargar el dato (scouting/sm_nationality.py).", "Nationality: data not loaded yet."),
    # filters
    ("Cuánto ha jugado", "How much he has played"), ("Minutos jugados (mínimo)", "Minutes played (minimum)"),
    ("de sus dos últimas temporadas", "over his last two seasons"), ("en esas temporadas", "in those seasons"),
    ("partidos completos", "full matches"), ("Al menos", "At least"), ("minutos", "minutes"),
    ("Estatura mínima", "Minimum height"), ("Sin mínimo de estatura", "No height minimum"), ("cm o más", "cm or taller"),
    ("Cualquier edad", "Any age"), ("Edad", "Age"), ("años", "yrs"), ("%d yrs", "%d yrs"),
    ("Nivel en su liga", "Level in his league"), ("Cualquiera", "Any"),
    ("Promedio de su liga o más", "League average or better"), ("Por encima de su liga", "Above his league"),
    ("Muy por encima", "Well above"), ("Por encima", "Above"), ("Por debajo", "Below"), ("En el promedio", "Average"),
    ("Qué tan bien hace las cosas (% de pases, duelos, regates…) comparado con los jugadores de su posición en su propia liga.",
     "How well he does things (pass, duel and dribble success %) compared with the players of his position in his own league."),
    ("Mercado", "Market"), ("Solo fichajes realistas para la USL", "Realistic USL targets only"),
    ("mercado realista", "realistic market"), ("todos los mercados", "all markets"),
    ("Solo con vínculo con EE.UU.", "US-linked only"), ("vínculo con EE.UU.", "US link"),
    ("Saca a los titulares habituales de clubes en ligas más fuertes (MLS, primera de Argentina, Serie B de Brasil, primera de Colombia, League One): en principio no vendrían a la USL. Los suplentes de esas ligas sí aparecen.",
     "Removes regular starters at clubs in stronger leagues (MLS, Argentina's top flight, Brazil's Serie B, Colombia's top flight, League One): they would not normally come to the USL. Fringe players from those leagues stay in."),
    ("Nacido en EE.UU. o seleccionado de EE.UU.: en principio no ocuparía plaza de extranjero. Confirmar caso a caso.",
     "US-born or a US international: would not normally take an international slot. Confirm case by case."),
    ("Sin jugadores de Miami", "No Miami players"), ("sin Miami", "no Miami"),
    ("Posición del radar", "Radar position"), ("Posiciones", "Positions"), ("Posición", "Position"),
    ("Cuánto juega ahí", "How often he plays there"), ("A veces", "Sometimes"), ("Habitualmente", "Usually"),
    ("Casi siempre", "Almost always"), ("habitualmente", "usually"), ("a veces", "sometimes"), ("casi siempre", "almost always"),
    ("Titular en esas posiciones en el", "Started in those positions in"), ("% o más de sus partidos", "% or more of his matches"),
    ("Según dónde fue titular en sus dos últimas temporadas: 'a veces' = al menos el 10% de sus titularidades en esas posiciones, 'habitualmente' = 30%, 'casi siempre' = 70%. Si su liga no trae la posición en la alineación, se usa la de su ficha.",
     "From where he started in his last two seasons: 'sometimes' = at least 10% of his starts in those positions, 'usually' = 30%, 'almost always' = 70%. If his league has no lineup positions, his listed position is used."),
    ("Clic para marcar o desmarcar; puedes elegir varias.", "Click to select or deselect; several allowed."),
    ("Marca al menos una posición en la cancha.", "Select at least one position on the pitch."),
    ("Portero (no disponible)", "Goalkeeper (not available)"),
    ("Temporadas a usar", "Seasons to use"), ("Temporadas", "Seasons"), ("Actual + anterior", "Current + previous"),
    ("Solo la actual", "Current only"), ("Solo la anterior", "Previous only"), ("actual + anterior", "current + previous"),
    ("solo la actual", "current only"), ("solo la anterior", "previous only"),
    ("Por liga: 'actual' es 2026 en Chile o la USL y 2026/27 en Inglaterra o México; 'anterior' es 2025 o 2025/26. Cada temporada necesita 600+ minutos.",
     "Per league: 'current' is 2026 in Chile or the USL and 2026/27 in England or Mexico; 'previous' is 2025 or 2025/26. Each season needs 600+ minutes."),
    ("Ojo: en las ligas europeas, México y Centroamérica la temporada 2026/27 recién empezó y pocos llegan a 600 minutos.",
     "Note: in Europe, Mexico and Central America the 2026/27 season has just started and few players reach 600 minutes."),
    ("Filtros:", "Filters:"), ("Ordenar por", "Sort by"), ("Más parecidos primero", "Most similar first"),
    ("Mejor nivel primero", "Highest level first"), ("Más jóvenes primero", "Youngest first"),
    ("Más minutos jugados", "Most minutes played"), ("(mayor primero)", "(highest first)"),
    ("Mostrar solo con al menos…", "Show only with at least…"), ("Sin mínimo", "No minimum"),
    ("Solo jugadores con", "Only players with"), ("o más en", "or more in"), ("Mostrar", "Show"),
    # results
    ("jugadores en toda la base (30 ligas) cumplen los filtros. Valores de:", "players in the whole database (30 leagues) pass the filters. Values from:"),
    ("(600+ minutos cada una), tal cual, sin ajustar por nivel de liga. Para abrir la ficha de uno, marca la casilla al inicio de su fila.",
     "(600+ minutes each), as recorded, not adjusted for league level. To open a player's card, tick the box at the start of his row."),
    ("Club actual", "Current club"), ("Liga (datos)", "League (data)"), ("País", "Country"), ("Minutos", "Minutes"),
    ("Jugador", "Player"), ("% minutos esta temporada", "% minutes this season"), ("% minutos", "% minutes"),
    ("Referencia", "Reference"), ("Buscando", "Looking for"), ("que juegan como", "who play like"),
    ("él", "him"), ("ellos", "them"), ("pasan los filtros", "pass the filters"),
    ("¿Cómo leer esta lista?", "How to read this list"),
    ("- **#1, #2…**: su lugar en la lista, según el orden que elijas.", "- **#1, #2…**: his place in the list, in the order you chose."),
    ("Parecido a", "Similarity to"), ("** (0 a 100): cuánto se parece su forma de jugar a la de", "** (0 to 100): how much his way of playing resembles"),
    (", comparado con todos los", ", compared with all the"),
    ("de la base. 100 = de los más parecidos; 50 = en la mitad. Mide estilo (cuánto remata, toca, disputa duelos aéreos…), no si es mejor o peor.",
     "in the database. 100 = among the most similar; 50 = halfway. It measures style (how much he shoots, touches, contests aerials…), not whether he is better or worse."),
    ("- **Nivel en su liga**: qué tan bien hace las cosas: sus porcentajes de acierto (pases, duelos, regates…) comparados con los jugadores de su posición en su propia liga. *Por encima*: mejores porcentajes que la mayoría de su liga. *En el promedio*: parecidos al resto. *Por debajo*: peores.",
     "- **Level in his league**: how well he does things: his success rates (passes, duels, dribbles…) compared with the players of his position in his own league. *Above*: better rates than most of his league. *Average*: like the rest. *Below*: worse."),
    ("- **% de los minutos**: qué parte de los minutos de su equipo jugó esta temporada (100% = jugó todo).",
     "- **% of minutes**: the share of his team's minutes he played this season (100% = played everything)."),
    ("- **min analizados**: los minutos de sus dos últimas temporadas que se usaron para calcular todo esto.",
     "- **min analysed**: the minutes from his last two seasons used for all of this."),
    ("Se parece en / Más que", "Similar in / More than"), ("/ Menos que", "/ Less than"),
    ("**: en qué estadísticas su perfil está más cerca del de", "**: in which stats his profile is closest to"),
    (", y en cuáles se despega hacia arriba o hacia abajo (todo medido contra su propia liga).",
     ", and in which it departs upward or downward (all measured against his own league)."),
    ("abre el radar lado a lado con", "opens the side-by-side radar with"),
    (", listo para descargar en PDF. **Ver ficha**: todos sus números.", ", ready to download as PDF. **Player card**: all his numbers."),
    ("Radar lado a lado con", "Side-by-side radar with"), (", listo para descargar", ", ready to download"),
    ("Se parece en:", "Similar in:"), ("Más que", "More than"), ("Menos que", "Less than"),
    ("min analizados", "min analysed"), ("% de los minutos de su equipo en", "% of his team's minutes in"),
    ("% de los minutos en", "% of minutes in"), ("Ver ficha", "Player card"), ("Ver 10 más (", "Show 10 more ("),
    ("restantes)", "left)"),
    (": menos de 600 minutos en una temporada. Su perfil se acerca al promedio de la posición (con pocos minutos sus números todavía no son confiables), así que los parecidos son más genéricos.",
     ": under 600 minutes in a season. His profile is pulled toward the position average (with few minutes his numbers are not reliable yet), so the matches are more generic."),
    # card
    ("Volver a", "Back to"), ("según sus números · en su ficha figura como", "by his numbers · listed as"),
    ("Con qué posición se comparan sus números. Se elige sola según cómo juega; cámbiala si quieres verlo como otra cosa.",
     "Which position his numbers are compared with. Picked from how he plays; change it to see him as something else."),
    ("Según sus números de", "From his numbers in"), (", comparado con los", ", compared with the"),
    ("de nuestras 30 ligas, sin ajustar por nivel de liga.", "in our 30 leagues, not adjusted for league level."),
    ("Dónde juega", "Where he plays"), ("Alineaciones:", "Lineups:"),
    ("% = probabilidad según sus números (modelo que acierta la posición el", "% = probability from his numbers (the model gets the position right"),
    ("% de las veces; la tiene entre sus dos primeras el", "% of the time; within its top two"),
    ("Sus números", "His numbers"), ("Sin temporadas con 600+ minutos para mostrar números.", "No seasons with 600+ minutes to show."),
    ("Sin temporadas con 600+ minutos.", "No seasons with 600+ minutes."),
    ("▲ entre el 30% más alto de los", "▲ in the top 30% of"), ("de nuestras ligas · ▼ entre el 30% más bajo. Valores reales de sus dos últimas temporadas, sin ajustar por nivel de liga. * su liga no registra ese dato, o tiene muy pocos intentos.",
     "in our leagues · ▼ in the bottom 30%. Real values from his last two seasons, not adjusted for league level. * his league does not record that stat, or too few attempts."),
    ("sin dato*", "no data*"), ("Ataque", "Attack"), ("Creación", "Creation"), ("Pase", "Passing"), ("Duelos", "Duels"),
    ("Defensa", "Defence"),
    ("Radar vs Miami", "Radar vs Miami"), ("Jugadores parecidos a él", "Players like him"),
    ("Comparar con (Miami)", "Compare with (Miami)"), ("📊 Abrir en Comparar (para exportar)", "📊 Open in Compare (to export)"),
    ("Los más parecidos a", "The most similar to"), ("como", "as"),
    (", con 1.200+ minutos y nivel al menos el promedio de su liga. Parecido: 100 = el más parecido de todos los de la posición.",
     ", with 1,200+ minutes and at least league-average level. Similarity: 100 = the most similar of the whole position."),
    ("Temporada", "Season"), ("Club", "Club"), ("Liga", "League"), ("Titular", "Starts"), ("Goles", "Goals"), ("Asist.", "Assists"),
    ("Solo competencias de nuestras 30 ligas en Sportmonks (sin copas ni selecciones).", "Only our 30 Sportmonks leagues (no cups or national teams)."),
    ("☆ Agregar a lista corta", "☆ Add to shortlist"), ("★ En la lista corta", "★ On the shortlist"), ("Clic para sacarlo", "Click to remove"),
    ("Jugador sin datos.", "No data for this player."),
    # headline words
    ("(entre el 20% más alto de los", "(in the top 20% of"), ("sin estadísticas en las que destaque frente a los", "with no stat that stands out against the"),
    ("de números parejos: nada muy por encima ni muy por debajo de los", "with even numbers: nothing far above or below the"),
    ("muchos", "many"), ("muchas", "many"), ("mucho", "high"), ("mucha", "high"), ("pocos", "few"), ("pocas", "few"),
    ("poco", "low"), ("poca", "low"), ("con", "with"),
    # compare
    ("Jugadores (hasta 4)", "Players (up to 4)"), ("Agregar desde la lista corta", "Add from the shortlist"),
    ("Elige al menos un jugador.", "Pick at least one player."), ("Temporada actual", "Current season"), ("Últimas dos", "Last two"),
    ("Los ejes del radar son los de esta posición.", "The radar axes are this position's."),
    ("Temporadas usadas:", "Seasons used:"), (". Valores tal cual (sin ajustar por liga). ▲ = el mejor del grupo en esa estadística. Radar con escala fija para la posición: centro = el 5% más bajo de la base, borde = el 5% más alto.",
     ". Values as recorded (not league-adjusted). ▲ = best of the group in that stat. Radar on a fixed scale for the position: centre = bottom 5% of the database, edge = top 5%."),
    (": Sportmonks tiene incompleta la MLS Next Pro (faltan partidos, por ejemplo 6 de 24 de Richmond en 2026). Para mandar estos números, usa Wyscout.",
     ": Sportmonks' MLS Next Pro coverage is incomplete (missing matches, e.g. 6 of Richmond's 24 in 2026). Use Wyscout before sending these numbers."),
    ("Generar reporte", "Generate report"), ("El reporte lleva la fecha, la fuente de los datos y las temporadas usadas. Azul = el primer jugador de la lista (normalmente el de Miami).",
     "The report carries the date, the data source and the seasons used. Blue = the first player in the list (normally the Miami player)."),
    ("Idioma", "Language"), ("⬇ Imagen (PNG, para WhatsApp)", "⬇ Image (PNG, for WhatsApp)"), ("Vista previa", "Preview"),
    ("⚠️ Hay jugadores de la MLS Next Pro: en Sportmonks les faltan partidos. Para un reporte, mejor el one-pager con Wyscout.",
     "⚠️ MLS Next Pro players here: Sportmonks is missing some of their matches. For a report, the Wyscout one-pager is safer."),
    # shortlist
    ("Guardada en la Google Sheet del club: permanente y compartida.", "Saved in the club's Google Sheet: permanent and shared."),
    ("Guardada solo en este servidor: en la versión online se borra cada vez que la app se reinicia. Para que sea permanente, conecta una Google Sheet (scouting/SHORTLIST_SETUP.md).",
     "Saved only on this server: the online version loses it whenever the app restarts. To make it permanent, connect a Google Sheet (scouting/SHORTLIST_SETUP.md)."),
    ("La Google Sheet configurada no respondió (", "The configured Google Sheet did not respond ("),
    ("Todavía no hay jugadores. Abre la ficha de un jugador y toca «☆ Agregar a lista corta».", "No players yet. Open a player's card and tap «☆ Add to shortlist»."),
    ("Cambia el <b>Estado</b> y escribe <b>Notas</b> directamente en la tabla; después toca «Guardar cambios».",
     "Change the <b>Status</b> and write <b>Notes</b> directly in the table, then tap «Save changes»."),
    ("Estado", "Status"), ("Agregado", "Added"), ("Nota", "Note"), ("Quitar", "Remove"), ("Guardar cambios", "Save changes"),
    ("Descargar (CSV)", "Download (CSV)"), ("Abrir ficha", "Open card"), ("por ver", "to watch"), ("visto", "watched"),
    ("descartado", "discarded"),
    # home
    ("Jugadores de 30 ligas (USL, MLS, Sudamérica, Centroamérica, Inglaterra, Escandinavia), temporadas 2024 a 2026 · datos Sportmonks actualizados el",
     "Players from 30 leagues (USL, MLS, South America, Central America, England, Scandinavia), seasons 2024 to 2026 · Sportmonks data updated"),
    ("🧬 Reemplazar a un jugador de Miami", "🧬 Replace a Miami player"),
    ("Elige a uno del plantel y mira quién juega parecido en otras ligas, con filtros de edad, minutos y mercado.",
     "Pick one from the squad and see who plays like him in other leagues, with age, minutes and market filters."),
    ("Buscar parecidos", "Find similar players"),
    ("Marca una o varias posiciones en la cancha y filtra toda la base por edad, minutos, liga, nacionalidad y estadísticas.",
     "Select one or several positions on the pitch and filter the whole database by age, minutes, league, nationality and stats."),
    ("Abrir el buscador", "Open the search"), ("⭐ Mi lista corta", "⭐ My shortlist"), ("Ver la lista", "See the list"),
    ("jugadores guardados", "players saved"), ("jugador guardado", "player saved"),
    (", con estado y notas. Desde ahí se abre cada ficha y se comparan.", ", with status and notes. From there each card opens and players are compared."),
    ("**Búsquedas recientes**", "**Recent searches**"), ("Las búsquedas que hagas en esta sesión quedan aquí para volver a ellas.",
                                                      "Searches you run in this session stay here so you can return to them."),
    ("Parecidos a", "Similar to"), ("Buscar:", "Search:"),
    ("¿Qué hay detrás de los números?", "What is behind the numbers?"),
    ("- **Datos:** Sportmonks (estadísticas de partido). No es Wyscout. Sin copas ni selecciones.", "- **Data:** Sportmonks (match statistics). Not Wyscout. No cups or national teams."),
    ("- **Valores tal cual:** no se ajustan por nivel de liga. Un gol en Bolivia y uno en la USL cuentan igual.",
     "- **Values as recorded:** not adjusted for league level. A goal in Bolivia and one in the USL count the same."),
    ("- **Lo que falta:** algunas ligas no registran pases al último tercio ni recuperaciones; la app lo marca como «sin dato» en vez de poner cero. En MLS Next Pro faltan partidos.",
     "- **What is missing:** some leagues do not record final-third passes or recoveries; the app shows «no data» instead of a zero. MLS Next Pro is missing matches."),
    ("- **Posición:** la que la app calcula por sus números acierta 8 de cada 10 veces (9 de 10 contando su segunda opción). En «Buscar por posición» se usa además dónde fue titular en las alineaciones.",
     "- **Position:** the one the app infers from the numbers is right 8 times in 10 (9 in 10 counting its second choice). «Search by position» also uses where he started in the lineups."),
    ("- **Parecido:** compara el estilo (cuánto remata, toca, disputa en el aire…) de cada jugador con el de la referencia, medido contra su propia liga. No dice si es mejor o peor; para eso está «Nivel».",
     "- **Similarity:** compares each player's style (how much he shoots, touches, contests in the air…) with the reference, measured against his own league. It does not say whether he is better or worse; that is «Level»."),
    # loading
    ("Cargando la base: 30 ligas, 3 temporadas, ~55.000 temporadas de jugador (solo demora la primera vez)…",
     "Loading the database: 30 leagues, 3 seasons, ~55,000 player-seasons (only slow the first time)…"),
    # positions (groups, plurals, slots, listed)
    ("Delantero centro (DC)", "Centre-forward (CF)"), ("Extremo (EI/ED)", "Winger (LW/RW)"), ("Mediapunta (MCO)", "Attacking midfielder (AM)"),
    ("Mediocentro (MED)", "Central midfielder (CM)"), ("Lateral (LD/LI)", "Full-back (RB/LB)"), ("Defensa central (DFC)", "Centre-back (CB)"),
    ("delanteros centro", "centre-forwards"), ("delantero centro", "centre-forward"), ("extremos", "wingers"),
    ("extremo izquierdo", "left winger"), ("extremo derecho", "right winger"), ("extremo", "winger"),
    ("mediapuntas", "attacking midfielders"), ("mediapunta", "attacking midfielder"), ("mediocentros", "central midfielders"),
    ("mediocentro defensivo", "defensive midfielder"), ("mediocentro", "central midfielder"),
    ("laterales", "full-backs"), ("lateral izquierdo", "left-back"), ("lateral derecho", "right-back"), ("lateral", "full-back"),
    ("carrilero izquierdo", "left wing-back"), ("carrilero derecho", "right wing-back"),
    ("volante izquierdo", "left midfielder"), ("volante derecho", "right midfielder"),
    ("defensas centrales", "centre-backs"), ("defensa central", "centre-back"), ("segundo delantero", "second striker"),
    ("delantera", "forward line"), ("mediocampo", "midfield"), ("defensa", "defence"), ("arco", "goal"),
    ("Portero", "Goalkeeper"), ("portero", "goalkeeper"), ("Delantero", "Forward"), ("delantero", "forward"),
    ("Mediocampista", "Midfielder"), ("mediocampista", "midfielder"), ("Defensor", "Defender"), ("defensor", "defender"),
    # stats (labels in radar.STATS and the short forms on the card)
    ("por 90 min", "per 90"), ("— % de éxito", "— success %"), ("— % del total", "— % of total"),
    ("Remates al arco", "Shots on target"), ("Remates", "Shots"), ("remates al arco", "shots on target"), ("remates", "shots"),
    ("Goles", "Goals"), ("goles", "goals"), ("Asistencias", "Assists"), ("asistencias", "assists"),
    ("Pases clave", "Key passes"), ("pases clave", "key passes"), ("Pases al último tercio", "Final-third passes"),
    ("pases al último tercio", "final-third passes"), ("Toques", "Touches"), ("toques", "touches"),
    ("Pases largos", "Long balls"), ("pases largos", "long balls"), ("Pase largo", "Long ball"),
    ("Pases/90", "Passes/90"), ("Pases", "Passes"), ("Pase %", "Pass %"), ("volumen de pase", "pass volume"),
    ("precisión de pase", "pass accuracy"), ("precisión en pase largo", "long-ball accuracy"),
    ("Regates intentados", "Dribbles attempted"), ("Regates", "Dribbles"), ("regates", "dribbles"), ("Regate", "Dribble"),
    ("éxito en el regate", "dribble success"), ("Centros", "Crosses"), ("centros", "crosses"), ("Centro —", "Cross —"),
    ("Centro %", "Cross %"), ("precisión de centro", "cross accuracy"), ("Faltas recibidas", "Fouls drawn"),
    ("faltas recibidas", "fouls drawn"), ("Duelos aéreos", "Aerial duels"), ("duelos aéreos", "aerial duels"),
    ("Duelo aéreo", "Aerial duel"), ("duelos", "duels"), ("éxito en duelos", "duel success"), ("éxito en el aire", "aerial success"),
    ("Entradas", "Tackles"), ("entradas", "tackles"), ("Intercepciones", "Interceptions"), ("intercepciones", "interceptions"),
    ("Despejes", "Clearances"), ("despejes", "clearances"), ("Recuperaciones", "Recoveries"), ("recuperaciones", "recoveries"),
    ("pérdidas", "possession lost"), ("precisión de remate", "shot accuracy"),
    ("Escala fija para la posición: centro = el 5% más bajo de la base, borde = el 5% más alto. Valores reales en la tabla.",
     "Fixed scale for the position: centre = bottom 5% of the database, edge = top 5%. Real values in the table."),
    ("* sin dato (su liga no lo registra o tiene muy pocos intentos):", "* no data (not recorded in his league, or too few attempts):"),
    # dynamic sentences that would otherwise need a bare "de"/"con"/"como"
    ("que juegan como él", "who play like him"), ("que juegan como ellos", "who play like them"),
    ("como delantero centro", "as a centre-forward"), ("como extremo", "as a winger"), ("como mediapunta", "as an attacking midfielder"),
    ("como mediocentro", "as a central midfielder"), ("como lateral", "as a full-back"), ("como defensa central", "as a centre-back"),
    ("con muchos", "with many"), ("con muchas", "with many"), ("con mucho", "with high"), ("con mucha", "with high"),
    ("Volver a Ficha de", "Back to the card of"), ("Ficha:", "Card:"), ("Parecidos a Miami FC", "Similar to Miami FC"),
    ("Pase — % de éxito", "Pass — success %"), ("Pase largo — % de éxito", "Long ball — success %"),
    ("Regate — % de éxito", "Dribble — success %"), ("Centro — % de éxito", "Cross — success %"),
    ("Duelo aéreo — % de éxito", "Aerial duel — success %"), ("Duelos — % de éxito", "Duels — success %"),
    ("Remates al arco — % del total", "Shots on target — % of total"), ("Duelos %", "Duels %"), ("Duelo aéreo %", "Aerial duel %"),
    ("Pase largo %", "Long ball %"), ("Regate %", "Dribble %"),
    ("Competencia", "League"), ("Nivel", "Level"), ("Parecido", "Similarity"), ("jugadores", "players"), ("jugador", "player"),
    ("PJ", "apps"), ("Por defecto solo el plantel", "By default only the squad of"),
]
_P = [(es, en) for es, en in _P if es not in ("Club", "Liga", "Todos", "Por defecto solo el plantel", "con", "de", "y", "a", "en", "como", "él", "ellos")] + [("Por defecto solo el plantel", "By default only the squad of")]
# " y " between two words (recent-search labels: "Parecidos a X y Z"); never bare "y"
_EXTRA = [(re.compile(r"(?<=\w) y (?=\w)"), " and "), (re.compile(r"De (\d+) a (\d+) (?:años|yrs)"), r"From \1 to \2 yrs")]


_L = "A-Za-zÁÉÍÓÚÜáéíóúüñÑ"


def _rx(phrase):
    """Word boundaries only where the phrase itself starts/ends with a letter (so ', con…' can follow a word)."""
    pre = rf"(?<![{_L}])" if re.match(rf"[{_L}]", phrase) else ""
    post = rf"(?![{_L}])" if re.search(rf"[{_L}]$", phrase) else ""
    return re.compile(pre + re.escape(phrase) + post)


_RULES = []          # (regex, english, phrase length)
for es, en in _P:
    _RULES.append((_rx(es), en, len(es)))
    if es[:1].islower() and es[:1].isalpha():
        _RULES.append((_rx(es[0].upper() + es[1:]), en[0].upper() + en[1:], len(es)))
# longest PHRASES first so "Minutos jugados (mínimo)" wins over "Minutos"; the two regex extras go last
_seen, _uniq = set(), []
for r in _RULES:
    if r[0].pattern not in _seen:
        _seen.add(r[0].pattern); _uniq.append(r)
_RULES = [(rx, en) for rx, en, _ in sorted(_uniq, key=lambda r: -r[2])] + list(_EXTRA)


def tr(s):
    """Translate one string (or each string in a list/tuple); anything else is returned as is."""
    if lang() != "en":
        return s
    if isinstance(s, (list, tuple)):
        return type(s)(tr(x) for x in s)
    if not isinstance(s, str) or not s:
        return s
    for rx, en in _RULES:
        s = rx.sub(en, s)
    return s


# ---------------------------------------------------------------- install: wrap the Streamlit API once
_TEXT_KW = ("label", "help", "placeholder", "body", "format", "caption")
_INSTALLED = False


def _wrap_fn(fn, text_pos=(0,), list_pos=(), fmt=False, frame=False, has_self=True):
    off = 1 if has_self else 0            # DeltaGenerator methods receive self first

    def wrapped(*args, **kwargs):
        if lang() == "en":
            args = list(args)
            for i in (off + j for j in text_pos):
                if i < len(args) and isinstance(args[i], str):
                    args[i] = tr(args[i])
            for i in (off + j for j in list_pos):
                if i < len(args) and isinstance(args[i], (list, tuple)):
                    args[i] = tr(args[i])
            for k in _TEXT_KW:
                if isinstance(kwargs.get(k), str):
                    kwargs[k] = tr(kwargs[k])
            if fmt:
                f = kwargs.get("format_func")
                kwargs["format_func"] = (lambda o, f=f: tr(f(o))) if f else (lambda o: tr(o) if isinstance(o, str) else str(o))
            if frame:
                import pandas as pd
                if len(args) > off and isinstance(args[off], pd.DataFrame):
                    args[off] = args[off].rename(columns=lambda c: tr(c) if isinstance(c, str) else c)
                cc = kwargs.get("column_config")
                if isinstance(cc, dict):
                    kwargs["column_config"] = {tr(k) if isinstance(k, str) else k: v for k, v in cc.items()}
                if isinstance(kwargs.get("disabled"), (list, tuple)):
                    kwargs["disabled"] = tr(kwargs["disabled"])
            args = tuple(args)
        return fn(*args, **kwargs)
    wrapped.__name__ = getattr(fn, "__name__", "wrapped")
    return wrapped


def install():
    """Wrap text-taking Streamlit calls so English mode needs no changes in the page code."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    from streamlit.delta_generator import DeltaGenerator as DG
    spec = {
        "markdown": {}, "caption": {}, "title": {}, "header": {}, "subheader": {}, "info": {}, "warning": {},
        "error": {}, "success": {}, "write": {}, "button": {}, "download_button": {}, "toggle": {}, "checkbox": {},
        "slider": {}, "number_input": {}, "text_input": {}, "expander": {}, "page_link": {"text_pos": ()},
        "selectbox": {"fmt": True}, "multiselect": {"fmt": True}, "segmented_control": {"fmt": True},
        "pills": {"fmt": True}, "radio": {"fmt": True}, "tabs": {"text_pos": (), "list_pos": (0,)},
        "dataframe": {"text_pos": (), "frame": True}, "data_editor": {"text_pos": (), "frame": True},
    }
    for name, opts in spec.items():
        orig = getattr(DG, name, None)
        if orig is None:
            continue
        w = _wrap_fn(orig, **opts)
        setattr(DG, name, w)
        if hasattr(st, name):                      # st.<name> is bound to the main container at import
            main = st._main if hasattr(st, "_main") else None
            setattr(st, name, (lambda w=w, main=main: (lambda *a, **k: w(main, *a, **k)))() if main is not None
                    else getattr(DG, name))
    for cname in ("TextColumn", "NumberColumn", "ProgressColumn", "CheckboxColumn", "SelectboxColumn", "LinkColumn"):
        c = getattr(st.column_config, cname, None)
        if c is not None:
            setattr(st.column_config, cname, _wrap_fn(c, has_self=False))

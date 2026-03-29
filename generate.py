"""
Monitor Centroamérica — Banco Mundial
Robot de generación del dashboard
Llama a Gemini, obtiene noticias reales y genera index.html completo
"""
 
import os
import requests
import json
from datetime import datetime, timezone, timedelta
 
# ─── CONFIG ───────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL   = "gemini-2.0-flash"
URL     = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
 
CR_TZ   = timezone(timedelta(hours=-6))
NOW     = datetime.now(CR_TZ)
TODAY   = NOW.strftime("%A %d de %B de %Y")
TIME    = NOW.strftime("%H:%M")
DATE_LABEL = NOW.strftime("%d/%m/%Y %H:%M") + " (CR)"
 
SYSTEM = f"""Eres un analista de inteligencia de seguridad especializado en Centroamérica para el Banco Mundial.
FECHA HOY: {TODAY}, {TIME} hora de Costa Rica.
REGLA CRÍTICA: Usa Google Search. Incluye noticias de hoy Y de los últimos 7 días cuando sean relevantes.
Siempre menciona la fecha de cada noticia. Texto limpio, sin asteriscos ni markdown.
Cubre: Guatemala, El Salvador, Honduras, Nicaragua, Costa Rica, Panamá.
Prioridades: bloqueos viales, manifestaciones, seguridad, alertas climáticas, riesgos políticos.
Responde en español."""
 
# ─── GEMINI CALL ──────────────────────────────────────────────────────────────
def ask(prompt):
    if not API_KEY:
        print("⚠ Sin API key de Gemini")
        return {"text": "Sin API key configurada.", "sources": []}
    import time
    time.sleep(10)  # pause 10s to respect 10 RPM limit
    try:
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 1800, "temperature": 0.2},
            "tools": [{"googleSearch": {}}]
        }
        r = requests.post(URL, json=body, timeout=60)
        r.raise_for_status()
        d = r.json()
        parts = d.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        text = text.replace("**", "").replace("*", "").strip()
        sources = []
        chunks = d.get("candidates", [{}])[0].get("groundingMetadata", {}).get("groundingChunks", [])
        seen = set()
        for c in chunks:
            web = c.get("web", {})
            url = web.get("uri", "")
            title = web.get("title", "")
            if url and title and url not in seen:
                sources.append({"title": title, "url": url})
                seen.add(url)
        return {"text": text, "sources": sources}
    except Exception as e:
        msg = str(e)
        if "429" in msg:
            print(f"  429 rate limit - esperando 30s y reintentando...")
            import time
            time.sleep(30)
            try:
                r2 = requests.post(URL, json=body, timeout=60)
                r2.raise_for_status()
                d2 = r2.json()
                parts2 = d2.get("candidates",[{}])[0].get("content",{}).get("parts",[])
                text2 = "".join(p.get("text","") for p in parts2).replace("**","").replace("*","").strip()
                sources2 = []
                for ch in d2.get("candidates",[{}])[0].get("groundingMetadata",{}).get("groundingChunks",[]):
                    w = ch.get("web",{})
                    if w.get("uri") and w.get("title"):
                        sources2.append({"title":w["title"],"url":w["uri"]})
                return {"text": text2, "sources": sources2}
            except Exception as e2:
                print(f"Error Gemini reintento: {e2}")
                return {"text": f"Sin datos disponibles en este momento.", "sources": []}
        print(f"Error Gemini: {e}")
        return {"text": f"Error al consultar Gemini: {e}", "sources": []}
 
# ─── PARSE STRUCTURED NEWS ────────────────────────────────────────────────────
def parse_news(result):
    text = result.get("text", "")
    sources = result.get("sources", [])
    items = []
    for i, line in enumerate(text.split("\n")):
        if "|" not in line:
            continue
        parts = [p.strip().lstrip("0123456789.) ") for p in line.split("|")]
        if len(parts) < 4:
            continue
        src = sources[i] if i < len(sources) else (sources[0] if sources else {})
        items.append({
            "level":    parts[0] if parts[0] else "MEDIO",
            "category": parts[1] if len(parts) > 1 else "",
            "title":    parts[2] if len(parts) > 2 else "",
            "description": parts[3] if len(parts) > 3 else "",
            "location": parts[4] if len(parts) > 4 else "Centroamérica",
            "date":     parts[5] if len(parts) > 5 else TODAY[:10],
            "source_title": src.get("title", "")[:50],
            "source_url":   src.get("url", "#"),
        })
    return items
 
# ─── HTML HELPERS ─────────────────────────────────────────────────────────────
def level_cls(level):
    if "CRÍTICO" in level: return "crit"
    if "ALTO" in level:    return "alto"
    if "MEDIO" in level:   return "med"
    return "low"
 
def badge_html(level, category="", is_new=False):
    cls = level_cls(level)
    new_badge = '<span class="nb new">NOVO</span>' if is_new else ""
    cat_badge = f'<span class="nb cat">{category}</span>' if category else ""
    return f'<span class="nb {cls}">{level}</span>{cat_badge}{new_badge}'
 
def news_card(item, is_new=False):
    cls = level_cls(item["level"])
    url = item["source_url"] or "#"
    target = 'target="_blank" rel="noopener"' if url != "#" else ""
    new_badge = '<span class="card-new">NOVO</span>' if is_new else ""
    return f'''<a class="nc {cls}" href="{url}" {target}>
  {new_badge}
  <div class="nc-top">{badge_html(item["level"], item["category"])}</div>
  <h3>{item["title"]}</h3>
  <p>{item["description"]}</p>
  <div class="nc-foot">
    <span class="nc-loc">📍 {item["location"]}</span>
    <span class="nc-date">{item["date"]}</span>
    <span class="nc-src">↗ {item["source_title"] or "Ver fuente"}</span>
  </div>
</a>'''
 
def sources_html(sources):
    if not sources:
        return ""
    items = "".join(
        f'<a href="{s["url"]}" target="_blank" rel="noopener" class="src-link">'
        f'<svg viewBox="0 0 16 16" fill="currentColor" width="11" height="11">'
        f'<path d="M8.636 3.5a.5.5 0 0 0-.5-.5H1.5A1.5 1.5 0 0 0 0 4.5v10A1.5 1.5 0 0 0 1.5 16h10a1.5 1.5 0 0 0 1.5-1.5V7.864a.5.5 0 0 0-1 0V14.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5h6.636a.5.5 0 0 0 .5-.5z"/>'
        f'<path d="M16 .5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0 0 1h3.793L6.146 9.146a.5.5 0 1 0 .708.708L15 1.707V5.5a.5.5 0 0 0 1 0v-5z"/></svg>'
        f'{s["title"][:55]}</a>'
        for s in sources
    )
    return f'<div class="sources"><div class="src-label">Fuentes verificadas</div>{items}</div>'
 
def date_item(parts):
    if len(parts) < 4:
        return ""
    nivel = parts[5] if len(parts) > 5 else parts[4] if len(parts) > 4 else "MEDIO"
    cls = level_cls(nivel)
    badge_cls = "nb " + cls
    return f'''<div class="di {cls}">
  <div class="di-date"><div class="di-day">{parts[0]}</div><div class="di-mon">{parts[1]}</div></div>
  <div class="di-body">
    <div class="di-title">{parts[3]}</div>
    <div class="di-desc">{parts[4] if len(parts) > 4 else ""}</div>
    <div class="di-meta"><span class="{badge_cls}">{nivel}</span><span class="nb cat">{parts[2]}</span></div>
  </div>
</div>'''
 
# ─── FETCH ALL DATA ───────────────────────────────────────────────────────────
print("🔍 Obteniendo datos de Gemini...")
 
print("  → Risk cards...")
r_risk = ask(f"""Para el dashboard del Banco Mundial, dame en 5 líneas el resumen de riesgo HOY en Centroamérica:
OPERACIONAL: [resumen breve con país y fecha]
POLÍTICO: [resumen breve con país y fecha]
CLIMÁTICO: [alertas activas hoy con país]
SOCIAL: [protestas o movimientos activos con país]
SEGURIDAD: [incidentes de seguridad recientes con país]
Máximo 30 palabras por línea.""")
 
print("  → Alertas...")
r_alerts = ask(f"""Busca en Google las 8 alertas más importantes de los ÚLTIMOS 7 DÍAS en Centroamérica para el Banco Mundial. Formato exacto, una línea por alerta:
NIVEL|CATEGORÍA|TÍTULO COMPLETO|DESCRIPCIÓN DETALLADA (3-4 oraciones con contexto, fechas e impacto para operaciones BM)|LUGAR, PAÍS|FECHA|FUENTE
Niveles: CRÍTICO, ALTO, MEDIO. Categorías: Operacional, Seguridad, Climático, Social/Crisis, Político
Ordena de mayor a menor criticidad.""")
 
print("  → Noticias...")
r_news = ask(f"""Busca en Google las 12 noticias más relevantes de los ÚLTIMOS 7 DÍAS en Centroamérica sobre seguridad, protestas, bloqueos, política o clima. Formato exacto, una línea por noticia:
NIVEL|CATEGORÍA|TÍTULO COMPLETO DE LA NOTICIA|DESCRIPCIÓN DETALLADA (3-4 oraciones con contexto completo e impacto para BM)|LUGAR, PAÍS|FECHA DD/MM/YYYY|FUENTE (nombre del medio)
Niveles: CRÍTICO, ALTO, MEDIO. Ordena de mayor a menor relevancia.""")
 
print("  → Fechas críticas...")
r_dates = ask(f"""Lista los 10 eventos y fechas críticas para los próximos 4 meses en Centroamérica relevantes para el Banco Mundial. Formato exacto:
DÍA|MES|CATEGORÍA|TÍTULO|DESCRIPCIÓN BREVE DEL IMPACTO PARA BM|NIVEL
Niveles: CRÍTICO, ALTO, MEDIO. Ordena cronológicamente.""")
 
print("  → Briefing ejecutivo...")
r_briefing = ask(f"""Escribe un briefing ejecutivo de HOY sobre Centroamérica para el Banco Mundial. Incluye:
1. La situación más crítica del momento con fecha y lugar exacto
2. Estado de carreteras y posibles bloqueos activos
3. Alertas climáticas emitidas esta semana
4. Evento político más relevante de la semana
5. Recomendación operacional para equipos en terreno
Texto limpio, sin asteriscos. Máximo 280 palabras. Cita fuentes y fechas.""")
 
print("  → Análisis de riesgo...")
r_risk_analysis = ask(f"""Genera análisis detallado de riesgo para Centroamérica. Para cada categoría una línea:
CATEGORÍA|NIVEL|ANÁLISIS DETALLADO (4-5 oraciones con eventos específicos de esta semana, tendencias y proyección)|PAÍS MÁS AFECTADO
Categorías: OPERACIONAL, POLÍTICO, CLIMÁTICO, SOCIAL/CRISIS, SEGURIDAD""")
 
# Parse data
alerts = parse_news(r_alerts)
news   = parse_news(r_news)
 
# Risk card texts
rc = {"OPERACIONAL": "Sin datos", "POLÍTICO": "Sin datos", "CLIMÁTICO": "Sin datos",
      "SOCIAL": "Sin datos", "SEGURIDAD": "Sin datos"}
for line in r_risk["text"].split("\n"):
    for k in rc:
        if line.startswith(k + ":"):
            rc[k] = line[len(k)+1:].strip()
 
# Risk analysis
risk_cards_html = ""
icons = {"OPERACIONAL":"⚙️","POLÍTICO":"🏛️","CLIMÁTICO":"🌧️","SOCIAL/CRISIS":"✊","SEGURIDAD":"🛡️"}
for line in r_risk_analysis["text"].split("\n"):
    if "|" not in line: continue
    parts = [p.strip().lstrip("0123456789.) ") for p in line.split("|")]
    if len(parts) < 3: continue
    cat, nivel, analisis = parts[0], parts[1], parts[2]
    pais = parts[3] if len(parts) > 3 else "Regional"
    cls = level_cls(nivel)
    ico = icons.get(cat, "📊")
    risk_cards_html += f'''<div class="rmc">
  <div class="rmc-head"><div class="rmc-title">{ico} {cat}</div><span class="nb {cls}">{nivel}</span></div>
  <div class="rmc-body"><p>{analisis}</p><div class="rmc-country">País más afectado: {pais}</div></div>
</div>'''
 
# Dates
dates_html = ""
for line in r_dates["text"].split("\n"):
    if "|" not in line: continue
    parts = [p.strip().lstrip("0123456789.) ") for p in line.split("|")]
    dates_html += date_item(parts)
 
# News lists
alerts_html  = "".join(news_card(a, True)  for a in alerts[:8])  or "<p style='padding:16px;color:#9ca3af'>Sin alertas recientes</p>"
news_html    = "".join(news_card(n, True)  for n in news[:12])   or "<p style='padding:16px;color:#9ca3af'>Sin noticias recientes</p>"
dash_alerts  = "".join(news_card(a, True)  for a in alerts[:4])
dash_news    = "".join(news_card(n, False) for n in news[:4])
dash_dates   = "".join(news_card({"level": d.get("di-title",""), "category":"", "title":"", "description":"", "location":"", "date":"", "source_title":"", "source_url":"#"}, False) for d in [])
# Simplified dates for dashboard
dash_dates_html = ""
for line in r_dates["text"].split("\n")[:4]:
    if "|" not in line: continue
    parts = [p.strip().lstrip("0123456789.) ") for p in line.split("|")]
    dash_dates_html += date_item(parts)
 
alert_count = len(alerts)
all_sources_alerts = sources_html(r_alerts["sources"])
all_sources_news   = sources_html(r_news["sources"])
briefing_text = r_briefing["text"]
briefing_sources = sources_html(r_briefing["sources"])
 
# ─── COUNTRY CONTEXTS (static, rich) ─────────────────────────────────────────
COUNTRY_CTX = {
    "Guatemala": {
        "flag":"🇬🇹","risk":"6.8","label":"Alto","badge":"alto",
        "pol":"""El gobierno de Bernardo Arévalo (Movimiento Semilla) enfrenta una crisis institucional sin precedentes. La Fiscal General Consuelo Porras usa el Ministerio Público como instrumento político: ha intentado desaforar diputados oficialistas, perseguido funcionarios y bloqueado reformas anticorrupción. La inestabilidad política es el principal riesgo para proyectos del Banco Mundial en el país. Sin embargo, las instituciones democráticas aún funcionan, lo que diferencia a Guatemala de Nicaragua o El Salvador.""",
        "seg":"""CODECA protagoniza bloqueos recurrentes en la CA-2 (al Pacífico), CA-1 (interamericana) y vías al occidente. Sus demandas de nacionalización eléctrica no han sido atendidas. El crimen organizado opera en Petén y zonas fronterizas. Las vías al Quiché e Ixchiguán son especialmente sensibles durante movilizaciones.""",
        "geo":"""17 millones de habitantes. Carreteras estratégicas: CA-1 (interamericana norte-sur), CA-2 (Pacífico), Ruta al Atlántico RN-9 (hacia Puerto Barrios). Temporada de lluvias mayo-octubre. Ciudad de Guatemala es el hub de operaciones BM en la región."""
    },
    "El Salvador": {
        "flag":"🇸🇻","risk":"8.8","label":"Crítico","badge":"crit",
        "pol":"""El gobierno de Nayib Bukele, reelecto con 85% en 2024, controla todos los poderes del Estado. El régimen de excepción desde 2022 ha derivado en +70.000 detenidos sin proceso judicial en el CECOT. La prensa libre fue eliminada: El Faro opera desde exilio en Costa Rica. La condicionalidad del BM choca permanentemente con el marco de DDHH del régimen.""",
        "seg":"""Las pandillas MS-13 y Barrio 18 fueron desarticuladas dentro del país. Paradoja: el país más seguro de su historia reciente bajo un régimen que viola sistemáticamente los DDHH. Riesgo para misiones del BM: restricciones de acceso, imposibilidad de trabajar con sociedad civil, y riesgo reputacional.""",
        "geo":"""El país más pequeño de Centroamérica (21.000 km²). Carretera Panamericana CA-1 como eje principal. San Salvador como hub. Sin costa caribeña. Temporada lluviosa junio-octubre."""
    },
    "Honduras": {
        "flag":"🇭🇳","risk":"7.5","label":"Alto","badge":"alto",
        "pol":"""La presidenta Xiomara Castro enfrenta fraccionamiento en su partido que bloquea el Congreso. Las extradiciones de narcotraficantes generan represalias del crimen organizado sobre funcionarios judiciales. La reforma judicial es urgente pero bloqueada políticamente.""",
        "seg":"""COPINH activo en Río Blanco e Intibucá. Conflictos agrarios en el Bajo Aguán (palma africana, DINANT). Barrio 18 y MS-13 reconfigurada en Tegucigalpa y SPS. La CA-5 es la carretera más crítica y monitoreada.""",
        "geo":"""Acceso al Caribe (Puerto Cortés) y Pacífico. CA-5 es el eje económico principal. Corredor Seco vulnerable a sequías. Tegucigalpa en cuenca del Choluteca con riesgo histórico de inundaciones."""
    },
    "Nicaragua": {
        "flag":"🇳🇮","risk":"9.5","label":"Crítico","badge":"crit",
        "pol":"""El régimen de Ortega-Murillo es el más cerrado de Centroamérica. Toda oposición fue eliminada. La Iglesia fue atacada: obispos detenidos y expulsados. 300+ ONGs clausuradas. La información confiable solo viene de medios en exilio.""",
        "seg":"""Sin sociedad civil activa. La Policía actúa como instrumento político-represivo. No hay protestas visibles. El principal indicador de crisis es el exilio masivo: 700.000+ personas emigraron desde 2018. Acceso muy limitado para organizaciones internacionales.""",
        "geo":"""Lago Nicaragua como recurso estratégico. Frontera sur con Costa Rica, norte con Honduras. Costa caribeña vulnerable a huracanes (junio-noviembre). Acceso físico difícil para misiones internacionales."""
    },
    "Costa Rica": {
        "flag":"🇨🇷","risk":"2.8","label":"Bajo","badge":"low",
        "pol":"""El gobierno de Rodrigo Chaves mantiene conflictos con la Asamblea Legislativa pero las instituciones democráticas operan con normalidad. Costa Rica es el hub regional del BM, sede de múltiples agencias ONU y punto de exilio para activistas y periodistas de la región.""",
        "seg":"""El crimen organizado usa Costa Rica como corredor de tránsito, aumentando la violencia en zonas costeras. La Fuerza Pública mantiene el orden. Las 18 instituciones monitoreadas (IMN, CNE, Bomberos, Tránsito) son fuentes de información confiables.""",
        "geo":"""Posición estratégica entre Nicaragua y Panamá. Ruta 27 (San José-Caldera) y Ruta 1 (norte) son críticas. San José concentra la mayoría de operaciones BM. Temporada lluviosa intensa en Caribe (todo el año) y Pacífico (mayo-noviembre)."""
    },
    "Panamá": {
        "flag":"🇵🇦","risk":"4.5","label":"Medio","badge":"med",
        "pol":"""El gobierno de Mulino enfrenta el arbitraje de First Quantum (USD 20 mil millones) por la cancelación del contrato de Cobre Panamá. El Frente Anti-Minero sigue activo. El Canal atraviesa su peor crisis hídrica en décadas.""",
        "seg":"""Panamá es relativamente estable pero el Darién es zona sin ley: 520.000+ migrantes cruzaron en 2023. Pandillas operan en la región del Darién. Ciudad de Panamá es segura para operaciones.""",
        "geo":"""El Canal de Panamá es la infraestructura estratégica más importante del hemisferio. La Carretera Panamericana termina en el Darién. Darién: selva densa, sin carreteras, grupos armados irregulares."""
    }
}
 
def country_section(name, data):
    badge_color = {"crit":"#dc2626","alto":"#d97706","med":"#2563eb","low":"#16a34a"}.get(data["badge"],"#6b7280")
    return f'''<div class="country-section" id="country-{name.replace(' ','-').replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u')}">
<div class="country-hero">
  <div class="ch-flag">{data["flag"]}</div>
  <div class="ch-info">
    <div class="ch-name">{name}</div>
    <div class="ch-risk">Riesgo operacional: <b style="color:{badge_color}">{data["risk"]}/10 — {data["label"]}</b></div>
  </div>
</div>
<div class="ctx-grid">
  <div class="ctx-box"><h4>🏛 Contexto político</h4><p>{data["pol"]}</p></div>
  <div class="ctx-box"><h4>🛡 Seguridad operacional</h4><p>{data["seg"]}</p></div>
  <div class="ctx-box ctx-full"><h4>🗺 Geografía y logística</h4><p>{data["geo"]}</p></div>
</div>
</div>'''
 
countries_html = "".join(country_section(name, data) for name, data in COUNTRY_CTX.items())
 
# ─── ACTORS (static) ──────────────────────────────────────────────────────────
ACTORS = [
    {"cat":"mov","name":"CODECA","flag":"🇬🇹","level":"crit","type":"Movimiento social campesino — Guatemala",
     "why":"Responsable de los principales bloqueos carreteros. Sus movilizaciones cortan la CA-2 y vías al occidente, afectando misiones del Banco Mundial.",
     "ctx":"Más de 40 bloqueos en 3 años. Demanda nacionalización eléctrica y distribución de tierras.",
     "links":[("Twitter/X","https://twitter.com/codeca_gt"),("Instagram","https://instagram.com/codeca_gt")]},
    {"cat":"mov","name":"COPINH","flag":"🇭🇳","level":"alto","type":"Organización indígena Lenca — Honduras",
     "why":"Sus conflictos en torno a proyectos hidroeléctricos pueden afectar proyectos de infraestructura con financiamiento internacional.",
     "ctx":"Herederos de Berta Cáceres. Líderes bajo amenaza. Conflicto activo en Río Blanco.",
     "links":[("Twitter/X","https://twitter.com/COPINH_Honduras")]},
    {"cat":"mov","name":"Cristosal","flag":"🇸🇻","level":"crit","type":"Organización DDHH — El Salvador",
     "why":"Principal fuente de documentación bajo el régimen de excepción. Sus reportes son la base de informes del BM sobre El Salvador.",
     "ctx":"Documenta +70.000 detenidos sin proceso. Muertes en custodia en el CECOT confirmadas.",
     "links":[("Twitter/X","https://twitter.com/Cristosal"),("cristosal.org","https://cristosal.org")]},
    {"cat":"mov","name":"CIDH","flag":"🌎","level":"alto","type":"Organismo multilateral — Regional",
     "why":"Sus medidas cautelares condicionan directamente la relación de los gobiernos con el BM. Una MC puede bloquear un desembolso.",
     "ctx":"Medidas cautelares activas en NI, SV y HN. Resoluciones jurídicamente vinculantes.",
     "links":[("Twitter/X","https://twitter.com/CIDH"),("oas.org/cidh","https://oas.org/es/cidh")]},
    {"cat":"mov","name":"Frente Anti-Minero","flag":"🇵🇦","level":"alto","type":"Movimiento ciudadano — Panamá",
     "why":"Forzó la cancelación del contrato de Cobre Panamá en 2023. Puede reactivarse ante cualquier renegociación.",
     "ctx":"Movimiento multiclasista. Arbitraje CIADI USD 20 mil millones activo.",
     "links":[]},
    {"cat":"med","name":"El Faro","flag":"🇸🇻","level":"crit","type":"Periodismo investigativo — El Salvador (exilio)",
     "why":"Principal fuente de información sobre el régimen Bukele. Referencia obligatoria para evaluaciones de riesgo político en SV.",
     "ctx":"Opera desde Costa Rica. Espionaje Pegasus confirmado. Periodistas con órdenes de captura.",
     "links":[("Twitter/X","https://twitter.com/elfaro_net"),("elfaro.net","https://elfaro.net")]},
    {"cat":"med","name":"Confidencial Nicaragua","flag":"🇳🇮","level":"crit","type":"Medio — Nicaragua (exilio en CR)",
     "why":"Única fuente confiable de información sobre Nicaragua. Toda la prensa independiente fue clausurada.",
     "ctx":"Directora condenada en ausencia. Opera desde Costa Rica desde 2021.",
     "links":[("Twitter/X","https://twitter.com/confidencial_ni"),("confidencial.digital","https://confidencial.digital")]},
    {"cat":"med","name":"Plaza Pública","flag":"🇬🇹","level":"med","type":"Periodismo investigativo — Guatemala",
     "why":"Referente del periodismo de datos en Guatemala. Insumo para evaluaciones de riesgo.",
     "ctx":"Financiado por la Universidad Rafael Landívar. Cobertura de conflictos sociales y corrupción.",
     "links":[("Twitter/X","https://twitter.com/PlazaPublicaGT"),("plazapublica.com.gt","https://plazapublica.com.gt")]},
    {"cat":"pol","name":"Gobierno Arévalo","flag":"🇬🇹","level":"alto","type":"Gobierno — Guatemala",
     "why":"Interlocutor principal del BM en Guatemala. Su estabilidad determina el ambiente para proyectos de desarrollo.",
     "ctx":"Bajo asedio del MP. El intento de golpe blando de 2023 fue frenado por presión del BM, BID y UE.",
     "links":[("Twitter/X","https://twitter.com/BArevalodeLeon")]},
    {"cat":"pol","name":"Gobierno Bukele","flag":"🇸🇻","level":"crit","type":"Gobierno — El Salvador",
     "why":"El gobierno más impredecible en DDHH. La condicionalidad del BM está en tensión permanente con sus políticas.",
     "ctx":"Reelecto con 85%. Régimen de excepción indefinido. Control total del Estado.",
     "links":[("Twitter/X","https://twitter.com/nayibbukele")]},
    {"cat":"pol","name":"Gobierno Ortega-Murillo","flag":"🇳🇮","level":"crit","type":"Gobierno — Nicaragua",
     "why":"Régimen más cerrado de CA. BM tiene actividad mínima. Monitorear para detectar cambios.",
     "ctx":"En el poder desde 2007. 300+ ONGs clausuradas. Exilio de 700.000+ personas.",
     "links":[]},
    {"cat":"seg","name":"MS-13 / Pandillas","flag":"🌎","level":"crit","type":"Crimen organizado — Regional",
     "why":"Reconfigurada en HN y GT. Riesgo de extorsión a contratistas en zonas de proyectos de infraestructura.",
     "ctx":"Huyeron de SV tras el régimen de excepción. Nuevas alianzas en HN y GT.",
     "links":[]},
    {"cat":"seg","name":"First Quantum / Cobre Panamá","flag":"🇵🇦","level":"alto","type":"Empresa minera — Panamá",
     "why":"Arbitraje USD 20 mil millones puede desestabilizar finanzas públicas de Panamá y afectar programas del BM.",
     "ctx":"Demanda ante CIADI activa. Frente Anti-Minero en alerta. Gobierno bajo presión.",
     "links":[("firstquantum.com","https://www.first-quantum.com")]},
]
 
def actor_html(a):
    color = {"crit":"#dc2626","alto":"#d97706","med":"#2563eb","low":"#16a34a"}.get(a["level"],"#6b7280")
    badge_cls = "nb " + a["level"]
    ctx_cls = "actor-ctx " + ("red" if a["level"]=="crit" else "amber" if a["level"]=="alto" else "")
    links_html = ""
    if a.get("links"):
        links_html = '<div class="actor-links">' + "".join(
            f'<a href="{u}" target="_blank" rel="noopener" class="actor-link">↗ {l}</a>'
            for l, u in a["links"]
        ) + '</div>'
    return f'''<div class="actor-card" style="border-top:3px solid {color}" data-cat="{a["cat"]}">
  <div class="actor-head">
    <div><div class="actor-name">{a["flag"]} {a["name"]}</div><div class="actor-type">{a["type"]}</div></div>
    <span class="{badge_cls}">{a["level"].upper()}</span>
  </div>
  <div class="actor-why-label">Por qué importa para el BM</div>
  <div class="actor-why">{a["why"]}</div>
  <div class="{ctx_cls}">{a["ctx"]}</div>
  {links_html}
</div>'''
 
actors_html = "".join(actor_html(a) for a in ACTORS)
 
# ─── GENERATE HTML ────────────────────────────────────────────────────────────
print("🎨 Generando HTML...")
 
HTML = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Monitor Centroamérica — Banco Mundial</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --sb:#111827;--sb2:#1f2937;
  --bg:#f3f4f6;--white:#fff;
  --g100:#f3f4f6;--g200:#e5e7eb;--g300:#d1d5db;--g400:#9ca3af;--g500:#6b7280;--g700:#374151;--g800:#1f2937;--g900:#111827;
  --red:#dc2626;--rbg:#fef2f2;--rborder:#fecaca;
  --amber:#d97706;--abg:#fffbeb;--aborder:#fde68a;
  --blue:#2563eb;--bbg:#eff6ff;--bborder:#bfdbfe;
  --green:#16a34a;--gbg:#f0fdf4;--gborder:#bbf7d0;
  --font:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --mono:'JetBrains Mono','Courier New',monospace;
}}
body{{font-family:var(--font);background:var(--bg);color:var(--g800);font-size:14px;display:flex;height:100vh;overflow:hidden}}
 
/* SIDEBAR */
.sb{{width:210px;flex-shrink:0;background:var(--sb);display:flex;flex-direction:column;height:100vh;overflow-y:auto}}
.sb::-webkit-scrollbar{{width:3px}}.sb::-webkit-scrollbar-thumb{{background:#374151}}
.sb-top{{padding:18px 16px 14px;border-bottom:1px solid #1f2937}}
.sb-brand{{display:flex;align-items:center;gap:9px;margin-bottom:10px}}
.sb-logo{{width:30px;height:30px;background:#1d4ed8;border-radius:7px;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.sb-logo svg{{width:14px;height:14px;fill:white}}
.sb-title{{font-size:13px;font-weight:700;color:white}}
.sb-sub{{font-size:10px;color:#6b7280;margin-top:1px}}
.sb-alive{{display:flex;align-items:center;gap:7px;background:#064e3b;border:1px solid #065f46;border-radius:6px;padding:5px 9px}}
.alive-dot{{width:6px;height:6px;border-radius:50%;background:#34d399;animation:pulse 2s infinite;flex-shrink:0}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.sb-alive-txt{{font-size:10px;color:#34d399;font-family:var(--mono)}}
.sb-sec{{font-size:9px;font-weight:700;color:#4b5563;padding:12px 16px 4px;letter-spacing:.1em;text-transform:uppercase}}
.nav-item{{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;font-size:12px;color:#9ca3af;cursor:pointer;border-left:2px solid transparent;transition:all .1s;user-select:none}}
.nav-item:hover{{background:#1f2937;color:#e5e7eb}}
.nav-item.active{{color:white;border-left-color:#3b82f6;background:#1e3a5f;font-weight:600}}
.nav-left{{display:flex;align-items:center;gap:8px}}
.nav-icon{{font-size:14px}}
.nb{{font-size:9px;padding:2px 6px;border-radius:8px;font-weight:700;font-family:var(--mono);white-space:nowrap}}
.sb .nb{{font-size:9px}}
.sb .nb.crit{{background:#7f1d1d;color:#fca5a5}}
.sb .nb.alto{{background:#78350f;color:#fcd34d}}
.sb .nb.low{{background:#064e3b;color:#6ee7b7}}
.sb .nb.med{{background:#1e3a5f;color:#93c5fd}}
.sb-footer{{margin-top:auto;padding:12px 16px;border-top:1px solid #1f2937}}
.sb-footer p{{font-size:10px;color:#4b5563;line-height:1.7;font-family:var(--mono)}}
.sb-footer b{{color:#6b7280}}
.sb-ts{{font-size:10px;color:#34d399;font-family:var(--mono);margin-top:6px}}
 
/* MAIN */
.main{{flex:1;display:flex;flex-direction:column;overflow:hidden}}
.topbar{{background:white;border-bottom:1px solid var(--g200);padding:10px 20px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;gap:12px}}
.tb-left h2{{font-size:17px;font-weight:700;color:var(--g900)}}
.tb-left p{{font-size:11px;color:var(--g400);margin-top:1px;font-family:var(--mono)}}
.tb-right{{display:flex;align-items:center;gap:8px}}
.date-chip{{font-size:11px;color:var(--g400);font-family:var(--mono)}}
.timer-chip{{display:flex;align-items:center;gap:6px;background:var(--g100);border:1px solid var(--g200);border-radius:20px;padding:5px 11px;font-size:11px;color:var(--g500);font-family:var(--mono)}}
.tbar{{width:60px;height:3px;background:var(--g200);border-radius:2px;overflow:hidden}}
.tfill{{height:100%;background:#3b82f6;border-radius:2px;transition:width 1s linear}}
 
/* PAGES */
.page{{display:none;flex:1;overflow-y:auto}}
.page.active{{display:block}}
.pi{{padding:20px 22px;max-width:1380px;margin:0 auto}}
.ph{{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:16px}}
.ph h2{{font-size:20px;font-weight:700;color:var(--g900)}}
.ph p{{font-size:11px;color:var(--g400);margin-top:2px;font-family:var(--mono)}}
.ph a{{font-size:12px;color:var(--blue);cursor:pointer;text-decoration:none}}
 
/* KPI */
.kpi-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px}}
.kpi{{background:white;border:1px solid var(--g200);border-radius:10px;padding:14px 16px}}
.kpi-v{{font-size:28px;font-weight:700;line-height:1;margin-bottom:4px}}
.kpi-v.red{{color:var(--red)}} .kpi-v.amber{{color:var(--amber)}} .kpi-v.green{{color:var(--green)}} .kpi-v.blue{{color:var(--blue)}}
.kpi-l{{font-size:11px;color:var(--g400);font-weight:600;text-transform:uppercase;letter-spacing:.05em}}
.kpi-s{{font-size:11px;color:var(--g500);margin-top:4px}}
 
/* RISK CARDS */
.rc-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px}}
.rc{{background:white;border:1px solid var(--g200);border-radius:10px;padding:14px 16px;cursor:pointer;transition:all .15s;text-decoration:none;display:block}}
.rc:hover{{box-shadow:0 4px 14px rgba(0,0,0,.1);transform:translateY(-1px)}}
.rc-level{{font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;display:inline-flex;align-items:center;gap:4px;margin-bottom:8px;font-family:var(--mono)}}
.rc-level.crit{{background:var(--rbg);color:var(--red);border:1px solid var(--rborder)}}
.rc-level.alto{{background:var(--abg);color:var(--amber);border:1px solid var(--aborder)}}
.rc-level.med{{background:var(--bbg);color:var(--blue);border:1px solid var(--bborder)}}
.rc h3{{font-size:13px;font-weight:700;color:var(--g800);margin-bottom:6px}}
.rc p{{font-size:12px;color:var(--g500);line-height:1.5}}
 
/* NEWS CARDS */
.nb.crit{{background:var(--rbg);color:var(--red);border:1px solid var(--rborder)}}
.nb.alto{{background:var(--abg);color:var(--amber);border:1px solid var(--aborder)}}
.nb.med{{background:var(--bbg);color:var(--blue);border:1px solid var(--bborder)}}
.nb.low{{background:var(--gbg);color:var(--green);border:1px solid var(--gborder)}}
.nb.cat{{background:var(--g100);color:var(--g500);border:1px solid var(--g200)}}
.nb.new{{background:#fef08a;color:#713f12;border:1px solid #fde047}}
.nc{{background:white;border:1px solid var(--g200);border-left:4px solid transparent;border-radius:10px;padding:16px 18px;margin-bottom:10px;display:block;text-decoration:none;color:inherit;transition:all .15s;position:relative}}
.nc:hover{{box-shadow:0 4px 16px rgba(0,0,0,.09)}}
.nc:hover h3{{color:var(--blue)}}
.nc.crit{{border-left-color:var(--red)}}
.nc.alto{{border-left-color:var(--amber)}}
.nc.med{{border-left-color:var(--blue)}}
.nc.low{{border-left-color:var(--green)}}
.card-new{{position:absolute;top:12px;right:12px}}
.nc-top{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}}
.nc h3{{font-size:14px;font-weight:600;color:var(--g900);line-height:1.4;margin-bottom:8px;transition:color .15s}}
.nc p{{font-size:13px;color:var(--g500);line-height:1.6;margin-bottom:10px}}
.nc-foot{{display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
.nc-loc{{font-size:11px;color:var(--g400)}}
.nc-date{{font-size:11px;color:var(--g400);font-family:var(--mono)}}
.nc-src{{font-size:11px;font-weight:600;color:var(--blue)}}
 
/* SOURCES */
.sources{{margin-top:14px;padding-top:12px;border-top:1px solid var(--g100)}}
.src-label{{font-size:10px;font-weight:700;color:var(--g400);text-transform:uppercase;letter-spacing:.07em;margin-bottom:7px;font-family:var(--mono)}}
.src-link{{display:flex;align-items:center;gap:7px;padding:6px 10px;background:var(--g100);border:1px solid var(--g200);border-radius:6px;margin-bottom:5px;text-decoration:none;color:var(--blue);font-size:12px;transition:all .12s}}
.src-link:hover{{background:var(--bbg);border-color:var(--bborder)}}
 
/* FILTER BAR */
.fbar{{display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap}}
.fb{{padding:5px 14px;border-radius:20px;font-size:12px;font-weight:500;cursor:pointer;border:1px solid var(--g300);background:white;color:var(--g600);transition:all .12s}}
.fb:hover{{border-color:#93c5fd;color:var(--blue)}}
.fb.on{{background:var(--blue);color:white;border-color:var(--blue)}}
 
/* AI BOX */
.ai-box{{background:white;border:1px solid var(--g200);border-radius:10px;margin-bottom:14px;overflow:hidden}}
.ai-top{{padding:11px 18px;background:var(--g100);border-bottom:1px solid var(--g200);display:flex;align-items:center;justify-content:space-between}}
.ai-chip{{font-size:10px;background:var(--blue);color:white;padding:2px 8px;border-radius:4px;font-family:var(--mono);font-weight:700;letter-spacing:.04em}}
.ai-ts{{font-size:10px;color:var(--g300);font-family:var(--mono)}}
.ai-body{{padding:18px 20px;font-size:13px;color:var(--g700);line-height:1.8}}
 
/* LAYOUT */
.two-col{{display:grid;grid-template-columns:1.4fr 1fr;gap:14px}}
.three-col{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
@media(max-width:1000px){{.two-col,.three-col,.kpi-row,.rc-row{{grid-template-columns:1fr 1fr}}}}
 
/* RISK MATRIX */
.rmc{{background:white;border:1px solid var(--g200);border-radius:10px;overflow:hidden;margin-bottom:12px}}
.rmc-head{{padding:12px 16px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--g100)}}
.rmc-title{{font-size:13px;font-weight:700;color:var(--g800);display:flex;align-items:center;gap:6px}}
.rmc-body{{padding:12px 16px}}
.rmc-body p{{font-size:13px;color:var(--g600);line-height:1.7;margin-bottom:6px}}
.rmc-country{{font-size:11px;color:var(--g400);font-family:var(--mono)}}
 
/* COUNTRIES */
.country-section{{margin-bottom:28px}}
.country-hero{{display:flex;align-items:center;gap:16px;background:white;border:1px solid var(--g200);border-radius:10px;padding:18px 20px;margin-bottom:14px}}
.ch-flag{{font-size:48px;line-height:1}}
.ch-name{{font-size:22px;font-weight:700;color:var(--g900);margin-bottom:4px}}
.ch-risk{{font-size:13px;color:var(--g500)}}
.ctx-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.ctx-box{{background:white;border:1px solid var(--g200);border-radius:10px;padding:16px 18px}}
.ctx-full{{grid-column:1/-1}}
.ctx-box h4{{font-size:13px;font-weight:700;color:var(--g900);margin-bottom:8px;display:flex;align-items:center;gap:6px}}
.ctx-box p{{font-size:13px;color:var(--g600);line-height:1.8}}
 
/* DATES */
.di{{background:white;border:1px solid var(--g200);border-left:4px solid transparent;border-radius:10px;padding:14px 16px;display:flex;gap:14px;margin-bottom:8px}}
.di.crit{{border-left-color:var(--red)}}
.di.alto{{border-left-color:var(--amber)}}
.di.med{{border-left-color:var(--blue)}}
.di-date{{text-align:center;width:44px;flex-shrink:0}}
.di-day{{font-size:22px;font-weight:700;color:var(--g900);line-height:1}}
.di-mon{{font-size:10px;color:var(--g400);text-transform:uppercase;font-family:var(--mono)}}
.di-body{{flex:1}}
.di-title{{font-size:13px;font-weight:600;color:var(--g900);margin-bottom:3px}}
.di-desc{{font-size:12px;color:var(--g500);line-height:1.5;margin-bottom:5px}}
.di-meta{{display:flex;gap:6px;flex-wrap:wrap}}
 
/* ACTORS */
.actor-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}}
.actor-card{{background:white;border:1px solid var(--g200);border-radius:10px;padding:16px;transition:all .15s}}
.actor-card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.08)}}
.actor-head{{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:10px}}
.actor-name{{font-size:14px;font-weight:700;color:var(--g900);margin-bottom:2px}}
.actor-type{{font-size:11px;color:var(--g400);font-family:var(--mono)}}
.actor-why-label{{font-size:10px;font-weight:700;color:var(--g400);text-transform:uppercase;letter-spacing:.07em;margin-bottom:4px}}
.actor-why{{font-size:12px;color:var(--g600);line-height:1.6;margin-bottom:8px}}
.actor-ctx{{font-size:12px;color:var(--g600);line-height:1.5;padding:8px 10px;border-radius:6px;border-left:3px solid var(--g300);background:var(--g100);margin-bottom:8px}}
.actor-ctx.red{{border-left-color:var(--red);background:var(--rbg)}}
.actor-ctx.amber{{border-left-color:var(--amber);background:var(--abg)}}
.actor-links{{display:flex;gap:6px;flex-wrap:wrap}}
.actor-link{{font-size:11px;padding:3px 10px;border-radius:4px;background:var(--bbg);color:#1d4ed8;border:1px solid var(--bborder);text-decoration:none;font-family:var(--mono);transition:background .1s}}
.actor-link:hover{{background:var(--bborder)}}
 
/* CONFIG */
.cfg-card{{background:white;border:1px solid var(--g200);border-radius:10px;padding:20px;margin-bottom:14px}}
.cfg-card h3{{font-size:15px;font-weight:700;margin-bottom:6px}}
.cfg-card p,.cfg-card li{{font-size:13px;color:var(--g500);line-height:1.7}}
.cfg-card ul{{padding-left:20px;margin-top:8px}}
.query-box{{background:white;border:1px solid var(--g200);border-radius:10px;padding:14px 18px;margin-bottom:14px}}
.ql{{font-size:10px;font-weight:700;color:var(--g400);text-transform:uppercase;letter-spacing:.07em;margin-bottom:8px;font-family:var(--mono)}}
.qrow{{display:flex;gap:8px}}
.qi{{flex:1;background:var(--g100);border:1px solid var(--g200);border-radius:7px;padding:8px 14px;color:var(--g900);font-size:13px;font-family:var(--font);outline:none}}
.qi:focus{{border-color:#93c5fd;background:white}}
.qi::placeholder{{color:var(--g400)}}
.qbtn{{padding:8px 16px;border-radius:7px;background:var(--blue);color:white;border:none;font-size:12px;font-weight:600;cursor:pointer;font-family:var(--font)}}
.qbtn:hover{{background:#1d4ed8}}
.qresult{{margin-top:10px}}
 
::-webkit-scrollbar{{width:5px;height:5px}}
::-webkit-scrollbar-track{{background:transparent}}
::-webkit-scrollbar-thumb{{background:var(--g300);border-radius:3px}}
</style>
</head>
<body>
 
<!-- SIDEBAR -->
<nav class="sb">
  <div class="sb-top">
    <div class="sb-brand">
      <div class="sb-logo"><svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="7" stroke="white" stroke-width="1.8" fill="none"/><circle cx="10" cy="10" r="3" fill="white"/></svg></div>
      <div><div class="sb-title">MONITOR CA</div><div class="sb-sub">Banco Mundial</div></div>
    </div>
    <div class="sb-alive"><div class="alive-dot"></div><span class="sb-alive-txt">SISTEMA ATIVO</span></div>
  </div>
 
  <div class="sb-sec">Monitoramento</div>
  <div class="nav-item active" onclick="goPage('dashboard',this)"><div class="nav-left"><span class="nav-icon">◈</span>Dashboard</div></div>
  <div class="nav-item" onclick="goPage('risk',this)"><div class="nav-left"><span class="nav-icon">⚡</span>Análise de Risco</div></div>
  <div class="nav-item" onclick="goPage('alerts',this)"><div class="nav-left"><span class="nav-icon">🔔</span>Alertas</div><span class="nb crit">{alert_count}</span></div>
  <div class="nav-item" onclick="goPage('news',this)"><div class="nav-left"><span class="nav-icon">📰</span>Notícias</div></div>
  <div class="nav-item" onclick="goPage('actors',this)"><div class="nav-left"><span class="nav-icon">👥</span>Atores</div></div>
  <div class="nav-item" onclick="goPage('dates',this)"><div class="nav-left"><span class="nav-icon">📅</span>Datas Críticas</div></div>
  <div class="nav-item" onclick="goPage('countries',this)"><div class="nav-left"><span class="nav-icon">🌎</span>Por País</div></div>
 
  <div class="sb-sec">Países</div>
  <div class="nav-item" onclick="goPage('countries',this);scrollCountry('Guatemala')"><div class="nav-left">🇬🇹 Guatemala</div><span class="nb alto">Alto</span></div>
  <div class="nav-item" onclick="goPage('countries',this);scrollCountry('El-Salvador')"><div class="nav-left">🇸🇻 El Salvador</div><span class="nb crit">Crítico</span></div>
  <div class="nav-item" onclick="goPage('countries',this);scrollCountry('Honduras')"><div class="nav-left">🇭🇳 Honduras</div><span class="nb alto">Alto</span></div>
  <div class="nav-item" onclick="goPage('countries',this);scrollCountry('Nicaragua')"><div class="nav-left">🇳🇮 Nicaragua</div><span class="nb crit">Crítico</span></div>
  <div class="nav-item" onclick="goPage('countries',this);scrollCountry('Costa-Rica')"><div class="nav-left">🇨🇷 Costa Rica</div><span class="nb low">Bajo</span></div>
  <div class="nav-item" onclick="goPage('countries',this);scrollCountry('Panama')"><div class="nav-left">🇵🇦 Panamá</div><span class="nb med">Medio</span></div>
 
  <div class="sb-sec">Sistema</div>
  <div class="nav-item" onclick="goPage('config',this)"><div class="nav-left"><span class="nav-icon">⚙</span>Configuração</div></div>
 
  <div class="sb-footer">
    <p>Motor: <b>Gemini AI</b><br>Intervalo: <b>2x/día (auto)</b><br>Países: <b>6</b><br>Fuente: <b>Google Search</b></p>
    <div class="sb-ts">Actualizado: {DATE_LABEL}</div>
  </div>
</nav>
 
<!-- MAIN -->
<div class="main">
<div class="topbar">
  <div class="tb-left">
    <h2 id="page-title">Dashboard</h2>
    <p id="page-sub">Monitor de seguridad e inteligencia operacional · Centroamérica</p>
  </div>
  <div class="tb-right">
    <span class="date-chip" id="datelbl">{DATE_LABEL}</span>
    <div class="timer-chip"><div class="alive-dot"></div>Próx. actualización <b id="cd">15:00</b><div class="tbar"><div class="tfill" id="tf" style="width:100%"></div></div></div>
  </div>
</div>
 
<!-- DASHBOARD -->
<div class="page active" id="page-dashboard"><div class="pi">
  <div class="kpi-row">
    <div class="kpi"><div class="kpi-v red">2</div><div class="kpi-l">Países críticos</div><div class="kpi-s">NI + SV</div></div>
    <div class="kpi"><div class="kpi-v amber">2</div><div class="kpi-l">Vigilancia alta</div><div class="kpi-s">GT + HN</div></div>
    <div class="kpi"><div class="kpi-v red">{alert_count}</div><div class="kpi-l">Alertas activas</div><div class="kpi-s">Últimos 7 días</div></div>
    <div class="kpi"><div class="kpi-v blue">6</div><div class="kpi-l">Países cubiertos</div><div class="kpi-s">Cobertura total</div></div>
    <div class="kpi"><div class="kpi-v green">✓</div><div class="kpi-l">Gemini AI</div><div class="kpi-s">Activo · gratis</div></div>
  </div>
 
  <div class="rc-row">
    <div class="rc" onclick="goPage('risk',document.querySelectorAll('.nav-item')[1])">
      <div class="rc-level alto">ALTO · Operacional</div><h3>Infraestructura y operaciones</h3><p>{rc["OPERACIONAL"]}</p>
    </div>
    <div class="rc" onclick="goPage('risk',document.querySelectorAll('.nav-item')[1])">
      <div class="rc-level alto">ALTO · Político</div><h3>Riesgo político regional</h3><p>{rc["POLÍTICO"]}</p>
    </div>
    <div class="rc" onclick="goPage('risk',document.querySelectorAll('.nav-item')[1])">
      <div class="rc-level alto">ALTO · Climático</div><h3>Alertas climáticas</h3><p>{rc["CLIMÁTICO"]}</p>
    </div>
    <div class="rc" onclick="goPage('risk',document.querySelectorAll('.nav-item')[1])">
      <div class="rc-level crit">CRÍTICO · Social</div><h3>Movimientos sociales</h3><p>{rc["SOCIAL"]}</p>
    </div>
    <div class="rc" onclick="goPage('risk',document.querySelectorAll('.nav-item')[1])">
      <div class="rc-level alto">ALTO · Seguridad</div><h3>Seguridad y crimen</h3><p>{rc["SEGURIDAD"]}</p>
    </div>
  </div>
 
  <div class="two-col">
    <div>
      <div class="ai-box">
        <div class="ai-top"><div style="display:flex;align-items:center;gap:8px"><span class="ai-chip">GEMINI AI</span><span style="font-size:13px;font-weight:600;color:var(--g700)">Briefing ejecutivo del día</span></div><span class="ai-ts">{DATE_LABEL}</span></div>
        <div class="ai-body">{briefing_text}{briefing_sources}</div>
      </div>
      <div class="ph"><div><div style="font-size:16px;font-weight:700;color:var(--g900)">Alertas recientes</div><div style="font-size:11px;color:var(--g400);font-family:var(--mono)">Últimas 48h · clic para abrir fuente</div></div><a onclick="goPage('alerts',document.querySelectorAll('.nav-item')[2])">Ver todas →</a></div>
      {dash_alerts}
    </div>
    <div>
      <div class="ph"><div><div style="font-size:16px;font-weight:700;color:var(--g900)">Últimas noticias</div><div style="font-size:11px;color:var(--g400);font-family:var(--mono)">Fuentes verificadas · clic para leer</div></div><a onclick="goPage('news',document.querySelectorAll('.nav-item')[3])">Ver todas →</a></div>
      {dash_news}
      <div style="margin-top:16px">
        <div class="ph"><div style="font-size:16px;font-weight:700;color:var(--g900)">Próximas fechas críticas</div><a onclick="goPage('dates',document.querySelectorAll('.nav-item')[5])">Ver todas →</a></div>
        {dash_dates_html}
      </div>
    </div>
  </div>
</div></div>
 
<!-- RISK -->
<div class="page" id="page-risk"><div class="pi">
  <div class="ph"><div><h2>Análisis de riesgo</h2><p>Matriz consolidada por categoría · Últimos 7 días</p></div></div>
  {risk_cards_html}
  {sources_html(r_risk_analysis["sources"])}
</div></div>
 
<!-- ALERTS -->
<div class="page" id="page-alerts"><div class="pi">
  <div class="ph"><div><h2>Alertas activas</h2><p>{alert_count} alertas · Últimos 7 días · clic en cada alerta para ir a la fuente</p></div></div>
  <div class="fbar">
    <button class="fb on" onclick="filterCards('alerts','all',this)">Todos ({alert_count})</button>
    <button class="fb" onclick="filterCards('alerts','Operacional',this)">Operacional</button>
    <button class="fb" onclick="filterCards('alerts','Seguridad',this)">Seguridad</button>
    <button class="fb" onclick="filterCards('alerts','Climático',this)">Climático</button>
    <button class="fb" onclick="filterCards('alerts','Social',this)">Social/Crisis</button>
    <button class="fb" onclick="filterCards('alerts','Político',this)">Político</button>
  </div>
  <div id="alerts-list">{alerts_html}</div>
  {all_sources_alerts}
</div></div>
 
<!-- NEWS -->
<div class="page" id="page-news"><div class="pi">
  <div class="ph"><div><h2>Noticias</h2><p>Monitoreo de noticias relevantes · clic en cada noticia para leer la fuente completa</p></div></div>
  <div class="fbar">
    <button class="fb on" onclick="filterCards('news','all',this)">Todos</button>
    <button class="fb" onclick="filterCards('news','Operacional',this)">Operacional</button>
    <button class="fb" onclick="filterCards('news','Seguridad',this)">Seguridad</button>
    <button class="fb" onclick="filterCards('news','Climático',this)">Climático</button>
    <button class="fb" onclick="filterCards('news','Social',this)">Social</button>
    <button class="fb" onclick="filterCards('news','Político',this)">Político</button>
  </div>
  <div id="news-list">{news_html}</div>
  {all_sources_news}
</div></div>
 
<!-- ACTORS -->
<div class="page" id="page-actors"><div class="pi">
  <div class="ph"><div><h2>Actores clave</h2><p>Quiénes son, por qué importan para el BM y cómo seguirlos · links directos</p></div></div>
  <div class="fbar">
    <button class="fb on" onclick="filterActors('all',this)">Todos</button>
    <button class="fb" onclick="filterActors('mov',this)">Movimientos sociales</button>
    <button class="fb" onclick="filterActors('med',this)">Medios independientes</button>
    <button class="fb" onclick="filterActors('pol',this)">Actores políticos</button>
    <button class="fb" onclick="filterActors('seg',this)">Seguridad / crimen</button>
  </div>
  <div class="actor-grid" id="actors-grid">{actors_html}</div>
</div></div>
 
<!-- DATES -->
<div class="page" id="page-dates"><div class="pi">
  <div class="ph"><div><h2>Fechas críticas 2026</h2><p>Calendario de eventos, movilizaciones y riesgos operacionales</p></div></div>
  {dates_html}
  {sources_html(r_dates["sources"])}
</div></div>
 
<!-- COUNTRIES -->
<div class="page" id="page-countries"><div class="pi">
  <div class="ph"><div><h2>Monitor por país</h2><p>Contexto político, seguridad y geografía operacional</p></div></div>
  {countries_html}
</div></div>
 
<!-- CONFIG -->
<div class="page" id="page-config"><div class="pi">
  <div class="ph"><div><h2>Configuração</h2><p>Cómo funciona el sistema de actualización automática</p></div></div>
  <div class="cfg-card">
    <h3>⚙️ Cómo funciona este panel</h3>
    <p>Este dashboard es generado automáticamente por un script Python que corre en GitHub Actions dos veces al día (7am y 1pm hora de Costa Rica). El script llama a Gemini AI con Google Search para obtener noticias reales y genera este HTML completo con las noticias ya incluidas. Netlify detecta el cambio y publica automáticamente. Sin CORS, sin errores de API desde el navegador.</p>
  </div>
  <div class="cfg-card">
    <h3>🔧 Para actualizar manualmente</h3>
    <p>Ve a tu repositorio en GitHub → pestaña "Actions" → "Actualizar Monitor CA" → "Run workflow". El panel se actualiza en menos de 2 minutos.</p>
  </div>
  <div class="cfg-card">
    <h3>📊 Última actualización</h3>
    <p>Fecha: <b>{DATE_LABEL}</b><br>Modelo: <b>{MODEL}</b><br>Alertas generadas: <b>{alert_count}</b><br>Noticias generadas: <b>{len(news)}</b></p>
  </div>
</div></div>
 
</div><!-- main -->
</div><!-- body -->
 
<script>
const TOTAL=900;let rem=TOTAL;
const PAGE_META={{
  dashboard:{{title:'Dashboard',sub:'Monitor de seguridad e inteligencia operacional · Centroamérica'}},
  risk:{{title:'Análise de Risco',sub:'Matriz consolidada de riesgo por categoría y país'}},
  alerts:{{title:'Alertas activas',sub:'Clic en cada alerta para ir directamente a la fuente'}},
  news:{{title:'Notícias',sub:'Monitoreo de noticias relevantes · clic para leer la fuente completa'}},
  actors:{{title:'Atores clave',sub:'Quiénes son, por qué importan para el BM y cómo seguirlos'}},
  dates:{{title:'Datas Críticas 2026',sub:'Calendario de eventos, movilizaciones y riesgos operacionales'}},
  countries:{{title:'Por País',sub:'Contexto político, seguridad y geografía operacional'}},
  config:{{title:'Configuração',sub:'Cómo funciona el sistema de actualización automática'}},
}};
 
function goPage(id,el){{
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.getElementById('page-'+id)?.classList.add('active');
  document.querySelectorAll('.nav-item').forEach(e=>e.classList.remove('active'));
  if(el)el.classList.add('active');
  const m=PAGE_META[id]||{{}};
  document.getElementById('page-title').textContent=m.title||id;
  document.getElementById('page-sub').textContent=m.sub||'';
}}
 
function scrollCountry(id){{
  setTimeout(()=>{{
    const el=document.getElementById('country-'+id);
    if(el)el.scrollIntoView({{behavior:'smooth',block:'start'}});
  }},100);
}}
 
function filterCards(listId,cat,btn){{
  const container=document.getElementById(listId+'-list');
  if(!container)return;
  document.querySelectorAll('#page-'+listId+' .fbar .fb').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  container.querySelectorAll('.nc').forEach(card=>{{
    if(cat==='all'){{card.style.display='block';return;}}
    const badges=card.querySelectorAll('.nb.cat');
    const match=[...badges].some(b=>b.textContent.toLowerCase().includes(cat.toLowerCase()));
    card.style.display=match?'block':'none';
  }});
}}
 
function filterActors(cat,btn){{
  document.querySelectorAll('#actor-filter .fb,.fbar .fb').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  document.querySelectorAll('.actor-card').forEach(card=>{{
    card.style.display=(cat==='all'||card.dataset.cat===cat)?'block':'none';
  }});
}}
 
function pad(n){{return String(n).padStart(2,'0')}}
function tick(){{
  rem--;
  if(rem<=0)rem=TOTAL;
  document.getElementById('cd').textContent=pad(Math.floor(rem/60))+':'+pad(rem%60);
  document.getElementById('tf').style.width=Math.round((rem/TOTAL)*100)+'%';
}}
setInterval(tick,1000);
</script>
</body>
</html>'''
 
# ─── WRITE FILE ───────────────────────────────────────────────────────────────
with open("index.html", "w", encoding="utf-8") as f:
    f.write(HTML)
 
print(f"✅ index.html generado ({len(HTML):,} caracteres)")
print(f"   Alertas: {len(alerts)} | Noticias: {len(news)} | Fuentes: {len(r_alerts['sources'])+len(r_news['sources'])}")
 

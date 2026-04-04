"""
EXPERTOSEO Dashboard — Streamlit web interface
Accesible desde el navegador en http://localhost:8501 o desde Railway.
"""

import logging
import queue
import sys
import threading
import time
from datetime import datetime, date
from pathlib import Path

import streamlit as st
import yaml

# Asegurar que el directorio del proyecto está en el path
sys.path.insert(0, str(Path(__file__).parent))

from expertoseo.utils import load_env, load_config, load_json, save_json, DATA_DIR

# ─────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────
load_env()

st.set_page_config(
    page_title="EXPERTOSEO",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS personalizado
st.markdown("""
<style>
    .metric-card {
        background: #1e1e2e;
        border-radius: 12px;
        padding: 1.2rem;
        border: 1px solid #313244;
        text-align: center;
    }
    .metric-value { font-size: 2rem; font-weight: 700; color: #cba6f7; }
    .metric-label { font-size: 0.85rem; color: #a6adc8; margin-top: 4px; }
    .score-green  { color: #a6e3a1; font-weight: 700; }
    .score-yellow { color: #f9e2af; font-weight: 700; }
    .score-red    { color: #f38ba8; font-weight: 700; }
    .status-ok    { color: #a6e3a1; }
    .status-draft { color: #f9e2af; }
    .status-error { color: #f38ba8; }
    .log-box {
        background: #11111b;
        border: 1px solid #313244;
        border-radius: 8px;
        padding: 1rem;
        font-family: monospace;
        font-size: 0.8rem;
        color: #cdd6f4;
        max-height: 400px;
        overflow-y: auto;
        white-space: pre-wrap;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Scheduler en background (inicia una sola vez por proceso)
# ─────────────────────────────────────────────
def _start_scheduler():
    try:
        config = load_config()
        from expertoseo.scheduler import BackgroundArticleScheduler
        scheduler = BackgroundArticleScheduler(config)
        scheduler.start()
        st.session_state["bg_scheduler"] = scheduler
        st.session_state["scheduler_started"] = True
    except Exception as e:
        st.session_state["scheduler_error"] = str(e)

if "scheduler_started" not in st.session_state:
    _start_scheduler()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def _score_html(score):
    if score == "-" or score is None:
        return "-"
    score = int(score)
    cls = "score-green" if score >= 70 else ("score-yellow" if score >= 50 else "score-red")
    return f'<span class="{cls}">{score}/100</span>'

def _status_html(status):
    cls = {"success": "status-ok", "publish": "status-ok",
           "draft": "status-draft", "error": "status-error"}.get(status, "")
    label = {"success": "✓ Publicado", "publish": "✓ Publicado",
             "draft": "⏳ Borrador", "error": "✗ Error"}.get(status, status)
    return f'<span class="{cls}">{label}</span>'

def _load_config_safe():
    try:
        return load_config()
    except Exception:
        return {}

def _get_rankings_latest():
    history = load_json("rankings.json")
    if not isinstance(history, dict) or not history:
        return []
    latest = max(history.keys())
    return history[latest]

def _get_prev_rankings():
    history = load_json("rankings.json")
    if not isinstance(history, dict) or len(history) < 2:
        return {}
    dates = sorted(history.keys())
    return {r["keyword"]: r["position"] for r in history[dates[-2]]}


# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🚀 EXPERTOSEO")
    st.markdown("---")
    page = st.radio(
        "Navegación",
        ["🏠 Inicio", "📝 Artículos", "📊 Rankings", "🚀 Publicar", "🔑 Keywords", "💬 Asistente", "⚙️ Configuración"],
        label_visibility="collapsed",
    )
    st.markdown("---")

    # Estado del scheduler
    scheduler = st.session_state.get("bg_scheduler")
    if scheduler and scheduler.scheduler.running:
        next_run = scheduler.get_next_run()
        st.success(f"🟢 Agente activo\n\nPróxima pub: **{next_run or 'pronto'}**")
    else:
        err = st.session_state.get("scheduler_error", "")
        st.warning(f"🟡 Scheduler inactivo\n{err[:80] if err else ''}")


# ─────────────────────────────────────────────
# PÁGINA: INICIO
# ─────────────────────────────────────────────
if page == "🏠 Inicio":
    st.title("🏠 Panel Principal")

    published = load_json("published.json")
    if not isinstance(published, list):
        published = []

    kw_queue = load_json("keywords.json")
    if not isinstance(kw_queue, list):
        kw_queue = []

    rankings = _get_rankings_latest()
    top10 = [r for r in rankings if r.get("position", 99) <= 10]
    scores = [p["seo_score"] for p in published if isinstance(p.get("seo_score"), (int, float))]
    avg_score = round(sum(scores) / len(scores)) if scores else 0

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{len(published)}</div><div class="metric-label">Artículos publicados</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{avg_score}</div><div class="metric-label">Score SEO medio</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{len(kw_queue)}</div><div class="metric-label">Keywords en cola</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{len(top10)}</div><div class="metric-label">Keywords TOP 10</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📋 Últimas publicaciones")

    if published:
        rows_html = ""
        for p in published[:8]:
            link = p.get("link", "#")
            title = p.get("title") or p.get("keyword") or "Sin título"
            title_cell = f'<a href="{link}" target="_blank">{title[:55]}</a>' if link != "#" else title[:55]
            rows_html += f"""<tr>
                <td>{title_cell}</td>
                <td>{p.get("keyword", "-")[:30]}</td>
                <td>{_score_html(p.get("seo_score", "-"))}</td>
                <td>{_status_html(p.get("status", "-"))}</td>
                <td>{(p.get("date") or p.get("timestamp", ""))[:10]}</td>
            </tr>"""
        st.markdown(f"""
        <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="color:#a6adc8;font-size:0.85rem;border-bottom:1px solid #313244;">
            <th style="text-align:left;padding:8px">Título</th>
            <th style="text-align:left;padding:8px">Keyword</th>
            <th style="text-align:center;padding:8px">Score</th>
            <th style="text-align:center;padding:8px">Estado</th>
            <th style="text-align:left;padding:8px">Fecha</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
        </table>""", unsafe_allow_html=True)
    else:
        st.info("Aún no hay artículos publicados. Ve a **Publicar** para lanzar el primer artículo.")

    st.markdown("---")
    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button("🚀 Publicar artículo ahora", type="primary", use_container_width=True):
            st.switch_page = True
            st.session_state["auto_launch"] = True
            st.rerun()


# ─────────────────────────────────────────────
# PÁGINA: ARTÍCULOS
# ─────────────────────────────────────────────
elif page == "📝 Artículos":
    st.title("📝 Historial de Artículos")

    published = load_json("published.json")
    if not isinstance(published, list) or not published:
        st.info("No hay artículos publicados todavía.")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        estados = ["Todos"] + list({p.get("status", "?") for p in published})
        filtro_estado = st.selectbox("Filtrar por estado", estados)
    with col2:
        filtro_buscar = st.text_input("Buscar por título o keyword", placeholder="ej: SEO, marketing...")

    filtered = published
    if filtro_estado != "Todos":
        filtered = [p for p in filtered if p.get("status") == filtro_estado]
    if filtro_buscar:
        q = filtro_buscar.lower()
        filtered = [p for p in filtered if q in (p.get("title") or "").lower() or q in (p.get("keyword") or "").lower()]

    st.markdown(f"**{len(filtered)} artículos** encontrados")

    if filtered:
        rows_html = ""
        for p in filtered:
            link = p.get("link", "#")
            title = p.get("title") or p.get("keyword") or "Sin título"
            title_cell = f'<a href="{link}" target="_blank">{title[:60]}</a>' if link and link != "#" else title[:60]
            err = f'<span style="color:#f38ba8;font-size:0.75rem">{str(p.get("error",""))[:40]}</span>' if p.get("error") else ""
            rows_html += f"""<tr style="border-bottom:1px solid #313244;">
                <td style="padding:8px">{title_cell}{err}</td>
                <td style="padding:8px">{p.get("keyword", "-")[:35]}</td>
                <td style="padding:8px;text-align:center">{_score_html(p.get("seo_score", "-"))}</td>
                <td style="padding:8px;text-align:center">{_status_html(p.get("status", "-"))}</td>
                <td style="padding:8px">{(p.get("date") or p.get("timestamp", ""))[:10]}</td>
            </tr>"""
        st.markdown(f"""
        <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="color:#a6adc8;font-size:0.8rem;border-bottom:2px solid #313244;">
            <th style="text-align:left;padding:8px">Título / Error</th>
            <th style="text-align:left;padding:8px">Keyword</th>
            <th style="text-align:center;padding:8px">Score SEO</th>
            <th style="text-align:center;padding:8px">Estado</th>
            <th style="text-align:left;padding:8px">Fecha</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
        </table>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# PÁGINA: RANKINGS
# ─────────────────────────────────────────────
elif page == "📊 Rankings":
    st.title("📊 Posiciones en Google")

    col_refresh, _ = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 Actualizar desde GSC"):
            with st.spinner("Consultando Google Search Console..."):
                try:
                    config = _load_config_safe()
                    from expertoseo.ranking_tracker import RankingTracker
                    tracker = RankingTracker(config)
                    tracker.fetch_rankings()
                    st.success("Rankings actualizados correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    rankings = _get_rankings_latest()
    prev = _get_prev_rankings()

    if not rankings:
        st.info("No hay datos de rankings todavía.\n\nConfigura Google Search Console en `.env` y pulsa **Actualizar desde GSC**.")
        st.stop()

    history = load_json("rankings.json")
    if isinstance(history, dict) and history:
        last_date = max(history.keys())
        st.caption(f"Última actualización: {last_date} — {len(rankings)} keywords rastreadas")

    top3   = [r for r in rankings if r.get("position", 99) <= 3]
    top10  = [r for r in rankings if 3 < r.get("position", 99) <= 10]
    top20  = [r for r in rankings if 10 < r.get("position", 99) <= 20]

    def render_ranking_table(rows, title, color):
        if not rows:
            return
        st.markdown(f"#### {title}")
        html_rows = ""
        for r in rows:
            kw = r["keyword"]
            pos = r["position"]
            prev_pos = prev.get(kw)
            if prev_pos:
                delta = prev_pos - pos
                arrow = f'<span style="color:#a6e3a1">▲{delta:.0f}</span>' if delta > 0 else (f'<span style="color:#f38ba8">▼{abs(delta):.0f}</span>' if delta < 0 else "—")
            else:
                arrow = "—"
            html_rows += f"""<tr style="border-bottom:1px solid #313244;">
                <td style="padding:8px">{kw}</td>
                <td style="padding:8px;text-align:center;font-weight:700;color:{color}">{pos}</td>
                <td style="padding:8px;text-align:center">{arrow}</td>
                <td style="padding:8px;text-align:right">{r.get("clicks", "-")}</td>
                <td style="padding:8px;text-align:right">{r.get("impressions", "-")}</td>
                <td style="padding:8px;text-align:right">{r.get("ctr", "-")}%</td>
            </tr>"""
        st.markdown(f"""
        <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="color:#a6adc8;font-size:0.8rem;border-bottom:2px solid #313244;">
            <th style="text-align:left;padding:8px">Keyword</th>
            <th style="text-align:center;padding:8px">Posición</th>
            <th style="text-align:center;padding:8px">Cambio</th>
            <th style="text-align:right;padding:8px">Clicks</th>
            <th style="text-align:right;padding:8px">Impresiones</th>
            <th style="text-align:right;padding:8px">CTR</th>
        </tr></thead>
        <tbody>{html_rows}</tbody>
        </table>""", unsafe_allow_html=True)
        st.markdown("")

    if top3:
        render_ranking_table(top3, "🥇 TOP 1-3", "#a6e3a1")
    if top10:
        render_ranking_table(top10, "🎯 TOP 4-10", "#f9e2af")
    if top20:
        render_ranking_table(top20[:20], "📈 TOP 11-20", "#89dceb")
    if not top3 and not top10 and not top20:
        st.warning("No hay keywords en TOP 20 todavía. Sigue publicando contenido.")


# ─────────────────────────────────────────────
# PÁGINA: PUBLICAR
# ─────────────────────────────────────────────
elif page == "🚀 Publicar":
    st.title("🚀 Lanzar Agente de Publicación")
    st.markdown("El agente genera el artículo, crea la portada, optimiza el SEO y lo publica en WordPress — todo automáticamente.")

    config = _load_config_safe()
    sites = config.get("sites", [])
    site_options = {s.get("name", s.get("slug")): s.get("slug") for s in sites}

    col1, col2 = st.columns(2)
    with col1:
        keyword_input = st.text_input(
            "Keyword objetivo (opcional)",
            placeholder="Dejar vacío para usar la siguiente de la cola",
            help="Si lo dejas vacío, se usará la próxima keyword de la cola o de GSC/Trends."
        )
    with col2:
        site_name = st.selectbox("Sitio", list(site_options.keys()) if site_options else ["Sin sitios configurados"])
        site_slug = site_options.get(site_name)

    col3, col4 = st.columns(2)
    with col3:
        as_draft = st.toggle("Publicar como borrador", value=False, help="Guarda como borrador en WordPress para revisar antes de publicar.")
    with col4:
        st.markdown("")

    st.markdown("---")

    # Auto-launch desde la página de inicio
    auto_launch = st.session_state.pop("auto_launch", False)

    launch = st.button("⚡ LANZAR AGENTE", type="primary", use_container_width=True) or auto_launch

    if launch:
        if not sites:
            st.error("No hay sitios configurados. Ve a **Configuración** y añade tu sitio WordPress.")
            st.stop()

        log_q: queue.Queue = queue.Queue()
        result_container: list = [None]

        # Handler de logs que envía mensajes a la queue
        class _UILogHandler(logging.Handler):
            def emit(self, record):
                log_q.put(self.format(record))

        ui_handler = _UILogHandler()
        ui_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s — %(message)s", datefmt="%H:%M:%S"))
        expertoseo_logger = logging.getLogger("expertoseo")
        expertoseo_logger.addHandler(ui_handler)

        def _pipeline_thread():
            try:
                cfg = load_config()
                if as_draft:
                    cfg.setdefault("schedule", {})["publish_status"] = "draft"
                if keyword_input.strip():
                    # Poner la keyword al frente de la cola
                    from expertoseo.utils import load_json as _lj, save_json as _sj
                    q = _lj("keywords.json")
                    if not isinstance(q, list):
                        q = []
                    q.insert(0, keyword_input.strip())
                    _sj("keywords.json", q)
                from expertoseo.scheduler import run_full_pipeline
                result_container[0] = run_full_pipeline(cfg, site_slug)
            except Exception as e:
                result_container[0] = {"status": "error", "error": str(e)}

        thread = threading.Thread(target=_pipeline_thread, daemon=True)
        thread.start()

        # Progreso y logs en vivo
        steps = [
            "🔍 Seleccionando keyword...",
            "✍️  Generando artículo con Claude...",
            "🔎 Optimizando SEO...",
            "🎨 Creando imagen de portada...",
            "📤 Publicando en WordPress...",
            "⚙️  Configurando RankMath...",
        ]
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_container = st.empty()
        logs: list[str] = []
        step_idx = 0
        step_keywords = ["keyword", "generando", "optimiz", "imagen", "publicando", "rankmath"]

        while thread.is_alive():
            try:
                while True:
                    msg = log_q.get_nowait()
                    logs.append(msg)
                    # Detectar paso actual por keywords en el log
                    msg_lower = msg.lower()
                    for i, kw in enumerate(step_keywords):
                        if kw in msg_lower and i >= step_idx:
                            step_idx = i
                            progress_bar.progress(min((step_idx + 1) / len(steps), 1.0))
                            status_text.markdown(f"**{steps[step_idx]}**")
                            break
            except queue.Empty:
                pass
            log_container.markdown(
                f'<div class="log-box">{chr(10).join(logs[-30:])}</div>',
                unsafe_allow_html=True,
            )
            time.sleep(0.3)

        # Vaciar queue final
        try:
            while True:
                logs.append(log_q.get_nowait())
        except queue.Empty:
            pass

        expertoseo_logger.removeHandler(ui_handler)
        thread.join()

        progress_bar.progress(1.0)
        log_container.markdown(
            f'<div class="log-box">{chr(10).join(logs)}</div>',
            unsafe_allow_html=True,
        )

        result = result_container[0]
        if result and result.get("status") == "success":
            status_text.empty()
            st.success(f"✅ ¡Artículo publicado correctamente!")
            c1, c2, c3 = st.columns(3)
            c1.metric("Score SEO", f"{result.get('seo_score', '-')}/100")
            c2.metric("Estado", result.get("status", "-"))
            c3.metric("Keyword", result.get("keyword", "-"))
            if result.get("link"):
                st.markdown(f"🔗 **[Ver artículo publicado]({result['link']})**")
        else:
            status_text.empty()
            err = result.get("error", "Error desconocido") if result else "Sin respuesta"
            st.error(f"❌ Error durante la publicación: {err}")


# ─────────────────────────────────────────────
# PÁGINA: KEYWORDS
# ─────────────────────────────────────────────
elif page == "🔑 Keywords":
    st.title("🔑 Gestión de Keywords")

    kw_queue = load_json("keywords.json")
    if not isinstance(kw_queue, list):
        kw_queue = []

    col_add, col_queue = st.columns([1, 1])

    with col_add:
        st.subheader("➕ Añadir keywords")
        new_kws = st.text_area(
            "Una keyword por línea",
            height=200,
            placeholder="posicionamiento web\nestrategia SEO 2025\nlink building para blogs",
        )
        if st.button("Añadir a la cola", type="primary"):
            lines = [l.strip() for l in new_kws.splitlines() if l.strip()]
            if lines:
                existing = set(kw_queue)
                added = [k for k in lines if k not in existing]
                kw_queue.extend(added)
                save_json("keywords.json", kw_queue)
                st.success(f"✅ {len(added)} keywords añadidas.")
                st.rerun()
            else:
                st.warning("Escribe al menos una keyword.")

    with col_queue:
        st.subheader(f"📋 Cola actual ({len(kw_queue)} keywords)")
        if kw_queue:
            for i, kw in enumerate(kw_queue):
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"**{i+1}.** {kw}")
                if c2.button("✕", key=f"del_{i}", help="Eliminar"):
                    kw_queue.pop(i)
                    save_json("keywords.json", kw_queue)
                    st.rerun()
        else:
            st.info("La cola está vacía. Añade keywords arriba o activa GSC para detección automática.")

    st.markdown("---")
    st.subheader("🔍 Descubrir oportunidades")
    col_gsc, col_trends = st.columns(2)

    with col_gsc:
        if st.button("📈 Oportunidades GSC (posición 4-20)", use_container_width=True):
            with st.spinner("Consultando Google Search Console..."):
                try:
                    config = _load_config_safe()
                    from expertoseo.keyword_research import KeywordResearch
                    kw_res = KeywordResearch(config)
                    opps = kw_res.get_gsc_opportunities()
                    if opps:
                        st.session_state["gsc_opps"] = opps
                    else:
                        st.warning("No se encontraron oportunidades. Verifica la config de GSC.")
                except Exception as e:
                    st.error(f"Error: {e}")

    with col_trends:
        if st.button("🔥 Tendencias Google Trends", use_container_width=True):
            with st.spinner("Consultando Google Trends..."):
                try:
                    config = _load_config_safe()
                    from expertoseo.keyword_research import KeywordResearch
                    kw_res = KeywordResearch(config)
                    trends = kw_res.get_trending_keywords()
                    if trends:
                        st.session_state["trends_kws"] = trends
                    else:
                        st.warning("No se encontraron tendencias.")
                except Exception as e:
                    st.error(f"Error: {e}")

    # Mostrar resultados GSC
    if "gsc_opps" in st.session_state:
        st.markdown("**Oportunidades de Google Search Console:**")
        opps = st.session_state["gsc_opps"]
        for opp in opps[:15]:
            c1, c2, c3, c4 = st.columns([4, 1, 1, 1])
            c1.markdown(f"**{opp['keyword']}**")
            c2.markdown(f"Pos: **{opp['position']}**")
            c3.markdown(f"{opp['impressions']} imp.")
            if c4.button("+ Cola", key=f"add_gsc_{opp['keyword'][:20]}"):
                if opp["keyword"] not in kw_queue:
                    kw_queue.append(opp["keyword"])
                    save_json("keywords.json", kw_queue)
                    st.success(f"'{opp['keyword']}' añadida.")
                    st.rerun()

    # Mostrar resultados Trends
    if "trends_kws" in st.session_state:
        st.markdown("**Keywords en tendencia:**")
        for kw in st.session_state["trends_kws"][:10]:
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"🔥 {kw}")
            if c2.button("+ Cola", key=f"add_tr_{kw[:20]}"):
                if kw not in kw_queue:
                    kw_queue.append(kw)
                    save_json("keywords.json", kw_queue)
                    st.success(f"'{kw}' añadida.")
                    st.rerun()


# ─────────────────────────────────────────────
# PÁGINA: ASISTENTE SEO
# ─────────────────────────────────────────────
elif page == "💬 Asistente":
    st.title("💬 Asistente SEO — Claude")
    st.markdown("Habla con tu experto SEO personal. Pregúntale sobre posicionamiento, análisis de tu web, estrategias, o pídele que genere contenido.")

    # Inicializar asistente en session_state (mantiene historial multi-turn)
    if "seo_assistant" not in st.session_state:
        try:
            config = _load_config_safe()
            from expertoseo.assistant import SEOAssistant
            st.session_state["seo_assistant"] = SEOAssistant(config)
            st.session_state["chat_history"] = []
        except Exception as e:
            st.error(f"Error iniciando el asistente: {e}")
            st.stop()

    # Mostrar historial de chat
    for msg in st.session_state.get("chat_history", []):
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

    # Input del usuario
    if prompt := st.chat_input("Pregunta algo sobre tu SEO..."):
        # Mostrar mensaje del usuario
        with st.chat_message("user", avatar="🧑"):
            st.markdown(prompt)
        st.session_state["chat_history"].append({"role": "user", "content": prompt})

        # Respuesta del asistente
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Analizando..."):
                try:
                    assistant = st.session_state["seo_assistant"]
                    response = assistant.chat(prompt)
                    st.markdown(response)
                    st.session_state["chat_history"].append({"role": "assistant", "content": response})
                except Exception as e:
                    err_msg = f"❌ Error: {e}"
                    st.error(err_msg)
                    st.session_state["chat_history"].append({"role": "assistant", "content": err_msg})

    # Botón para limpiar historial
    if st.session_state.get("chat_history"):
        if st.button("🗑️ Limpiar conversación", help="Borra el historial del chat"):
            st.session_state["chat_history"] = []
            config = _load_config_safe()
            from expertoseo.assistant import SEOAssistant
            st.session_state["seo_assistant"] = SEOAssistant(config)
            st.rerun()


# ─────────────────────────────────────────────
# PÁGINA: CONFIGURACIÓN
# ─────────────────────────────────────────────
elif page == "⚙️ Configuración":
    st.title("⚙️ Configuración")

    config_path = Path(__file__).parent / "config.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
    except Exception as e:
        st.error(f"Error leyendo config.yaml: {e}")
        st.stop()

    tab1, tab2 = st.tabs(["⚡ Ajustes rápidos", "📄 YAML completo"])

    with tab1:
        st.subheader("Programación automática")
        schedule = config_data.get("schedule", {})
        col1, col2, col3 = st.columns(3)
        with col1:
            new_interval = st.number_input("Publicar cada N días", min_value=1, max_value=30, value=schedule.get("interval_days", 2))
        with col2:
            new_time = st.text_input("Hora de publicación (HH:MM)", value=schedule.get("publish_time", "09:00"))
        with col3:
            new_status = st.selectbox("Estado al publicar", ["publish", "draft"], index=0 if schedule.get("publish_status", "publish") == "publish" else 1)

        st.subheader("Calidad SEO")
        seo = config_data.get("seo", {})
        col4, col5, col6 = st.columns(3)
        with col4:
            new_min_words = st.number_input("Palabras mínimas", min_value=500, max_value=5000, value=seo.get("min_words", 1500), step=100)
        with col5:
            new_max_words = st.number_input("Palabras máximas", min_value=1000, max_value=10000, value=seo.get("max_words", 2500), step=100)
        with col6:
            new_min_score = st.slider("Score SEO mínimo para publicar", min_value=0, max_value=100, value=seo.get("min_score", 70))

        st.subheader("Nicho y keywords")
        kw_cfg = config_data.get("keywords", {})
        new_niche = st.text_input("Nicho principal", value=kw_cfg.get("niche", ""))
        new_manual_kws = st.text_area(
            "Keywords manuales (una por línea)",
            value="\n".join(kw_cfg.get("manual", [])),
            height=120,
        )

        if st.button("💾 Guardar cambios", type="primary"):
            config_data.setdefault("schedule", {}).update({
                "interval_days": new_interval,
                "publish_time": new_time,
                "publish_status": new_status,
            })
            config_data.setdefault("seo", {}).update({
                "min_words": new_min_words,
                "max_words": new_max_words,
                "min_score": new_min_score,
            })
            config_data.setdefault("keywords", {}).update({
                "niche": new_niche,
                "manual": [l.strip() for l in new_manual_kws.splitlines() if l.strip()],
            })
            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False)
                st.success("✅ Configuración guardada. Los cambios se aplicarán en la próxima publicación.")
            except Exception as e:
                st.error(f"Error guardando: {e}")

    with tab2:
        st.subheader("config.yaml completo (solo lectura)")
        try:
            raw = config_path.read_text(encoding="utf-8")
            st.code(raw, language="yaml")
        except Exception as e:
            st.error(str(e))

        st.markdown("---")
        st.subheader("Variables de entorno (.env)")
        env_path = Path(__file__).parent / ".env"
        env_example_path = Path(__file__).parent / ".env.example"
        if env_path.exists():
            # Mostrar .env ocultando valores
            lines = env_path.read_text().splitlines()
            masked = []
            for line in lines:
                if "=" in line and not line.strip().startswith("#"):
                    key, _, val = line.partition("=")
                    masked_val = val[:4] + "****" if val else "(vacío)"
                    masked.append(f"{key}={masked_val}")
                else:
                    masked.append(line)
            st.code("\n".join(masked), language="bash")
        else:
            st.warning(".env no encontrado. Crea uno basándote en `.env.example`.")
            if env_example_path.exists():
                st.code(env_example_path.read_text(), language="bash")

        st.info("💡 En Railway, las variables de entorno se configuran en el panel de **Variables** — no necesitas el archivo .env.")

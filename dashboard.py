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
        ["🏠 Inicio", "📝 Artículos", "📊 Rankings", "🚀 Publicar", "🔑 Keywords", "💬 Asistente", "✅ Checklist SEO", "⚙️ Configuración"],
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

    # ── Publicar ahora (inline, sin salir de Inicio) ─────────────────────
    st.markdown("---")
    st.subheader("⚡ Publicar artículo ahora")

    col_kw, col_draft, col_btn = st.columns([3, 1, 1])
    with col_kw:
        quick_kw = st.text_input(
            "Keyword (opcional — vacío = usar la siguiente de la cola)",
            key="home_kw",
            placeholder="ej: mejores auriculares bluetooth 2025",
            label_visibility="collapsed",
        )
    with col_draft:
        quick_draft = st.toggle("Borrador", key="home_draft", help="Publicar como borrador para revisarlo antes")
    with col_btn:
        launch_now = st.button("🚀 PUBLICAR AHORA", type="primary", use_container_width=True)

    if launch_now:
        log_q: queue.Queue = queue.Queue()
        result_box: list = [None]

        class _QuickLogHandler(logging.Handler):
            def emit(self, record):
                log_q.put(self.format(record))

        h = _QuickLogHandler()
        h.setFormatter(logging.Formatter("%(asctime)s — %(message)s", datefmt="%H:%M:%S"))
        logging.getLogger("expertoseo").addHandler(h)

        def _quick_pipeline():
            try:
                cfg = load_config()
                if quick_draft:
                    cfg.setdefault("schedule", {})["publish_status"] = "draft"
                if quick_kw.strip():
                    q = load_json("keywords.json")
                    if not isinstance(q, list):
                        q = []
                    q.insert(0, quick_kw.strip())
                    save_json("keywords.json", q)
                from expertoseo.scheduler import run_full_pipeline
                result_box[0] = run_full_pipeline(cfg)
            except Exception as e:
                result_box[0] = {"status": "error", "error": str(e)}

        t = threading.Thread(target=_quick_pipeline, daemon=True)
        t.start()

        log_area = st.empty()
        prog = st.progress(0, text="Iniciando...")
        logs = []
        step_map = {"keyword": 15, "generando": 35, "optimiz": 55, "imagen": 70, "publicando": 85, "rankmath": 95}

        while t.is_alive():
            try:
                while True:
                    msg = log_q.get_nowait()
                    logs.append(msg)
                    for kw, pct in step_map.items():
                        if kw in msg.lower():
                            prog.progress(pct / 100, text=msg[:80])
                            break
            except queue.Empty:
                pass
            log_area.markdown(f'<div class="log-box">{chr(10).join(logs[-15:])}</div>', unsafe_allow_html=True)
            time.sleep(0.3)

        t.join()
        logging.getLogger("expertoseo").removeHandler(h)
        prog.progress(1.0, text="Completado")

        r = result_box[0]
        if r and r.get("status") == "success":
            st.success(f"✅ Publicado correctamente — Score SEO: {r.get('seo_score', '-')}/100")
            if r.get("link"):
                st.markdown(f"🔗 **[Ver artículo en resenaspremium.com]({r['link']})**")
            st.rerun()
        else:
            err = r.get("error", "Error desconocido") if r else "Sin respuesta"
            st.error(f"❌ {err}")


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

    # Mensaje pre-cargado desde el checklist
    if "pending_assistant_msg" in st.session_state:
        pending = st.session_state.pop("pending_assistant_msg")
        with st.chat_message("user", avatar="🧑"):
            st.markdown(pending)
        st.session_state["chat_history"].append({"role": "user", "content": pending})
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Analizando..."):
                try:
                    response = st.session_state["seo_assistant"].chat(pending)
                    st.markdown(response)
                    st.session_state["chat_history"].append({"role": "assistant", "content": response})
                except Exception as e:
                    st.error(str(e))

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


# ─────────────────────────────────────────────
# PÁGINA: CHECKLIST SEO
# ─────────────────────────────────────────────
elif page == "✅ Checklist SEO":
    st.title("✅ Checklist SEO — Guía paso a paso")
    st.markdown("Marca cada tarea cuando la hayas completado. El asistente analizará si está bien hecha y te dará feedback.")

    # ── Definición de todas las tareas SEO ──────────────────────────────
    CHECKLIST_ITEMS = {
        "🔍 Google Search Console": [
            {
                "id": "gsc_verify",
                "title": "Verificar propiedad del sitio en GSC",
                "desc": "Añadir tu web en Google Search Console y verificar la propiedad con el método que prefieras (HTML tag, DNS, etc.)",
                "how": "Ve a search.google.com/search-console → Añadir propiedad → Introduce tu URL → Elige verificación por etiqueta HTML → Copia el código → Pégalo en el <head> de tu web → Verifica.",
                "gsc_step": True,
            },
            {
                "id": "gsc_sitemap",
                "title": "Enviar Sitemap XML a GSC",
                "desc": "Enviar el sitemap.xml de tu WordPress para que Google indexe todas tus páginas más rápido.",
                "how": "En GSC → Sitemaps → Escribe 'sitemap.xml' → Enviar. En WordPress con RankMath el sitemap está en /sitemap_index.xml",
                "gsc_step": True,
            },
            {
                "id": "gsc_coverage",
                "title": "Revisar errores de cobertura/indexación",
                "desc": "Comprobar que no hay páginas con errores 404, excluidas o con problemas de crawl.",
                "how": "En GSC → Indexación → Páginas → Revisa las secciones 'No indexado' y 'Error'. Corrige los errores más frecuentes.",
                "gsc_step": True,
            },
            {
                "id": "gsc_connected",
                "title": "Conectar GSC con EXPERTOSEO (API)",
                "desc": "Vincular la cuenta de servicio de Google con EXPERTOSEO para que el agente vea tus posiciones automáticamente.",
                "how": "Ver guía detallada abajo ↓",
                "gsc_step": True,
            },
        ],
        "⚙️ SEO Técnico": [
            {
                "id": "tech_ssl",
                "title": "SSL activado (HTTPS)",
                "desc": "Tu web debe cargar en https:// — Google penaliza webs sin SSL.",
                "how": "Comprueba que resenaspremium.com carga con HTTPS. Si no, actívalo en tu hosting (suele ser gratis con Let's Encrypt).",
            },
            {
                "id": "tech_speed",
                "title": "Velocidad de carga > 80 en PageSpeed",
                "desc": "Google usa Core Web Vitals como factor de ranking. Objetivo: > 80 en móvil.",
                "how": "Ve a pagespeed.web.dev → Analiza tu URL → Aplica las recomendaciones (comprimir imágenes, activar caché, lazy load).",
            },
            {
                "id": "tech_mobile",
                "title": "Web adaptada a móvil (responsive)",
                "desc": "Google usa mobile-first indexing. Si tu web no se ve bien en móvil, pierde ranking.",
                "how": "Abre tu web desde el móvil o usa la herramienta de prueba en search.google.com/test/mobile-friendly",
            },
            {
                "id": "tech_robots",
                "title": "robots.txt configurado correctamente",
                "desc": "El archivo robots.txt no debe bloquear a Googlebot de páginas importantes.",
                "how": "Visita resenaspremium.com/robots.txt — asegúrate de que no bloquea /wp-content/ ni páginas importantes.",
            },
            {
                "id": "tech_canonical",
                "title": "URLs canónicas configuradas",
                "desc": "Evitar contenido duplicado con URLs canónicas. RankMath lo hace automáticamente si está bien configurado.",
                "how": "En RankMath → General Settings → Links → verifica que 'Canonical URL' está activado.",
            },
        ],
        "📝 SEO On-Page": [
            {
                "id": "onpage_rankmath",
                "title": "RankMath configurado y activo",
                "desc": "RankMath debe estar instalado, activado y con la licencia conectada (o versión gratuita).",
                "how": "En wp-admin → RankMath → Dashboard. Completa el asistente de configuración inicial si no lo has hecho.",
            },
            {
                "id": "onpage_schema",
                "title": "Schema markup activo en RankMath",
                "desc": "Activar schema de tipo Article/Review para que Google muestre rich snippets en los resultados.",
                "how": "En RankMath → Títulos y Metadatos → Posts → Schema Type → Selecciona 'Article' o 'Review'.",
            },
            {
                "id": "onpage_og",
                "title": "Open Graph (redes sociales) configurado",
                "desc": "Las etiquetas OG hacen que tus artículos se vean bien cuando alguien los comparte en redes.",
                "how": "En RankMath → General Settings → Social → activa Open Graph y Twitter Cards.",
            },
            {
                "id": "onpage_breadcrumbs",
                "title": "Breadcrumbs activados",
                "desc": "Los breadcrumbs mejoran la navegación y aparecen en los resultados de Google.",
                "how": "En RankMath → General Settings → Breadcrumbs → activa y añade el shortcode a tu tema.",
            },
        ],
        "🔗 SEO Off-Page y Contenido": [
            {
                "id": "content_strategy",
                "title": "Estrategia de contenidos definida",
                "desc": "Tener un calendario editorial con las keywords objetivo para los próximos 30 días.",
                "how": "Usa la página de Keywords de EXPERTOSEO para añadir tus keywords objetivo a la cola. El agente las trabajará automáticamente.",
            },
            {
                "id": "content_internal",
                "title": "Links internos entre artículos",
                "desc": "Cada artículo nuevo debe enlazar a 2-3 artículos relacionados del mismo sitio.",
                "how": "EXPERTOSEO sugiere links internos automáticamente al generar cada artículo. Revísalos en la sección de Artículos.",
            },
            {
                "id": "offpage_gmb",
                "title": "Google My Business configurado (si aplica)",
                "desc": "Si tu negocio es local, GMB es imprescindible para aparecer en búsquedas locales.",
                "how": "Ve a business.google.com → Crea o reclama tu ficha → Completa toda la información.",
            },
        ],
    }

    # ── Cargar estado del checklist ──────────────────────────────────────
    checklist_data = load_json("seo_checklist.json")
    if not isinstance(checklist_data, dict):
        checklist_data = {}

    def _save_checklist():
        save_json("seo_checklist.json", checklist_data)

    # ── Progreso global ──────────────────────────────────────────────────
    all_ids = [item["id"] for cat_items in CHECKLIST_ITEMS.values() for item in cat_items]
    done_ids = [i for i in all_ids if checklist_data.get(i, {}).get("done")]
    progress = len(done_ids) / len(all_ids) if all_ids else 0

    col_prog, col_score = st.columns([3, 1])
    with col_prog:
        st.progress(progress, text=f"Progreso: {len(done_ids)}/{len(all_ids)} tareas completadas")
    with col_score:
        pct = int(progress * 100)
        color = "#a6e3a1" if pct >= 70 else ("#f9e2af" if pct >= 40 else "#f38ba8")
        st.markdown(f'<div style="text-align:center;font-size:2rem;font-weight:700;color:{color}">{pct}%</div>', unsafe_allow_html=True)

    st.markdown("---")

    # ── Render de cada categoría ─────────────────────────────────────────
    for category, items in CHECKLIST_ITEMS.items():
        cat_done = sum(1 for item in items if checklist_data.get(item["id"], {}).get("done"))
        with st.expander(f"{category} — {cat_done}/{len(items)} completadas", expanded=(cat_done < len(items))):
            for item in items:
                item_id = item["id"]
                item_state = checklist_data.get(item_id, {"done": False, "feedback": None, "note": ""})
                is_done = item_state.get("done", False)
                feedback = item_state.get("feedback")
                user_note = item_state.get("note", "")

                col_check, col_info = st.columns([1, 12])

                with col_check:
                    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
                    new_done = st.checkbox("", value=is_done, key=f"chk_{item_id}", label_visibility="collapsed")

                with col_info:
                    # Título con indicador de estado
                    status_icon = "✅" if is_done else "⬜"
                    if is_done and feedback:
                        ok = feedback.get("ok", True)
                        status_icon = "✅" if ok else "⚠️"
                    st.markdown(f"**{status_icon} {item['title']}**")
                    st.caption(item["desc"])

                    # Mostrar feedback de Claude si existe
                    if feedback:
                        if feedback.get("ok"):
                            st.success(f"✅ {feedback.get('message', 'Correcto')}")
                        else:
                            st.warning(f"⚠️ {feedback.get('message', 'Necesita revisión')}")
                            if feedback.get("suggestion"):
                                st.info(f"💡 {feedback['suggestion']}")

                    # Expansión para ver cómo hacerlo y añadir nota
                    with st.expander("📋 Cómo hacerlo / Añadir nota"):
                        st.markdown(f"**Instrucciones:** {item['how']}")
                        new_note = st.text_area(
                            "Tu nota (describe qué hiciste o qué problema encontraste)",
                            value=user_note,
                            key=f"note_{item_id}",
                            height=80,
                        )

                        col_save, col_eval = st.columns(2)
                        with col_save:
                            if st.button("💾 Guardar nota", key=f"save_{item_id}"):
                                checklist_data.setdefault(item_id, {})["note"] = new_note
                                _save_checklist()
                                st.success("Nota guardada.")

                        with col_eval:
                            eval_label = "🤖 Evaluar con Claude" if not feedback else "🔄 Re-evaluar"
                            if st.button(eval_label, key=f"eval_{item_id}"):
                                with st.spinner("Analizando con Claude..."):
                                    try:
                                        from expertoseo.utils import require_env
                                        import anthropic
                                        client = anthropic.Anthropic(api_key=require_env("ANTHROPIC_API_KEY"))

                                        eval_prompt = f"""Eres un experto SEO. El usuario ha marcado como completada la siguiente tarea SEO:

Tarea: {item['title']}
Descripción: {item['desc']}
Instrucciones correctas: {item['how']}
Nota del usuario: {new_note or user_note or '(sin nota)'}
Sitio web: https://resenaspremium.com

Evalúa si la tarea está correctamente completada basándote en su nota.
Si no hay nota, asume que puede estar hecha pero pide confirmación.

Responde SOLO en formato JSON:
{{"ok": true/false, "message": "mensaje corto de 1 frase", "suggestion": "sugerencia concreta si hay algo que mejorar o null"}}"""

                                        resp = client.messages.create(
                                            model="claude-sonnet-4-6",
                                            max_tokens=300,
                                            messages=[{"role": "user", "content": eval_prompt}],
                                        )
                                        import json, re
                                        text = resp.content[0].text
                                        json_match = re.search(r'\{.*\}', text, re.DOTALL)
                                        if json_match:
                                            fb = json.loads(json_match.group(0))
                                        else:
                                            fb = {"ok": True, "message": text[:100], "suggestion": None}

                                        checklist_data.setdefault(item_id, {})["feedback"] = fb
                                        checklist_data[item_id]["done"] = new_done
                                        _save_checklist()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error: {e}")

                # Guardar cambio de checkbox
                if new_done != is_done:
                    checklist_data.setdefault(item_id, {})["done"] = new_done
                    if not new_done:
                        checklist_data[item_id]["feedback"] = None
                    _save_checklist()
                    st.rerun()

                st.markdown("---")

    # ── Guía detallada: Conectar GSC con EXPERTOSEO ──────────────────────
    st.markdown("## 📖 Guía: Conectar Google Search Console con EXPERTOSEO")

    with st.expander("🔑 Paso a paso completo para conectar la API de GSC", expanded=False):
        st.markdown("""
### ¿Por qué conectar GSC?
Con GSC conectado, EXPERTOSEO puede ver automáticamente qué keywords están en posición 4-20 (oportunidades rápidas para llegar al TOP) y actualizar tus rankings cada día.

---

### Paso 1 — Crear proyecto en Google Cloud Console
1. Ve a [console.cloud.google.com](https://console.cloud.google.com)
2. Crea un proyecto nuevo → llámalo `EXPERTOSEO`
3. En el menú lateral: **APIs y Servicios** → **Biblioteca**
4. Busca **"Google Search Console API"** → Actívala

---

### Paso 2 — Crear cuenta de servicio
1. En **APIs y Servicios** → **Credenciales** → **Crear credenciales** → **Cuenta de servicio**
2. Nombre: `expertoseo-gsc`
3. Clic en **Crear y continuar** → **Listo**
4. Haz clic en la cuenta de servicio recién creada
5. Pestaña **Claves** → **Añadir clave** → **Crear clave nueva** → **JSON**
6. Se descarga un archivo `.json` → guárdalo bien

---

### Paso 3 — Dar acceso a tu Search Console
1. Ve a [search.google.com/search-console](https://search.google.com/search-console)
2. Selecciona tu propiedad `resenaspremium.com`
3. **Configuración** (⚙️) → **Usuarios y permisos** → **Añadir usuario**
4. Email: el email de la cuenta de servicio (termina en `@...iam.gserviceaccount.com`)
5. Permiso: **Restringido** (solo lectura)

---

### Paso 4 — Subir credenciales a Railway
1. Abre el archivo `.json` descargado con un editor de texto
2. Copia TODO el contenido
3. En Railway → tu servicio → **Variables** → añade:
   ```
   GOOGLE_SERVICE_ACCOUNT_JSON = {"type":"service_account","project_id":"...todo el JSON..."}
   ```
   *(pega el JSON completo como valor de la variable)*

---

### Paso 5 — Verificar conexión
Una vez configurado, ve a la página de **Rankings** en este dashboard y pulsa **"Actualizar desde GSC"**. Si funciona, verás tus keywords y posiciones.

---
**¿Problemas?** Escribe al asistente SEO y describe el error que ves.
        """)

    # Botón para ir al asistente con contexto
    if st.button("💬 Pedir ayuda al asistente SEO con este checklist"):
        done_tasks = [item["title"] for cat in CHECKLIST_ITEMS.values() for item in cat if checklist_data.get(item["id"], {}).get("done")]
        pending_tasks = [item["title"] for cat in CHECKLIST_ITEMS.values() for item in cat if not checklist_data.get(item["id"], {}).get("done")]
        st.session_state["chat_history"] = st.session_state.get("chat_history", [])
        msg = f"Analiza mi progreso SEO. Tareas completadas: {done_tasks}. Tareas pendientes: {pending_tasks}. ¿Qué debo priorizar ahora mismo para resenaspremium.com?"
        st.session_state.setdefault("pending_assistant_msg", msg)
        st.info("Ve a la página '💬 Asistente' — el contexto de tu checklist ya está preparado.")

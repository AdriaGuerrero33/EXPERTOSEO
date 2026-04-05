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

try:
    from expertoseo.utils import load_env, load_config, load_json, save_json, save_credentials_file, DATA_DIR
    load_env()
    _BOOT_OK = True
    _BOOT_ERR = None
except Exception as _e:
    _BOOT_OK = False
    _BOOT_ERR = str(_e)

st.set_page_config(
    page_title="EXPERTOSEO",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Apple-quality CSS (macOS Dark Mode) ──────────────────────────────────────
st.markdown("""
<style>
/* System font stack */
*, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif !important;
}

/* Page background */
[data-testid="stAppViewContainer"] > .main { background: #161618 !important; }
[data-testid="stSidebar"] {
    background: #1c1c1e !important;
    border-right: 1px solid rgba(255,255,255,0.08) !important;
}
.block-container { padding-top: 1.8rem !important; max-width: 1080px !important; }

/* KPI cards */
.kpi-card {
    background: #1c1c1e;
    border-radius: 16px;
    padding: 1.4rem 1.2rem;
    border: 1px solid rgba(255,255,255,0.08);
    text-align: center;
    height: 100%;
}
.kpi-val  { font-size: 2.2rem; font-weight: 700; color: #fff; line-height: 1.1; }
.kpi-lbl  { font-size: 0.72rem; color: rgba(255,255,255,0.4); margin-top: 6px;
             letter-spacing: 0.06em; text-transform: uppercase; }

/* Deprecated aliases kept for compat */
.metric-card  { background:#1c1c1e; border-radius:16px; padding:1.4rem 1.2rem;
                border:1px solid rgba(255,255,255,0.08); text-align:center; }
.metric-value { font-size:2.2rem; font-weight:700; color:#fff; }
.metric-label { font-size:0.72rem; color:rgba(255,255,255,0.4); margin-top:6px;
                letter-spacing:0.06em; text-transform:uppercase; }

/* Score / status colors */
.score-green, .s-green   { color: #30d158; font-weight: 600; }
.score-yellow,.s-yellow  { color: #ff9f0a; font-weight: 600; }
.score-red,   .s-red     { color: #ff453a; font-weight: 600; }
.status-ok    { color: #30d158; }
.status-draft { color: #ff9f0a; }
.status-error { color: #ff453a; }

/* Badges */
.badge-ok    { background:rgba(48,209,88,0.15);  color:#30d158; border-radius:20px;
               padding:2px 10px; font-size:0.78rem; font-weight:600; }
.badge-draft { background:rgba(255,159,10,0.15); color:#ff9f0a; border-radius:20px;
               padding:2px 10px; font-size:0.78rem; font-weight:600; }
.badge-error { background:rgba(255,69,58,0.15);  color:#ff453a; border-radius:20px;
               padding:2px 10px; font-size:0.78rem; font-weight:600; }

/* Credential status */
.cred-ok  { display:inline-block; background:rgba(48,209,88,0.12);  color:#30d158;
             border-radius:8px; padding:4px 12px; font-size:0.82rem; font-weight:600; }
.cred-bad { display:inline-block; background:rgba(255,69,58,0.12);  color:#ff453a;
             border-radius:8px; padding:4px 12px; font-size:0.82rem; font-weight:600; }
.cred-opt { display:inline-block; background:rgba(255,255,255,0.06); color:rgba(255,255,255,0.4);
             border-radius:8px; padding:4px 12px; font-size:0.82rem; font-weight:600; }

/* Tables */
.t-wrap { border-radius:12px; overflow:hidden; border:1px solid rgba(255,255,255,0.08); }
table { width:100%; border-collapse:collapse; }
thead tr { background:rgba(255,255,255,0.04); }
thead th { padding:10px 14px; text-align:left; font-size:0.72rem; color:rgba(255,255,255,0.38);
           font-weight:600; text-transform:uppercase; letter-spacing:0.06em;
           border-bottom:1px solid rgba(255,255,255,0.08); }
tbody tr { border-bottom:1px solid rgba(255,255,255,0.05); }
tbody tr:last-child { border-bottom:none; }
tbody td { padding:10px 14px; font-size:0.88rem; color:rgba(255,255,255,0.82); }
a { color:#0a84ff; text-decoration:none; }
a:hover { text-decoration:underline; }

/* Log box */
.log-box {
    background: #0d0d0f;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    font-family: "SF Mono","Menlo","Monaco","Consolas",monospace !important;
    font-size: 0.78rem;
    color: rgba(255,255,255,0.65);
    max-height: 380px;
    overflow-y: auto;
    white-space: pre-wrap;
    line-height: 1.65;
}

/* Info card */
.info-card {
    background: rgba(10,132,255,0.08);
    border: 1px solid rgba(10,132,255,0.2);
    border-radius: 12px;
    padding: 1rem 1.2rem;
    color: rgba(255,255,255,0.85);
    font-size: 0.88rem;
    line-height: 1.55;
}

/* Hide Streamlit chrome */
#MainMenu, footer { visibility: hidden; }
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

if _BOOT_OK and "scheduler_started" not in st.session_state:
    _start_scheduler()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def _safe_load_config():
    try:
        return load_config() if _BOOT_OK else {}
    except Exception:
        return {}

def _safe_load_json(name, default=None):
    try:
        return load_json(name) if _BOOT_OK else (default or [])
    except Exception:
        return default or []
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
    import os as _os_nav
    _nav_required = ["ANTHROPIC_API_KEY", "EXPERTOSEO_SECRET_TOKEN"]
    _nav_creds_ok = all(_os_nav.environ.get(k) for k in _nav_required)
    _nav_pages = ["🏠 Inicio", "📝 Artículos", "📊 Rankings", "🚀 Publicar",
                  "🔑 Keywords", "💬 Asistente", "⚙️ Configuración"]
    if not _nav_creds_ok:
        _nav_pages.insert(-1, "🗝️ Credenciales")  # solo aparece si faltan credenciales
    else:
        # Botón pequeño de acceso a credenciales en el footer del sidebar
        _nav_pages.append("🗝️ Credenciales")  # siempre disponible, al final

    page = st.radio(
        "Navegación",
        _nav_pages,
        label_visibility="collapsed",
    )

    # Aviso de volumen: si data/credentials.yaml no existe, los datos no persisten
    _creds_yaml = DATA_DIR / "credentials.yaml"
    if not _creds_yaml.exists():
        st.warning("⚠️ Sin persistencia — Ve a Railway → tu servicio → **Volumes** → montar `/app/data` para que los datos no se borren al redesplegar.", icon="⚠️")
    st.markdown("---")

    if not _BOOT_OK:
        st.error(f"⚠️ Error de arranque:\n{_BOOT_ERR}")
    else:
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
    history = load_json("rankings.json")

    if not rankings:
        st.markdown("""
<div class="info-card">
<strong>📊 Aún no hay datos de rankings.</strong><br><br>
Para ver tus posiciones en Google necesitas conectar <strong>Google Search Console</strong>.<br>
Ve a <strong>🗝️ Credenciales</strong> e introduce tu JSON de cuenta de servicio de Google, luego pulsa <em>Actualizar desde GSC</em>.
</div>""", unsafe_allow_html=True)
        st.markdown("")
        # Mostrar artículos publicados como alternativa útil
        published = load_json("published.json")
        if isinstance(published, list) and published:
            st.subheader("📝 Artículos publicados (URLs para posicionar)")
            st.caption("Estos son los artículos que ya están indexados en Google:")
            for p in published[:10]:
                link = p.get("link", "")
                title = p.get("title") or p.get("keyword") or "Sin título"
                kw = p.get("keyword", "")
                score = p.get("seo_score", "-")
                date_str = (p.get("date") or p.get("timestamp", ""))[:10]
                score_cls = "s-green" if isinstance(score, (int,float)) and score >= 70 else "s-yellow" if isinstance(score, (int,float)) and score >= 50 else "s-red"
                link_html = f'<a href="{link}" target="_blank">{title[:60]}</a>' if link else title[:60]
                st.markdown(f'<div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.06)">{link_html} &nbsp;<span class="{score_cls}">{score}/100</span> <span style="color:rgba(255,255,255,0.3);font-size:0.8rem">— {date_str}</span></div>', unsafe_allow_html=True)
        st.stop()

    if isinstance(history, dict) and history:
        last_date = max(history.keys())
        # KPIs de GSC
        total_clicks = sum(r.get("clicks", 0) or 0 for r in rankings)
        total_impressions = sum(r.get("impressions", 0) or 0 for r in rankings)
        avg_pos = sum(r.get("position", 0) for r in rankings) / len(rankings) if rankings else 0
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="kpi-card"><div class="kpi-val">{len(rankings)}</div><div class="kpi-lbl">Keywords rastreadas</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="kpi-card"><div class="kpi-val">{total_clicks:,}</div><div class="kpi-lbl">Clics totales</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="kpi-card"><div class="kpi-val">{total_impressions:,}</div><div class="kpi-lbl">Impresiones</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="kpi-card"><div class="kpi-val">{avg_pos:.1f}</div><div class="kpi-lbl">Posición media</div></div>', unsafe_allow_html=True)
        st.markdown("")
        st.caption(f"Última actualización: {last_date}")

    top3   = [r for r in rankings if r.get("position", 99) <= 3]
    top10  = [r for r in rankings if 3 < r.get("position", 99) <= 10]
    top20  = [r for r in rankings if 10 < r.get("position", 99) <= 20]
    top50  = [r for r in rankings if 20 < r.get("position", 99) <= 50]

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
        render_ranking_table(top3, "🥇 TOP 1-3", "#30d158")
    if top10:
        render_ranking_table(top10, "🎯 TOP 4-10", "#ff9f0a")
    if top20:
        render_ranking_table(top20[:20], "📈 TOP 11-20", "#0a84ff")

    if not top3 and not top10 and not top20:
        st.markdown("""
<div class="info-card">
<strong>📈 Aún no tienes keywords en TOP 20.</strong><br><br>
Es normal al principio — Google tarda semanas en posicionar contenido nuevo.
Mientras tanto, aquí están tus keywords con más impresiones (mayor potencial):
</div>""", unsafe_allow_html=True)
        st.markdown("")

    # Mostrar TOP 21-50 siempre que existan (oportunidades reales de mejora)
    if top50:
        render_ranking_table(top50[:25], "🚀 TOP 21-50 — Oportunidades (optimiza estos artículos)", "#bf5af2")

    # Tabla completa paginada
    if rankings:
        with st.expander(f"📋 Ver todas las keywords ({len(rankings)} en total)"):
            render_ranking_table(
                sorted(rankings, key=lambda r: r.get("position", 999))[:50],
                "", "#ffffff"
            )


# ─────────────────────────────────────────────
# PÁGINA: PUBLICAR
# ─────────────────────────────────────────────
elif page == "🚀 Publicar":
    st.title("🚀 Publicar")

    _pub_tab1, _pub_tab2, _pub_tab3, _pub_tab4 = st.tabs(
        ["📤 Publicar artículo", "📅 Calendario", "⚙️ RankMath SEO", "🔍 SEO Interno"]
    )

    # ─── TAB 1: PUBLICAR ───────────────────────────────────────────────────────
    with _pub_tab1:
        st.markdown("El agente genera el artículo, crea la portada, optimiza el SEO y lo publica en WordPress — todo automáticamente.")

        config = _load_config_safe()
        sites = config.get("sites", [])
        site_options = {s.get("name", s.get("slug")): s.get("slug") for s in sites}

        col1, col2 = st.columns(2)
        with col1:
            keyword_input = st.text_input(
                "Keyword objetivo (opcional)",
                placeholder="💡 Dejar vacío = próxima de la cola automáticamente",
                help="Puedes incluir emojis en la keyword: 🏆 mejor reseña, 🌟 top productos, etc.",
            )
        with col2:
            site_name = st.selectbox("Sitio", list(site_options.keys()) if site_options else ["Sin sitios configurados"])
            site_slug = site_options.get(site_name)

        col3, col4 = st.columns(2)
        with col3:
            as_draft = st.toggle("Publicar como borrador", value=False, help="Guarda como borrador en WordPress para revisar antes de publicar.")
        with col4:
            use_emoji_title = st.toggle("Emojis en título 🎯", value=True, help="El agente incluirá emojis relevantes en el título del artículo")

        # ── Portada personalizada ─────────────────────────────────────────
        st.markdown("**Portada** (opcional — si no subes ninguna, el agente genera una automáticamente)")
        col_img1, col_img2 = st.columns([2, 1])
        with col_img1:
            custom_image = st.file_uploader(
                "Sube tu propia portada",
                type=["jpg", "jpeg", "png", "webp"],
                help="Si subes una imagen, se usará como portada en vez de la generada automáticamente",
                label_visibility="collapsed",
            )
        with col_img2:
            if custom_image:
                st.image(custom_image, caption="Vista previa portada", use_container_width=True)
            else:
                st.caption("Sin imagen → el agente crea una con IA")

        # Guardar imagen personalizada en sesión
        if custom_image:
            import tempfile as _tmp
            _img_tmp = Path(_tmp.gettempdir()) / f"expertoseo_cover_{custom_image.name}"
            _img_tmp.write_bytes(custom_image.read())
            st.session_state["custom_cover_path"] = str(_img_tmp)
        elif "custom_cover_path" in st.session_state and not custom_image:
            st.session_state.pop("custom_cover_path", None)

        st.markdown("---")

        auto_launch = st.session_state.pop("auto_launch", False)
        launch = st.button("⚡ LANZAR AGENTE", type="primary", use_container_width=True) or auto_launch

        if launch:
            if not sites:
                st.error("No hay sitios configurados. Ve a **Configuración** y añade tu sitio WordPress.")
                st.stop()

            log_q: queue.Queue = queue.Queue()
            result_container: list = [None]

            class _UILogHandler(logging.Handler):
                def emit(self, record):
                    log_q.put(self.format(record))

            ui_handler = _UILogHandler()
            ui_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s — %(message)s", datefmt="%H:%M:%S"))
            expertoseo_logger = logging.getLogger("expertoseo")
            expertoseo_logger.addHandler(ui_handler)

            _cover_path = st.session_state.get("custom_cover_path")

            def _pipeline_thread():
                try:
                    cfg = load_config()
                    if as_draft:
                        cfg.setdefault("schedule", {})["publish_status"] = "draft"
                    if use_emoji_title:
                        cfg.setdefault("ai", {})["use_emoji_title"] = True
                    if keyword_input.strip():
                        from expertoseo.utils import load_json as _lj, save_json as _sj
                        q = _lj("keywords.json")
                        if not isinstance(q, list):
                            q = []
                        q.insert(0, keyword_input.strip())
                        _sj("keywords.json", q)
                    from expertoseo.scheduler import run_full_pipeline
                    result_container[0] = run_full_pipeline(
                        cfg, site_slug,
                        custom_image_path=_cover_path,
                    )
                except Exception as e:
                    result_container[0] = {"status": "error", "error": str(e)}

            thread = threading.Thread(target=_pipeline_thread, daemon=True)
            thread.start()

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
                st.success("✅ ¡Artículo publicado correctamente!")
                col_res1, col_res2 = st.columns([2, 1])
                with col_res1:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Score SEO", f"{result.get('seo_score', '-')}/100")
                    c2.metric("Keyword", result.get("keyword", "-")[:20])
                    c3.metric("Estado", "Publicado" if not as_draft else "Borrador")
                    if result.get("link"):
                        st.markdown(f"🔗 **[Ver artículo en WordPress]({result['link']})**")
                with col_res2:
                    _img_path = result.get("image_path") or _cover_path
                    if _img_path and Path(str(_img_path)).exists():
                        st.image(str(_img_path), caption="Portada publicada", use_container_width=True)
            else:
                status_text.empty()
                err = result.get("error", "Error desconocido") if result else "Sin respuesta"
                st.error(f"❌ Error durante la publicación: {err}")

    # ─── TAB 2: CALENDARIO ────────────────────────────────────────────────────
    with _pub_tab2:
        import calendar as _cal
        from datetime import datetime as _dt, date as _date_t, timedelta as _td

        _now = _dt.now()

        # ── Cargar datos ──────────────────────────────────────────────────
        _pub_all = load_json("published.json")
        if not isinstance(_pub_all, list):
            _pub_all = []
        _plan_all = load_json("schedule_plan.json")
        if not isinstance(_plan_all, list):
            _plan_all = []

        # Índice por fecha: publicados y programados
        _pub_by_date: dict = {}
        for _p in _pub_all:
            _d = (_p.get("date") or "")[:10]
            if _d:
                _pub_by_date.setdefault(_d, []).append({"type": "published", **_p})

        _plan_by_date: dict = {}
        for _e in _plan_all:
            _d = (_e.get("date") or "")[:10]
            if _d and _e.get("status") == "pending":
                _plan_by_date.setdefault(_d, []).append(_e)

        # ── Botones de acción ─────────────────────────────────────────────
        _btn_col1, _btn_col2, _btn_col3 = st.columns(3)
        with _btn_col1:
            if st.button("🤖 Auto-programar próximos 30 días", type="primary", use_container_width=True,
                         help="Genera automáticamente 1 artículo cada 2 días durante los próximos 30 días"):
                try:
                    from expertoseo.scheduler import generate_auto_schedule
                    _new_plan = generate_auto_schedule(n_articles=15)
                    _pending = sum(1 for e in _new_plan if e.get("status") == "pending")
                    st.success(f"✅ Plan actualizado: {_pending} artículos programados (1 cada 2 días)")
                    st.rerun()
                except Exception as _ex:
                    st.error(str(_ex))
        with _btn_col2:
            _pending_count = sum(1 for e in _plan_all if e.get("status") == "pending")
            st.markdown(
                f'<div class="kpi-card"><div class="kpi-val">{_pending_count}</div>'
                f'<div class="kpi-lbl">Programados</div></div>',
                unsafe_allow_html=True,
            )
        with _btn_col3:
            _pub_count = sum(1 for e in _plan_all if e.get("status") == "published")
            st.markdown(
                f'<div class="kpi-card"><div class="kpi-val">{len(_pub_all)}</div>'
                f'<div class="kpi-lbl">Publicados</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # ── Selector mes/año ──────────────────────────────────────────────
        _col_m1, _col_m2, _col_m3 = st.columns([1, 1, 3])
        with _col_m1:
            _sel_month = st.selectbox("Mes", list(range(1, 13)), index=_now.month - 1,
                                      format_func=lambda m: _dt(2000, m, 1).strftime("%B"))
        with _col_m2:
            _sel_year = st.selectbox("Año", list(range(_now.year - 1, _now.year + 2)), index=1)

        _month_name = _dt(_sel_year, _sel_month, 1).strftime("%B %Y")
        st.subheader(f"📅 {_month_name}")

        # Leyenda
        st.markdown(
            '<div style="display:flex;gap:16px;margin-bottom:12px;font-size:.78rem">'
            '<span style="color:#30d158">● Publicado</span>'
            '<span style="color:#0a84ff">● Programado</span>'
            '<span style="color:#ff9f0a">● Hoy</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        # ── Cuadrícula del calendario ─────────────────────────────────────
        _weeks = _cal.monthcalendar(_sel_year, _sel_month)
        _day_names = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        _cal_html = ['<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-top:4px">']
        for dn in _day_names:
            _cal_html.append(f'<div style="text-align:center;font-size:.7rem;color:rgba(255,255,255,.4);padding:4px;font-weight:600;letter-spacing:.05em">{dn}</div>')
        _total_month_pubs = 0
        for _week in _weeks:
            for _day in _week:
                if _day == 0:
                    _cal_html.append('<div></div>')
                else:
                    _date_str = f"{_sel_year}-{_sel_month:02d}-{_day:02d}"
                    _pubs_day  = _pub_by_date.get(_date_str, [])
                    _sched_day = _plan_by_date.get(_date_str, [])
                    _is_today  = (_date_str == _now.strftime("%Y-%m-%d"))
                    _total_month_pubs += len(_pubs_day)

                    if _pubs_day:
                        _bg = "rgba(48,209,88,0.18)"; _border = "1.5px solid #30d158"; _color = "#30d158"
                        _kw_hint = (_pubs_day[0].get("keyword") or "")[:12]
                        _badge = f'<div style="font-size:.58rem;margin-top:2px;color:#30d158">{len(_pubs_day)} pub.</div>'
                        if _kw_hint:
                            _badge += f'<div style="font-size:.55rem;color:rgba(255,255,255,.4);overflow:hidden;white-space:nowrap;text-overflow:ellipsis;max-width:100%">{_kw_hint}</div>'
                    elif _sched_day:
                        _bg = "rgba(10,132,255,0.15)"; _border = "1.5px solid #0a84ff"; _color = "#0a84ff"
                        _kw_hint = (_sched_day[0].get("keyword") or "auto")[:12]
                        _badge = f'<div style="font-size:.6rem;margin-top:2px;color:#0a84ff">⏰ prog.</div>'
                        _badge += f'<div style="font-size:.55rem;color:rgba(255,255,255,.4);overflow:hidden;white-space:nowrap;text-overflow:ellipsis;max-width:100%">{_kw_hint}</div>'
                    elif _is_today:
                        _bg = "rgba(255,159,10,0.15)"; _border = "1.5px solid #ff9f0a"; _color = "#ff9f0a"
                        _badge = '<div style="font-size:.6rem;margin-top:2px;color:#ff9f0a">HOY</div>'
                    else:
                        _bg = "rgba(255,255,255,0.03)"; _border = "1px solid rgba(255,255,255,0.07)"; _color = "rgba(255,255,255,.55)"
                        _badge = ""
                    _cal_html.append(
                        f'<div style="background:{_bg};border:{_border};border-radius:10px;padding:7px 3px;'
                        f'text-align:center;min-height:56px;overflow:hidden">'
                        f'<div style="font-size:.88rem;font-weight:700;color:{_color}">{_day}</div>'
                        f'{_badge}</div>'
                    )
        _cal_html.append('</div>')
        st.markdown("".join(_cal_html), unsafe_allow_html=True)

        # ── Añadir publicación manual ─────────────────────────────────────
        st.markdown("---")
        _add_col, _list_col = st.columns([1, 1])
        with _add_col:
            st.subheader("➕ Programar artículo")
            with st.form("add_schedule_form"):
                _new_date = st.date_input("Fecha de publicación", min_value=_date_t.today())
                _new_kw   = st.text_input("Keyword (opcional — vacío = auto)",
                                          placeholder="🏆 mejores reseñas de auriculares")
                _new_hour = st.selectbox("Hora", ["07:00", "08:00", "09:00", "10:00", "11:00", "12:00"], index=2)
                _add_btn  = st.form_submit_button("📅 Añadir al calendario", use_container_width=True)
                if _add_btn:
                    import uuid as _uuid
                    _new_entry = {
                        "id": f"plan_{_uuid.uuid4().hex[:8]}",
                        "date": _new_date.strftime("%Y-%m-%d"),
                        "datetime": f"{_new_date.strftime('%Y-%m-%d')}T{_new_hour}:00",
                        "keyword": _new_kw.strip() or None,
                        "status": "pending",
                        "created_at": _date_t.today().strftime("%Y-%m-%d"),
                    }
                    _plan_all.append(_new_entry)
                    _plan_all.sort(key=lambda e: e.get("date", ""))
                    save_json("schedule_plan.json", _plan_all)
                    st.success(f"✅ Programado para {_new_date.strftime('%d/%m/%Y')} a las {_new_hour}")
                    st.rerun()

        with _list_col:
            st.subheader(f"📋 Plan de {_month_name}")
            _month_plan = [e for e in _plan_all if (e.get("date") or "").startswith(f"{_sel_year}-{_sel_month:02d}")]
            _month_published = [(d, p) for d, ps in _pub_by_date.items()
                                for p in ps if d.startswith(f"{_sel_year}-{_sel_month:02d}")]
            _month_published.sort(key=lambda x: x[0])

            if not _month_plan and not _month_published:
                st.info("Sin artículos este mes. Pulsa **Auto-programar** para llenar el calendario.")
            else:
                for _e in sorted(_month_plan, key=lambda x: x.get("date", "")):
                    _e_kw   = _e.get("keyword") or "auto"
                    _e_date = _e.get("date", "")
                    _e_st   = _e.get("status", "pending")
                    _e_time = (_e.get("datetime") or "")[-8:-3] or "09:00"
                    _st_badge = '<span style="color:#0a84ff">⏰ programado</span>' if _e_st == "pending" else '<span style="color:#30d158">✅ publicado</span>'
                    _del_key = f"del_plan_{_e.get('id','')}"
                    _row_cols = st.columns([4, 1])
                    with _row_cols[0]:
                        st.markdown(
                            f'<div style="background:#1c1c1e;border-radius:8px;padding:8px 12px;margin-bottom:4px;border:1px solid rgba(10,132,255,.2)">'
                            f'<span style="color:rgba(255,255,255,.5);font-size:.72rem">{_e_date} {_e_time}</span> {_st_badge}<br>'
                            f'<span style="color:#fff;font-size:.85rem">🎯 {_e_kw}</span></div>',
                            unsafe_allow_html=True,
                        )
                    with _row_cols[1]:
                        if st.button("✕", key=_del_key, help="Eliminar"):
                            _plan_all = [x for x in _plan_all if x.get("id") != _e.get("id")]
                            save_json("schedule_plan.json", _plan_all)
                            st.rerun()
                for _d, _p in _month_published:
                    _score = _p.get("seo_score", "-")
                    _kw    = _p.get("keyword", "—")
                    _title = _p.get("title", "Sin título")[:40]
                    _link  = _p.get("link", "")
                    _link_html = f' <a href="{_link}" target="_blank" style="color:#0a84ff;font-size:.75rem">↗</a>' if _link else ""
                    st.markdown(
                        f'<div style="background:rgba(48,209,88,.06);border-radius:8px;padding:8px 12px;margin-bottom:4px;border:1px solid rgba(48,209,88,.2)">'
                        f'<span style="color:rgba(255,255,255,.5);font-size:.72rem">{_d}</span> <span style="color:#30d158;font-size:.72rem">✅ publicado</span><br>'
                        f'<span style="color:#fff;font-size:.85rem">{_title}</span>{_link_html}</div>',
                        unsafe_allow_html=True,
                    )

    # ─── TAB 3: RANKMATH SEO ──────────────────────────────────────────────────
    with _pub_tab3:
        import os as _rm_os, requests as _rm_req

        st.markdown("Gestiona el SEO de tus artículos publicados directamente desde aquí. Los cambios se aplican en WordPress via API.")

        _rm_token  = _rm_os.environ.get("EXPERTOSEO_SECRET_TOKEN", "")
        _rm_config = _load_config_safe()
        _rm_url    = (_rm_config.get("sites") or [{}])[0].get("url", "").rstrip("/")
        _rm_pubs   = load_json("published.json")
        if not isinstance(_rm_pubs, list):
            _rm_pubs = []
        _rm_pubs_with_id = [p for p in _rm_pubs if p.get("post_id")]

        if not _rm_token:
            st.warning("Necesitas configurar `EXPERTOSEO_SECRET_TOKEN` para editar posts via API.")
        elif not _rm_pubs_with_id:
            st.info("Aún no hay artículos publicados con ID de WordPress. Publica el primero desde la pestaña **📤 Publicar artículo**.")
        else:
            # Selector de artículo
            _rm_options = {f"{p.get('title','?')[:50]} ({p.get('date','')[:10]})": p for p in reversed(_rm_pubs_with_id)}
            _rm_sel_label = st.selectbox("Selecciona un artículo", list(_rm_options.keys()))
            _rm_sel = _rm_options[_rm_sel_label]
            _rm_post_id = _rm_sel.get("post_id")

            # Fetch datos actuales del post
            if st.button("🔄 Cargar datos actuales de WordPress", key="rm_load"):
                with st.spinner("Cargando..."):
                    try:
                        _r = _rm_req.get(
                            f"{_rm_url}/wp-json/wp/v2/posts/{_rm_post_id}",
                            headers={"X-Expertoseo-Token": _rm_token},
                            timeout=10,
                        )
                        if _r.status_code == 200:
                            _post_data = _r.json()
                            st.session_state["rm_post_data"] = _post_data
                            st.success("✅ Datos cargados")
                        else:
                            st.error(f"Error {_r.status_code}: {_r.text[:200]}")
                    except Exception as _ex:
                        st.error(str(_ex))

            _cached = st.session_state.get("rm_post_data", {})
            _meta = _cached.get("meta", {}) if isinstance(_cached.get("meta"), dict) else {}

            st.markdown("---")
            st.subheader("✏️ Editar SEO")

            with st.form("rankmath_form"):
                _rm_seo_title = st.text_input(
                    "🏷️ SEO Title (RankMath)",
                    value=_meta.get("rank_math_title", _rm_sel.get("seo_title", "")),
                    placeholder="Título SEO con keyword principal — puede incluir emojis 🏆",
                    help="Aparece en los resultados de Google. Máx. 60 caracteres recomendado."
                )
                _char_count = len(_rm_seo_title)
                _cc_color = "#30d158" if _char_count <= 60 else "#ff453a"
                st.markdown(f'<span style="font-size:.75rem;color:{_cc_color}">{_char_count}/60 caracteres</span>', unsafe_allow_html=True)

                _rm_meta_desc = st.text_area(
                    "📝 Meta descripción",
                    value=_meta.get("rank_math_description", _rm_sel.get("meta_description", "")),
                    height=80,
                    placeholder="Descripción que aparece en Google — incluye la keyword y un CTA. Máx. 155 caracteres.",
                )
                _mdc = len(_rm_meta_desc)
                _mdc_color = "#30d158" if _mdc <= 155 else "#ff453a"
                st.markdown(f'<span style="font-size:.75rem;color:{_mdc_color}">{_mdc}/155 caracteres</span>', unsafe_allow_html=True)

                _rm_focus_kw = st.text_input(
                    "🎯 Focus Keyword",
                    value=_meta.get("rank_math_focus_keyword", _rm_sel.get("keyword", "")),
                    placeholder="Keyword principal del artículo",
                )

                _rm_submit = st.form_submit_button("💾 Guardar en WordPress", type="primary", use_container_width=True)
                if _rm_submit:
                    _payload = {
                        "meta": {
                            "rank_math_title": _rm_seo_title,
                            "rank_math_description": _rm_meta_desc,
                            "rank_math_focus_keyword": _rm_focus_kw,
                        }
                    }
                    with st.spinner("Guardando en WordPress..."):
                        try:
                            _r = _rm_req.post(
                                f"{_rm_url}/wp-json/wp/v2/posts/{_rm_post_id}",
                                headers={"X-Expertoseo-Token": _rm_token, "Content-Type": "application/json"},
                                json=_payload,
                                timeout=15,
                            )
                            if _r.status_code in (200, 201):
                                st.success("✅ SEO actualizado en WordPress")
                                # Actualizar registro local
                                for _lp in _rm_pubs:
                                    if _lp.get("post_id") == _rm_post_id:
                                        _lp["seo_title"] = _rm_seo_title
                                        _lp["meta_description"] = _rm_meta_desc
                                        _lp["keyword"] = _rm_focus_kw
                                save_json("published.json", _rm_pubs)
                            else:
                                st.error(f"Error {_r.status_code}: {_r.text[:400]}")
                        except Exception as _ex:
                            st.error(str(_ex))

            # Enlace al artículo
            if _rm_sel.get("link"):
                st.markdown(f"🔗 [Ver artículo en WordPress]({_rm_sel['link']})")

    # ─── TAB 4: SEO INTERNO ───────────────────────────────────────────────────
    with _pub_tab4:
        st.markdown("Registro de las optimizaciones SEO aplicadas automáticamente por EXPERTOSEO a cada artículo.")

        _si_pubs = load_json("published.json")
        if not isinstance(_si_pubs, list) or not _si_pubs:
            st.info("Todavía no hay artículos publicados. El SEO Interno se mostrará aquí una vez que publiques el primero.")
        else:
            for _si_p in reversed(_si_pubs[-20:]):
                _si_title = _si_p.get("title", "Sin título")
                _si_kw    = _si_p.get("keyword", "—")
                _si_score = _si_p.get("seo_score", "—")
                _si_date  = (_si_p.get("date") or "")[:10]
                _si_link  = _si_p.get("link", "")
                _si_meta  = _si_p.get("meta_description", "—")
                _si_seo_t = _si_p.get("seo_title", "—")
                _si_tags  = _si_p.get("tags", [])
                _si_cat   = _si_p.get("categories", [])
                _si_score_color = "#30d158" if isinstance(_si_score, int) and _si_score >= 70 else "#ff9f0a" if isinstance(_si_score, int) and _si_score >= 50 else "#ff453a"

                with st.expander(f"📄 {_si_title[:60]} — {_si_date}", expanded=False):
                    _c1, _c2, _c3, _c4 = st.columns(4)
                    _c1.metric("Score SEO", f"{_si_score}/100")
                    _c2.metric("Keyword", _si_kw[:18] if _si_kw else "—")
                    _c3.metric("Fecha", _si_date or "—")
                    _c4.metric("Estado", _si_p.get("status", "—"))

                    st.markdown("**🏷️ SEO Title aplicado:**")
                    st.code(_si_seo_t, language=None)
                    st.markdown("**📝 Meta descripción:**")
                    st.code(_si_meta, language=None)
                    if _si_tags:
                        st.markdown(f"**🔖 Tags:** {', '.join(str(t) for t in _si_tags[:10])}")
                    if _si_cat:
                        st.markdown(f"**📁 Categorías:** {', '.join(str(c) for c in _si_cat[:5])}")
                    if _si_link:
                        st.markdown(f"[🔗 Ver en WordPress]({_si_link})")


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
    st.title("💬 Asistente SEO")
    st.markdown(
        "Pregunta cualquier cosa. El asistente tiene acceso real a WordPress, "
        "GSC, artículos, keywords y puede ejecutar acciones directamente."
    )

    # Acciones rápidas
    _qa_cols = st.columns(4)
    _qa_prompts = {
        "🔌 Estado WP": "Comprueba si WordPress está conectado y dime el resultado exacto",
        "📊 Rankings": "Muéstrame los rankings actuales de GSC y las oportunidades más importantes",
        "🔑 Keywords": "Muéstrame la cola de keywords y recomiéndame cuál publicar primero",
        "📝 Artículos": "Muéstrame los últimos artículos publicados con sus links y scores SEO",
    }
    for _qcol, (_qlabel, _qprompt) in zip(_qa_cols, _qa_prompts.items()):
        with _qcol:
            if st.button(_qlabel, use_container_width=True, key=f"qa_{_qlabel}"):
                st.session_state["pending_assistant_msg"] = _qprompt

    st.markdown("---")

    # Inicializar asistente
    if "seo_assistant" not in st.session_state:
        try:
            config = _load_config_safe()
            from expertoseo.assistant import SEOAssistant
            st.session_state["seo_assistant"] = SEOAssistant(config)
            st.session_state["chat_history"] = []
        except Exception as e:
            st.error(f"Error iniciando el asistente: {e}")
            st.stop()

    # Historial de chat
    for msg in st.session_state.get("chat_history", []):
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

    # Mensaje pre-cargado (desde botones de acceso rápido)
    if "pending_assistant_msg" in st.session_state:
        pending = st.session_state.pop("pending_assistant_msg")
        with st.chat_message("user", avatar="🧑"):
            st.markdown(pending)
        st.session_state["chat_history"].append({"role": "user", "content": pending})
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Consultando APIs... (puede tardar unos segundos)"):
                try:
                    response = st.session_state["seo_assistant"].chat(pending)
                    st.markdown(response)
                    st.session_state["chat_history"].append({"role": "assistant", "content": response})
                except Exception as e:
                    st.error(str(e))
        st.rerun()

    # Input
    if prompt := st.chat_input("Pregunta algo — puede ejecutar acciones reales en WordPress, GSC, etc."):
        with st.chat_message("user", avatar="🧑"):
            st.markdown(prompt)
        st.session_state["chat_history"].append({"role": "user", "content": prompt})

        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Pensando y consultando herramientas..."):
                try:
                    response = st.session_state["seo_assistant"].chat(prompt)
                    st.markdown(response)
                    st.session_state["chat_history"].append({"role": "assistant", "content": response})
                except Exception as e:
                    err_msg = f"❌ Error: {e}"
                    st.error(err_msg)
                    st.session_state["chat_history"].append({"role": "assistant", "content": err_msg})

    if st.session_state.get("chat_history"):
        if st.button("🗑️ Limpiar conversación"):
            st.session_state["chat_history"] = []
            config = _load_config_safe()
            from expertoseo.assistant import SEOAssistant
            st.session_state["seo_assistant"] = SEOAssistant(config)
            st.rerun()


# ─────────────────────────────────────────────
# PÁGINA: ESTADO DE APIs
# ─────────────────────────────────────────────
elif page == "🔌 Estado APIs":
    st.title("🔌 Estado de Conexiones")
    st.markdown("Comprueba que todas las APIs están correctamente configuradas antes de publicar.")

    import os

    # ── Diagnóstico de variables de entorno ──────────────────────────────
    REQUIRED_VARS = ["ANTHROPIC_API_KEY", "WP_APP_PASSWORD_SITE1", "OPENAI_API_KEY",
                     "UNSPLASH_ACCESS_KEY", "GOOGLE_SERVICE_ACCOUNT_JSON"]

    with st.expander("🔍 Diagnóstico: ¿qué variables ve el contenedor?", expanded=True):
        st.caption("Esto muestra exactamente qué variables tiene Railway en este contenedor.")
        found_any = False
        for var in REQUIRED_VARS:
            val = os.environ.get(var, "")
            if val:
                masked = val[:6] + "****" + val[-3:] if len(val) > 12 else "****"
                st.markdown(f"✅ `{var}` → `{masked}` ({len(val)} caracteres)")
                found_any = True
            else:
                st.markdown(f"❌ `{var}` → **no encontrada en el entorno del contenedor**")

        # Mostrar todas las variables de entorno que SÍ están (sin valores sensibles)
        all_env_keys = sorted(os.environ.keys())
        custom_keys = [k for k in all_env_keys if not k.startswith(("PATH", "HOME", "USER", "SHELL", "LANG", "LC_", "PWD", "SHLVL", "TERM", "HOSTNAME"))]
        st.markdown(f"\n**Variables personalizadas visibles en este contenedor ({len(custom_keys)}):**")
        st.code(" | ".join(custom_keys) if custom_keys else "(ninguna)", language=None)

        if not found_any:
            st.error("⚠️ **Ninguna variable de Railway está llegando al contenedor.** "
                     "Esto significa que el contenedor fue construido ANTES de añadir las variables. "
                     "Solución: **haz un Redeploy manual en Railway** (ver instrucciones abajo).")
            st.markdown("""
**Cómo hacer Redeploy manual en Railway:**
1. Ve a tu servicio EXPERTOSEO en Railway
2. Pestaña **Deployments**
3. En el deployment activo → clic en los **3 puntos** (⋮) de la derecha
4. Clic en **Redeploy**
5. Espera 2-3 minutos
6. Recarga esta página
""")

    def _check(label, fn):
        try:
            ok, msg = fn()
            if ok:
                st.success(f"✅ **{label}** — {msg}")
            else:
                st.error(f"❌ **{label}** — {msg}")
        except Exception as e:
            st.error(f"❌ **{label}** — Error: {e}")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("APIs de IA")

        # Claude
        def _test_claude():
            key = os.getenv("ANTHROPIC_API_KEY", "")
            if not key:
                return False, "ANTHROPIC_API_KEY no configurada en Railway Variables"
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            r = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10,
                                        messages=[{"role":"user","content":"hi"}])
            return True, f"Conectado correctamente (modelo: claude-haiku)"
        _check("Claude API", _test_claude)

        # OpenAI (opcional)
        def _test_openai():
            key = os.getenv("OPENAI_API_KEY", "")
            if not key:
                return True, "No configurada (opcional — portadas usarán Unsplash/Picsum)"
            return True, "API key presente"
        _check("OpenAI / DALL-E (opcional)", _test_openai)

        st.markdown("")
        st.subheader("Imágenes")

        # Unsplash
        def _test_unsplash():
            key = os.getenv("UNSPLASH_ACCESS_KEY", "")
            if not key:
                return True, "No configurada (usará Picsum — imágenes genéricas gratuitas)"
            resp = __import__("requests").get(
                "https://api.unsplash.com/photos/random",
                params={"query": "technology"},
                headers={"Authorization": f"Client-ID {key}"},
                timeout=8,
            )
            if resp.status_code == 200:
                return True, "Conectado — imágenes temáticas disponibles"
            return False, f"Error {resp.status_code} — verifica la clave"
        _check("Unsplash (imágenes)", _test_unsplash)

    with col2:
        st.subheader("WordPress")

        # WordPress
        def _test_wordpress():
            cfg = _safe_load_config()
            sites = cfg.get("sites", [])
            if not sites:
                return False, "No hay sitios en config.yaml"
            site = sites[0]
            url = site.get("url", "")
            creds = site.get("wp_app_password", "")
            if not creds:
                return False, f"WP_APP_PASSWORD_SITE1 no configurada en Railway Variables"
            if ":" not in creds:
                user = site.get("wp_user", "")
                pwd = creds
            else:
                user, pwd = creds.split(":", 1)
            resp = __import__("requests").get(
                f"{url.rstrip('/')}/wp-json/wp/v2/users/me",
                auth=(user.strip(), pwd.strip()),
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return True, f"Conectado como '{data.get('name', user)}' en {url}"
            elif resp.status_code == 401:
                return False, f"401 — Credenciales incorrectas para usuario '{user}'"
            elif resp.status_code == 403:
                return False, f"403 — El usuario '{user}' no existe en WordPress. Ve a 🗝️ Credenciales → introduce tu username real de WP"
            else:
                return False, f"Error {resp.status_code} — {url}"
        _check("WordPress REST API", _test_wordpress)

        # RankMath
        def _test_rankmath():
            cfg = _safe_load_config()
            sites = cfg.get("sites", [])
            if not sites:
                return False, "Sin sitios configurados"
            url = sites[0].get("url", "")
            resp = __import__("requests").get(
                f"{url.rstrip('/')}/wp-json/rankmath/v1/getHead",
                params={"url": url}, timeout=8,
            )
            if resp.status_code == 200:
                return True, "Plugin activo y REST API disponible"
            return False, "RankMath no responde — ¿está instalado y activado?"
        _check("RankMath Plugin", _test_rankmath)

        st.markdown("")
        st.subheader("Google Search Console")

        # GSC
        def _test_gsc():
            json_val = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
            if not json_val:
                return False, "GOOGLE_SERVICE_ACCOUNT_JSON no configurada (ver Checklist → Guía GSC)"
            # Detectar si es JSON inline o path
            if json_val.strip().startswith("{"):
                return True, "Credenciales JSON presentes — se usarán al actualizar rankings"
            elif os.path.exists(json_val):
                return True, f"Archivo de credenciales encontrado: {json_val}"
            else:
                return False, "El valor parece una ruta de archivo pero no existe. Pega el JSON completo como valor de la variable."
        _check("Google Search Console API", _test_gsc)

    st.markdown("---")
    st.info("💡 Pulsa **R** o recarga la página para volver a ejecutar los tests.")

    if st.button("🔄 Re-ejecutar todos los tests"):
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
# PÁGINA: CREDENCIALES
# ─────────────────────────────────────────────
elif page == "🗝️ Credenciales":
    import os as _os, requests as _req

    st.title("🗝️ Credenciales y API Keys")

    # ── Persistencia ─────────────────────────────────────────────────────────
    _creds_path = DATA_DIR / "credentials.yaml"
    _volume_ok  = _creds_path.exists()

    if not _volume_ok:
        st.error("""
**⚠️ Sin volumen persistente** — los datos se pierden cuando Railway redespliega.
Para que las credenciales (y artículos publicados, keywords, rankings) se guarden para siempre:
1. Ve a Railway → tu proyecto → pestaña **Volumes** → **Add Volume**
2. Mount path: `/app/data`
3. Despliega el servicio

Mientras tanto, añade las credenciales de WordPress directamente en **Railway Variables** (siguiendo las instrucciones de abajo).
""")

    # ── Estado actual ──────────────────────────────────────────────────────
    CREDS_DEF = [
        ("ANTHROPIC_API_KEY",           "Claude AI",            True),
        ("EXPERTOSEO_SECRET_TOKEN",     "WP Token (auth)",      True),
        ("WP_USERNAME_SITE1",           "WP Usuario",           False),
        ("WP_APP_PASSWORD_SITE1",       "WP Contraseña App",    False),
        ("OPENAI_API_KEY",              "OpenAI",               False),
        ("UNSPLASH_ACCESS_KEY",         "Unsplash",             False),
        ("GOOGLE_SERVICE_ACCOUNT_JSON", "Google GSC",           False),
    ]
    required_ok = all(_os.environ.get(k) for k, _, req in CREDS_DEF if req)
    if required_ok:
        st.success("✅ Todas las credenciales obligatorias están activas.")

    cols_s = st.columns(len(CREDS_DEF))
    for i, (key, label, req) in enumerate(CREDS_DEF):
        with cols_s[i]:
            val = _os.environ.get(key, "")
            if val:
                st.markdown(f'**{label}**\n\n<span class="cred-ok">✓ OK</span>', unsafe_allow_html=True)
            elif req:
                st.markdown(f'**{label}**\n\n<span class="cred-bad">✗ Falta</span>', unsafe_allow_html=True)
            else:
                st.markdown(f'**{label}**\n\n<span class="cred-opt">○ Opcional</span>', unsafe_allow_html=True)

    st.markdown("---")

    # ── MÉTODO 1: Railway Variables (RECOMENDADO — persiste) ─────────────
    with st.expander("🏆 Método recomendado: añadir a Railway Variables (persiste siempre)", expanded=not required_ok):
        st.markdown("""
Estos son los valores que debes añadir en **Railway → tu servicio → Variables**. Una vez guardados, sobreviven a todos los redespliegues automáticamente.

| Variable | Valor a poner |
|---|---|
| `WP_USERNAME_SITE1` | Tu usuario de login de WordPress |
| `WP_APP_PASSWORD_SITE1` | La Application Password de WordPress |

**¿Cómo añadir una variable en Railway?**
1. Ve a railway.app → tu proyecto → tu servicio → pestaña **Variables**
2. Pulsa **New Variable**
3. Escribe el nombre y el valor
4. Pulsa **Add** — Railway redesplegará automáticamente
""")
        # Auto-detect WP username
        if st.button("🔍 Detectar usuarios de WordPress", key="detect_users"):
            cfg = _safe_load_config()
            sites = cfg.get("sites", [])
            if sites:
                _url = sites[0].get("url", "").rstrip("/")
                with st.spinner("Consultando WordPress..."):
                    try:
                        r = _req.get(f"{_url}/wp-json/wp/v2/users", timeout=8)
                        if r.status_code == 200:
                            for u in r.json():
                                st.success(f"**Username (usa este):** `{u.get('slug','?')}` — Nombre: {u.get('name','?')}")
                        else:
                            st.info("WordPress no lista usuarios públicamente. Encuentra tu username en: WP Admin → Usuarios → Tu perfil → campo **Nombre de usuario**")
                    except Exception as ex:
                        st.error(str(ex))

    # ── MÉTODO 2: Formulario (sesión actual, se puede perder al redesplegar) ─
    with st.expander("💾 Guardar credenciales en este servidor (puede perderse sin volumen)", expanded=_volume_ok):
        st.caption("Rellena solo los campos que quieras actualizar. Los vacíos no se modifican.")
        with st.form("creds_form"):
            new_token = st.text_input("WordPress Token Secreto (EXPERTOSEO_SECRET_TOKEN) ← obligatorio",
                type="password", placeholder="expertoseo-secret-2025-xxxxx",
                help="El mismo valor que pusiste en el Code Snippet de WordPress")
            new_wp_user = st.text_input("WordPress Username (WP_USERNAME_SITE1) — opcional",
                placeholder="_adriaguerrero",
                help="Solo necesario si no usas el token secreto")
            new_wp_pass = st.text_input("WordPress Application Password (WP_APP_PASSWORD_SITE1) — opcional",
                type="password", placeholder="xxxx xxxx xxxx xxxx xxxx xxxx",
                help="Solo necesario si no usas el token secreto")
            new_anthropic = st.text_input("Claude AI API Key (ANTHROPIC_API_KEY)",
                type="password", placeholder="sk-ant-api03-...",
                help="console.anthropic.com → API Keys")
            new_openai = st.text_input("OpenAI API Key (opcional)", type="password", placeholder="sk-...")
            new_unsplash = st.text_input("Unsplash Key (opcional)", type="password", placeholder="access-key")
            new_gsc = st.text_area("Google Service Account JSON (opcional)", height=80,
                placeholder='{"type": "service_account", ...}')

            submitted = st.form_submit_button("💾 Guardar en servidor", type="primary", use_container_width=True)
            if submitted:
                _existing = {}
                if _creds_path.exists():
                    import yaml as _yaml
                    with open(_creds_path, encoding="utf-8") as _f:
                        _existing = _yaml.safe_load(_f) or {}
                _updates = {}
                if new_token.strip():     _updates["EXPERTOSEO_SECRET_TOKEN"] = new_token.strip()
                if new_wp_user.strip():   _updates["WP_USERNAME_SITE1"] = new_wp_user.strip()
                if new_wp_pass.strip():   _updates["WP_APP_PASSWORD_SITE1"] = new_wp_pass.strip()
                if new_anthropic.strip(): _updates["ANTHROPIC_API_KEY"] = new_anthropic.strip()
                if new_openai.strip():    _updates["OPENAI_API_KEY"] = new_openai.strip()
                if new_unsplash.strip():  _updates["UNSPLASH_ACCESS_KEY"] = new_unsplash.strip()
                if new_gsc.strip():       _updates["GOOGLE_SERVICE_ACCOUNT_JSON"] = new_gsc.strip()
                if _updates:
                    save_credentials_file({**_existing, **_updates})
                    st.success(f"✅ {len(_updates)} credencial(es) guardadas. Activas ahora mismo.")
                    st.rerun()
                else:
                    st.warning("No introdujiste ningún valor nuevo.")

    # ── Test WordPress ───────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔌 Conexión WordPress — Solución definitiva (token secreto)")

    _wp_token_now = _os.environ.get("EXPERTOSEO_SECRET_TOKEN", "")
    _wp_url_now   = (_safe_load_config().get("sites") or [{}])[0].get("url", "https://resenaspremium.com").rstrip("/")

    # El token que el usuario debe usar — si ya está configurado lo mostramos, si no sugerimos uno
    _suggested_token = _wp_token_now or "expertoseo-secret-2025-xk9mP"

    st.info("""
**¿Por qué falló antes?** Tu servidor (nginx/hosting) bloquea el header `Authorization` antes de que llegue a WordPress.
**Solución**: usar un header personalizado `X-Expertoseo-Token` que nginx NO bloquea. Solo necesitas hacer 2 cosas:
""")

    col_step1, col_step2 = st.columns(2)
    with col_step1:
        st.markdown("### Paso 1 — Snippet PHP en WordPress")
        st.markdown("Copia este código en **Code Snippets → Añadir nuevo** y actívalo:")
        php_snippet = f"""<?php
// EXPERTOSEO — Token Auth (bypass nginx)
// NO cambies la línea $secret — debe coincidir con Railway Variable

add_filter('determine_current_user', function($user_id) {{
    if (!empty($user_id)) return $user_id;
    $token  = $_SERVER['HTTP_X_EXPERTOSEO_TOKEN'] ?? '';
    $secret = '{_suggested_token}';
    if (!empty($token) && hash_equals($secret, $token)) {{
        return 1; // ID del usuario admin
    }}
    return $user_id;
}}, 20);

add_filter('rest_authentication_errors', function($result) {{
    if (get_current_user_id() > 0) return $result;
    $token  = $_SERVER['HTTP_X_EXPERTOSEO_TOKEN'] ?? '';
    $secret = '{_suggested_token}';
    if (!empty($token) && hash_equals($secret, $token)) {{
        return null; // sin error — usuario ya autenticado arriba
    }}
    return $result;
}});"""
        st.code(php_snippet, language="php")

    with col_step2:
        st.markdown("### Paso 2 — Variable en Railway")
        st.markdown("Añade esta variable en **Railway → tu servicio → Variables**:")
        st.code(f"EXPERTOSEO_SECRET_TOKEN = {_suggested_token}", language="bash")
        st.markdown("""
**Pasos exactos:**
1. Ve a [railway.app](https://railway.app) → tu proyecto → tu servicio
2. Pestaña **Variables** → **New Variable**
3. Nombre: `EXPERTOSEO_SECRET_TOKEN`
4. Valor: copia el token de arriba
5. Pulsa **Add** — Railway redespliega solo
""")
        if _wp_token_now:
            st.success(f"✅ EXPERTOSEO_SECRET_TOKEN ya está configurado ({len(_wp_token_now)} chars)")
        else:
            st.warning("❌ EXPERTOSEO_SECRET_TOKEN no está en el entorno todavía")

    st.markdown("---")
    st.subheader("🧪 Probar conexión")
    col_t1, col_t2 = st.columns([1, 2])
    with col_t1:
        _test_token = _wp_token_now
        if _test_token:
            st.caption(f"Token: `{_test_token[:8]}...` | Sitio: `{_wp_url_now}`")
            if st.button("🔌 Probar con Token", type="primary", use_container_width=True):
                with st.spinner("Conectando..."):
                    try:
                        r = _req.get(
                            f"{_wp_url_now}/wp-json/wp/v2/users/me",
                            headers={"X-Expertoseo-Token": _test_token},
                            timeout=10,
                        )
                        if r.status_code == 200:
                            u = r.json()
                            st.success(f"✅ Conectado como **{u.get('name', '?')}** (`{u.get('slug', '?')}`)")
                        else:
                            try:
                                body = r.json()
                                code = body.get("code", "?")
                                msg  = body.get("message", r.text[:300])
                            except Exception:
                                code, msg = str(r.status_code), r.text[:400]
                            st.error(f"❌ HTTP {r.status_code} — `{code}`")
                            st.code(msg, language=None)
                            if r.status_code == 403 and "<html" in r.text.lower():
                                st.warning("El snippet PHP no está activo todavía. ¿Activaste el snippet en Code Snippets?")
                            elif code == "rest_not_logged_in":
                                st.warning("El snippet PHP no está reconociendo el token. Comprueba que el token en el snippet coincide exactamente con EXPERTOSEO_SECRET_TOKEN.")
                    except Exception as ex:
                        st.error(str(ex))
        else:
            st.warning("Primero añade `EXPERTOSEO_SECRET_TOKEN` en Railway Variables (Paso 2) y redespliega.")

    with col_t2:
        with st.expander("🔧 Alternativa: Basic Auth (solo si el snippet del paso 1 no funciona)"):
            _wp_user_now = _os.environ.get("WP_USERNAME_SITE1", "")
            _wp_pass_now = _os.environ.get("WP_APP_PASSWORD_SITE1", "")
            st.caption("Estado Basic Auth:")
            st.markdown(f"Usuario: {'`' + _wp_user_now + '`' if _wp_user_now else '**❌ no configurado**'}")
            st.markdown(f"Password: {'✅ presente' if _wp_pass_now else '**❌ no configurado**'}")
            if _wp_user_now and _wp_pass_now:
                if st.button("Probar Basic Auth", use_container_width=True):
                    with st.spinner("Conectando..."):
                        try:
                            r = _req.get(f"{_wp_url_now}/wp-json/wp/v2/users/me",
                                         auth=(_wp_user_now, _wp_pass_now), timeout=10)
                            if r.status_code == 200:
                                st.success(f"✅ Basic Auth OK: {r.json().get('name', _wp_user_now)}")
                            else:
                                try:
                                    body = r.json()
                                    st.error(f"❌ {r.status_code}: {body.get('code','?')} — {body.get('message','')[:200]}")
                                except Exception:
                                    st.error(f"❌ {r.status_code}: {r.text[:400]}")
                        except Exception as ex:
                            st.error(str(ex))

# ── Las páginas no activas (Checklist, Estado APIs) siguen en el código pero
#    no están en el nav — se eliminan del menú para simplificar la interfaz.
if False:

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

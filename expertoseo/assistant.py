"""
Asistente SEO interactivo impulsado por Claude con herramientas reales.
Puede ejecutar acciones: publicar artículos, consultar WordPress, GSC, keywords, etc.
"""

import json
import os
import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt

from .utils import load_config, load_json, save_json, require_env, now_str, logger

console = Console()

SYSTEM_PROMPT = """Eres EXPERTOSEO — el agente SEO autónomo integrado en el sistema EXPERTOSEO.

IMPORTANTE: Eres parte de un sistema Python real. NO eres un chat genérico de IA.
Tienes herramientas reales que puedes ejecutar AHORA MISMO:
- Consultar WordPress (posts publicados, estado de conexión, editar posts)
- Ver y actualizar la cola de keywords
- Ver el plan de publicación del calendario
- Lanzar publicación de un artículo nuevo
- Consultar datos reales de Google Search Console
- Ver y analizar todos los artículos publicados

NUNCA digas que no puedes conectarte a APIs externas. PUEDES hacerlo mediante las herramientas disponibles.
NUNCA digas que eres solo un modelo de lenguaje sin acceso real. En EXPERTOSEO SÍ tienes acceso real.
Cuando el usuario pida algo que puedas hacer con una herramienta, ÚSALA inmediatamente.

=== DATOS DEL SISTEMA (actualizados en cada mensaje) ===
{context}
=== FIN DATOS ===

ESTILO DE RESPUESTA:
- Responde SIEMPRE en español
- Sé directo y concreto. Usa los datos reales del sistema
- Si el usuario pide un link, un artículo, datos de rankings: usa las herramientas para obtenerlos
- Al final de respuestas largas: **📋 Próximos 3 pasos:**"""


# ── Definición de herramientas reales ────────────────────────────────────────

TOOLS = [
    {
        "name": "test_wordpress",
        "description": "Comprueba si WordPress está conectado y devuelve el estado de la conexión y usuario autenticado.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_published_articles",
        "description": "Devuelve la lista de artículos publicados con título, keyword, SEO score, fecha y enlace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Número máximo de artículos a devolver (default 10)"}
            },
            "required": [],
        },
    },
    {
        "name": "get_keywords_queue",
        "description": "Devuelve las keywords actualmente en la cola de publicación.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "add_keyword",
        "description": "Añade una o varias keywords a la cola de publicación.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de keywords a añadir",
                }
            },
            "required": ["keywords"],
        },
    },
    {
        "name": "get_schedule_plan",
        "description": "Devuelve el plan de publicaciones programadas (calendario).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Número de entradas a devolver (default 10)"}
            },
            "required": [],
        },
    },
    {
        "name": "get_rankings",
        "description": "Devuelve los datos más recientes de Google Search Console: keywords, posiciones, clics, impresiones.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "enum": ["all", "top10", "top20", "opportunities"],
                    "description": "Filtro: all=todos, top10=top10, top20=top20, opportunities=posición 11-20",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_article_details",
        "description": "Devuelve los detalles completos de un artículo específico (por título o keyword).",
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Texto para buscar en título o keyword del artículo"}
            },
            "required": ["search"],
        },
    },
    {
        "name": "publish_article_now",
        "description": "Lanza el pipeline completo para generar y publicar un artículo ahora mismo. Usa con precaución.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Keyword objetivo (opcional, si no se especifica usa la siguiente de la cola)"},
                "as_draft": {"type": "boolean", "description": "Si true, publica como borrador para revisar antes"}
            },
            "required": [],
        },
    },
    {
        "name": "fetch_wordpress_posts",
        "description": "Obtiene los últimos posts directamente desde WordPress via REST API.",
        "input_schema": {
            "type": "object",
            "properties": {
                "per_page": {"type": "integer", "description": "Número de posts a obtener (default 5)"},
                "status": {"type": "string", "description": "Estado: publish, draft, all (default: publish)"}
            },
            "required": [],
        },
    },
]


# ── Implementación de herramientas ────────────────────────────────────────────

def _tool_test_wordpress(config: dict) -> dict:
    import requests as _req
    sites = config.get("sites", [])
    if not sites:
        return {"status": "error", "message": "No hay sitios configurados"}
    url = sites[0].get("url", "").rstrip("/")
    token = os.environ.get("EXPERTOSEO_SECRET_TOKEN", "")
    wp_user = os.environ.get("WP_USERNAME_SITE1", "")
    wp_pass = os.environ.get("WP_APP_PASSWORD_SITE1", "")
    try:
        headers = {}
        auth = None
        if token:
            headers["X-Expertoseo-Token"] = token
        elif wp_user and wp_pass:
            auth = (wp_user, wp_pass)
        else:
            return {"status": "error", "message": "Sin credenciales configuradas (EXPERTOSEO_SECRET_TOKEN o WP_USERNAME_SITE1+WP_APP_PASSWORD_SITE1)"}
        r = _req.get(f"{url}/wp-json/wp/v2/users/me", headers=headers, auth=auth, timeout=10)
        if r.status_code == 200:
            u = r.json()
            return {"status": "connected", "user": u.get("name"), "slug": u.get("slug"), "roles": u.get("roles", []), "url": url}
        else:
            try:
                body = r.json()
                return {"status": "error", "http_code": r.status_code, "wp_code": body.get("code"), "message": body.get("message", r.text[:200])}
            except Exception:
                return {"status": "error", "http_code": r.status_code, "message": r.text[:300]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _tool_get_published_articles(limit: int = 10) -> list:
    published = load_json("published.json")
    if not isinstance(published, list):
        return []
    result = []
    for p in published[:limit]:
        result.append({
            "title": p.get("title", "Sin título"),
            "keyword": p.get("keyword"),
            "seo_score": p.get("seo_score"),
            "date": (p.get("date") or "")[:10],
            "link": p.get("link"),
            "status": p.get("status"),
            "post_id": p.get("post_id") or p.get("id"),
            "seo_title": p.get("seo_title"),
            "meta_description": p.get("meta_description"),
        })
    return result


def _tool_get_keywords_queue() -> dict:
    queue = load_json("keywords.json")
    if not isinstance(queue, list):
        queue = []
    return {"count": len(queue), "keywords": queue}


def _tool_add_keyword(keywords: list) -> dict:
    queue = load_json("keywords.json")
    if not isinstance(queue, list):
        queue = []
    existing = set(queue)
    added = [k for k in keywords if k not in existing]
    queue.extend(added)
    save_json("keywords.json", queue)
    return {"added": added, "skipped": [k for k in keywords if k in existing], "total_in_queue": len(queue)}


def _tool_get_schedule_plan(limit: int = 10) -> list:
    plan = load_json("schedule_plan.json")
    if not isinstance(plan, list):
        return []
    return [
        {"date": e.get("date"), "time": (e.get("datetime") or "")[-8:-3], "keyword": e.get("keyword") or "auto", "status": e.get("status")}
        for e in plan[:limit]
    ]


def _tool_get_rankings(filter: str = "all") -> dict:
    rankings_history = load_json("rankings.json")
    if not isinstance(rankings_history, dict) or not rankings_history:
        return {"error": "No hay datos de GSC todavía. Conecta Google Search Console en Credenciales."}
    latest_date = max(rankings_history.keys())
    all_kws = rankings_history[latest_date]
    if filter == "top10":
        kws = [r for r in all_kws if r.get("position", 99) <= 10]
    elif filter == "top20":
        kws = [r for r in all_kws if r.get("position", 99) <= 20]
    elif filter == "opportunities":
        kws = [r for r in all_kws if 10 < r.get("position", 99) <= 20]
        kws = sorted(kws, key=lambda x: x.get("impressions", 0), reverse=True)
    else:
        kws = all_kws
    total_clicks = sum(r.get("clicks", 0) or 0 for r in all_kws)
    total_imp    = sum(r.get("impressions", 0) or 0 for r in all_kws)
    avg_pos      = sum(r.get("position", 0) for r in all_kws) / len(all_kws) if all_kws else 0
    return {
        "date": latest_date,
        "total_keywords": len(all_kws),
        "total_clicks": total_clicks,
        "total_impressions": total_imp,
        "avg_position": round(avg_pos, 1),
        "filter_applied": filter,
        "keywords": kws[:30],
    }


def _tool_get_article_details(search: str) -> dict:
    published = load_json("published.json")
    if not isinstance(published, list):
        return {"error": "Sin artículos publicados"}
    search_lower = search.lower()
    for p in published:
        title = (p.get("title") or "").lower()
        kw    = (p.get("keyword") or "").lower()
        if search_lower in title or search_lower in kw:
            return p
    return {"error": f"No se encontró artículo que coincida con '{search}'"}


def _tool_fetch_wordpress_posts(config: dict, per_page: int = 5, status: str = "publish") -> dict:
    import requests as _req
    sites = config.get("sites", [])
    if not sites:
        return {"error": "Sin sitios configurados"}
    url = sites[0].get("url", "").rstrip("/")
    token = os.environ.get("EXPERTOSEO_SECRET_TOKEN", "")
    wp_user = os.environ.get("WP_USERNAME_SITE1", "")
    wp_pass = os.environ.get("WP_APP_PASSWORD_SITE1", "")
    try:
        headers = {"X-Expertoseo-Token": token} if token else {}
        auth = (wp_user, wp_pass) if (not token and wp_user and wp_pass) else None
        params = {"per_page": per_page, "_fields": "id,title,link,status,date,slug"}
        if status != "all":
            params["status"] = status
        r = _req.get(f"{url}/wp-json/wp/v2/posts", headers=headers, auth=auth, params=params, timeout=15)
        if r.status_code == 200:
            posts = r.json()
            return {
                "posts": [{"id": p["id"], "title": p["title"]["rendered"], "link": p["link"], "status": p["status"], "date": p["date"][:10]} for p in posts],
                "total": len(posts),
            }
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def _tool_publish_article_now(config: dict, site_slug: str | None, keyword: str = "", as_draft: bool = False) -> dict:
    """Lanza el pipeline de publicación en un thread separado."""
    import threading
    result_container: list = [None]
    def _run():
        try:
            from .scheduler import run_full_pipeline
            from .utils import load_json as _lj, save_json as _sj
            if keyword.strip():
                q = _lj("keywords.json")
                if not isinstance(q, list):
                    q = []
                q.insert(0, keyword.strip())
                _sj("keywords.json", q)
            cfg = dict(config)
            if as_draft:
                cfg.setdefault("schedule", {})["publish_status"] = "draft"
            result_container[0] = run_full_pipeline(cfg, site_slug)
        except Exception as e:
            result_container[0] = {"status": "error", "error": str(e)}
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=180)  # esperar máximo 3 min
    result = result_container[0]
    if result is None:
        return {"status": "timeout", "message": "El pipeline tardó demasiado. Comprueba los logs en la pestaña Publicar."}
    return result


# ── Clase principal ───────────────────────────────────────────────────────────

class SEOAssistant:
    """Asistente SEO con herramientas reales via tool_use de Claude."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.client = anthropic.Anthropic(api_key=require_env("ANTHROPIC_API_KEY"))
        self.ai_config = self.config.get("ai", {})
        self.model = self.ai_config.get("assistant_model", "claude-sonnet-4-6")
        self.max_tokens = self.ai_config.get("max_tokens_assistant", 4000)
        self.site_slug = (self.config.get("schedule", {}) or {}).get("active_site")
        self.conversation_history: list[dict] = []

    def _build_context(self) -> str:
        lines = []

        # Sitio
        sites = self.config.get("sites", [])
        if sites:
            s = sites[0]
            lines.append(f"Sitio: {s.get('name', '?')} — {s.get('url', '?')}")
        niche = self.config.get("keywords", {}).get("niche", "")
        if niche:
            lines.append(f"Nicho: {niche}")

        # Estado APIs
        token = os.environ.get("EXPERTOSEO_SECRET_TOKEN", "")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        gsc_key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        lines.append(f"APIs: Claude={'✅' if anthropic_key else '❌'} | WordPress={'✅ (token)' if token else '❌'} | GSC={'✅' if gsc_key else '❌'}")

        # Keywords
        kw_queue = load_json("keywords.json")
        if isinstance(kw_queue, list) and kw_queue:
            lines.append(f"Cola keywords ({len(kw_queue)}): {', '.join(kw_queue[:6])}")

        # Artículos
        published = load_json("published.json")
        if isinstance(published, list) and published:
            scores = [p.get("seo_score") for p in published if isinstance(p.get("seo_score"), (int, float))]
            avg = round(sum(scores) / len(scores)) if scores else 0
            lines.append(f"Artículos publicados: {len(published)} | Score medio: {avg}/100")
            for p in published[:5]:
                lines.append(f"  [{(p.get('date') or '')[:10]}] {p.get('title','?')[:55]} | kw: {p.get('keyword','?')} | score: {p.get('seo_score','?')} | link: {p.get('link','—')}")
        else:
            lines.append("Artículos publicados: ninguno aún")

        # Rankings GSC
        rankings_history = load_json("rankings.json")
        if isinstance(rankings_history, dict) and rankings_history:
            latest_date = max(rankings_history.keys())
            latest = rankings_history[latest_date]
            total_clicks = sum(r.get("clicks", 0) or 0 for r in latest)
            total_imp    = sum(r.get("impressions", 0) or 0 for r in latest)
            avg_pos = sum(r.get("position", 0) for r in latest) / len(latest) if latest else 0
            top20_opp = sorted([r for r in latest if 10 < r.get("position", 99) <= 20], key=lambda x: x.get("impressions", 0), reverse=True)
            lines.append(f"GSC ({latest_date}): {len(latest)} kws | {total_clicks} clics | {total_imp} imp | pos.media {avg_pos:.1f}")
            if top20_opp:
                lines.append(f"Oportunidades rápidas TOP 11-20 ({len(top20_opp)}):")
                for r in top20_opp[:5]:
                    lines.append(f"  '{r['keyword']}' pos {r['position']:.1f} | {r.get('impressions',0)} imp")
        else:
            lines.append("GSC: sin datos (usa la herramienta get_rankings para más detalle)")

        # Plan de publicación
        plan = load_json("schedule_plan.json")
        if isinstance(plan, list):
            pending = [e for e in plan if e.get("status") == "pending"]
            if pending:
                lines.append(f"Plan programado: {len(pending)} artículos pendientes, próximo: {pending[0].get('date')} ({pending[0].get('keyword') or 'auto'})")

        return "\n".join(lines)

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Ejecuta una herramienta real y devuelve el resultado como JSON string."""
        try:
            if tool_name == "test_wordpress":
                result = _tool_test_wordpress(self.config)
            elif tool_name == "get_published_articles":
                result = _tool_get_published_articles(tool_input.get("limit", 10))
            elif tool_name == "get_keywords_queue":
                result = _tool_get_keywords_queue()
            elif tool_name == "add_keyword":
                result = _tool_add_keyword(tool_input.get("keywords", []))
            elif tool_name == "get_schedule_plan":
                result = _tool_get_schedule_plan(tool_input.get("limit", 10))
            elif tool_name == "get_rankings":
                result = _tool_get_rankings(tool_input.get("filter", "all"))
            elif tool_name == "get_article_details":
                result = _tool_get_article_details(tool_input.get("search", ""))
            elif tool_name == "fetch_wordpress_posts":
                result = _tool_fetch_wordpress_posts(
                    self.config,
                    tool_input.get("per_page", 5),
                    tool_input.get("status", "publish"),
                )
            elif tool_name == "publish_article_now":
                result = _tool_publish_article_now(
                    self.config,
                    self.site_slug,
                    tool_input.get("keyword", ""),
                    tool_input.get("as_draft", False),
                )
            else:
                result = {"error": f"Herramienta desconocida: {tool_name}"}
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"Error ejecutando herramienta {tool_name}: {e}")
            return json.dumps({"error": str(e)})

    def chat(self, user_message: str) -> str:
        """Envía un mensaje y obtiene respuesta con posibles llamadas a herramientas reales."""
        self.conversation_history.append({"role": "user", "content": user_message})

        context = self._build_context()
        system = SYSTEM_PROMPT.format(context=context)

        messages = list(self.conversation_history)

        # Agentic loop: Claude puede llamar múltiples herramientas antes de responder
        max_iterations = 5
        for _ in range(max_iterations):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                tools=TOOLS,
                messages=messages,
            )

            # Si hay llamadas a herramientas, ejecutarlas
            if response.stop_reason == "tool_use":
                # Añadir la respuesta del asistente con los tool_use blocks
                messages.append({"role": "assistant", "content": response.content})

                # Ejecutar cada herramienta y construir tool_result blocks
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.info(f"Asistente llama herramienta: {block.name}({block.input})")
                        output = self._execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": output,
                        })

                messages.append({"role": "user", "content": tool_results})
                continue  # siguiente iteración para que Claude procese los resultados

            # Respuesta final (stop_reason == "end_turn")
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text

            self.conversation_history.append({"role": "assistant", "content": final_text})
            return final_text

        # Si agotamos iteraciones
        return "Error: el asistente entró en un bucle. Intenta de nuevo."

    def run_interactive(self) -> None:
        """Inicia el chat interactivo en la terminal."""
        console.print(Panel(
            "[bold blue]EXPERTOSEO Assistant[/bold blue]\n"
            "Tu experto SEO personal impulsado por Claude.\n\n"
            "[dim]Comandos especiales:[/dim]\n"
            "  [cyan]/rankings[/cyan]  — Ver posiciones actuales\n"
            "  [cyan]/keywords[/cyan]  — Ver cola de keywords\n"
            "  [cyan]/publicar[/cyan]  — Generar y publicar artículo ahora\n"
            "  [cyan]/salir[/cyan]     — Cerrar el asistente",
            title="Bienvenido",
            border_style="blue",
        ))

        console.print("\n[dim]Analizando tu situación SEO actual...[/dim]")
        welcome = self.chat(
            "Hola, analiza mi situación SEO actual con los datos disponibles y "
            "dime cuáles son mis 3 prioridades más importantes ahora mismo."
        )
        console.print(Panel(Markdown(welcome), title="[bold]EXPERTOSEO[/bold]", border_style="green"))

        while True:
            try:
                user_input = Prompt.ask("\n[bold cyan]Tú[/bold cyan]").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Hasta luego.[/yellow]")
                break

            if not user_input:
                continue
            if user_input.lower() in ("/salir", "/exit", "salir", "exit"):
                console.print("[yellow]Hasta luego.[/yellow]")
                break

            console.print("[dim]Pensando...[/dim]")
            try:
                response = self.chat(user_input)
                console.print(Panel(Markdown(response), title="[bold]EXPERTOSEO[/bold]", border_style="green"))
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

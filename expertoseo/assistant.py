"""
Asistente SEO interactivo impulsado por Claude.
Chat en terminal con capacidad de ejecutar acciones reales.
"""

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt

from .utils import load_config, load_json, require_env, now_str, logger

console = Console()

SYSTEM_PROMPT = """Eres EXPERTOSEO, un experto en SEO de alto nivel con más de 10 años de experiencia.
Tu misión es ayudar al usuario a posicionarse en el TOP 1 de Google para todas sus webs.

Tienes acceso completo a los datos del sistema: artículos publicados, rankings de Google Search Console,
cola de keywords, configuración del sitio y métricas SEO. Úsalos siempre para dar respuestas concretas.

Eres experto en:
- SEO On-Page: optimización de contenido, metadatos, estructura HTML, schema markup, emojis en títulos
- SEO Off-Page: link building, autoridad de dominio, menciones de marca
- SEO Técnico: Core Web Vitals, indexación, sitemap, robots.txt, velocidad de carga
- Keyword Research: volumen, dificultad, intención de búsqueda, long-tail, clustering semántico
- Content Marketing: estrategia de contenidos, pillar pages, topic clusters, cadencia de publicación
- Google Search Console: análisis de datos, CTR, impresiones, posición media, detección de oportunidades
- WordPress + RankMath: configuración óptima, meta titles, meta descriptions, focus keywords, schema
- Algoritmos de Google: E-E-A-T, Helpful Content Update, Core Updates 2024-2025
- Elementor: compatibilidad de contenido, estructura de páginas

=== DATOS EN TIEMPO REAL DEL SISTEMA ===
{context}
=== FIN DE DATOS ===

CAPACIDADES DISPONIBLES:
- Tienes todos los datos del sistema listados arriba — úsalos directamente en tus respuestas
- Puedes analizar patrones en los artículos publicados y sugerir mejoras concretas
- Puedes identificar keywords en posición 11-20 para optimización rápida
- Puedes generar títulos con emojis, meta descripciones, estrategias de linking interno
- Puedes recomendar qué artículo publicar a continuación según los gaps de keywords

REGLAS:
- Responde SIEMPRE en español
- Sé concreto y accionable — cita datos reales del sistema cuando los tengas
- Nunca des consejos genéricos si hay datos disponibles para ser específico
- Cuando detectes una oportunidad clara (keyword en pos 11-20, artículo con score bajo, etc.), priorízala
- Si el usuario pregunta sobre rankings, artículos o keywords, USA los datos de arriba
- Al final de cada respuesta larga, incluye: **📋 Próximos 3 pasos prioritarios:**"""


class SEOAssistant:
    """Asistente SEO interactivo con Claude."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.client = anthropic.Anthropic(api_key=require_env("ANTHROPIC_API_KEY"))
        self.ai_config = self.config.get("ai", {})
        self.model = self.ai_config.get("assistant_model", "claude-sonnet-4-6")
        self.max_tokens = self.ai_config.get("max_tokens_assistant", 4000)
        self.conversation_history: list[dict] = []

    def _build_context(self) -> str:
        """Construye el contexto con datos actuales del sistema."""
        import os
        lines = []

        # ── Sitio y configuración ──────────────────────────────────────────
        sites = self.config.get("sites", [])
        if sites:
            s = sites[0]
            lines.append(f"Sitio web: {s.get('name', '?')} — {s.get('url', '?')}")
        niche = self.config.get("keywords", {}).get("niche", "")
        if niche:
            lines.append(f"Nicho: {niche}")

        # ── Estado de APIs ─────────────────────────────────────────────────
        wp_token = os.environ.get("EXPERTOSEO_SECRET_TOKEN", "")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        gsc_key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        lines.append(f"APIs: Claude={'✅' if anthropic_key else '❌'} | WordPress Token={'✅' if wp_token else '❌'} | GSC={'✅' if gsc_key else '❌'}")

        # ── Keywords en cola ───────────────────────────────────────────────
        kw_queue = load_json("keywords.json")
        if isinstance(kw_queue, list) and kw_queue:
            lines.append(f"\nKeywords en cola ({len(kw_queue)}): {', '.join(kw_queue[:8])}")
        else:
            lines.append("\nCola de keywords: vacía")

        # ── Artículos publicados ───────────────────────────────────────────
        published = load_json("published.json")
        if isinstance(published, list) and published:
            scores = [p.get("seo_score") for p in published if isinstance(p.get("seo_score"), (int, float))]
            avg_score = round(sum(scores) / len(scores)) if scores else 0
            lines.append(f"\nArtículos publicados: {len(published)} total | Score SEO medio: {avg_score}/100")

            # Últimos 8 artículos con detalle
            lines.append("Últimos artículos:")
            for p in reversed(published[-8:]):
                sc = p.get("seo_score", "—")
                kw = p.get("keyword", "—")
                dt = (p.get("date") or "")[:10]
                title = p.get("title", "Sin título")[:60]
                seo_t = p.get("seo_title", "")[:50]
                lines.append(f"  [{dt}] {title}")
                lines.append(f"     Keyword: {kw} | Score: {sc}/100 | SEO Title: {seo_t or '(no configurado)'}")

            # Artículos con score bajo (mejora rápida)
            low_score = [p for p in published if isinstance(p.get("seo_score"), int) and p["seo_score"] < 60]
            if low_score:
                lines.append(f"\nArtículos con score SEO bajo (<60) — oportunidad de mejora:")
                for p in low_score[:5]:
                    lines.append(f"  - '{p.get('title','?')[:50]}' → Score: {p.get('seo_score')}/100")
        else:
            lines.append("\nArtículos publicados: ninguno todavía")

        # ── Rankings Google Search Console ────────────────────────────────
        rankings_history = load_json("rankings.json")
        if isinstance(rankings_history, dict) and rankings_history:
            latest_date = max(rankings_history.keys())
            latest = rankings_history[latest_date]

            total_clicks = sum(r.get("clicks", 0) or 0 for r in latest)
            total_impressions = sum(r.get("impressions", 0) or 0 for r in latest)
            avg_pos = sum(r.get("position", 0) for r in latest) / len(latest) if latest else 0

            lines.append(f"\n=== Google Search Console ({latest_date}) ===")
            lines.append(f"Palabras clave rastreadas: {len(latest)}")
            lines.append(f"Clics: {total_clicks} | Impresiones: {total_impressions} | Posición media: {avg_pos:.1f}")

            top3  = sorted([r for r in latest if r.get("position", 99) <= 3],  key=lambda x: x.get("clicks", 0), reverse=True)
            top10 = sorted([r for r in latest if 3 < r.get("position", 99) <= 10], key=lambda x: x.get("clicks", 0), reverse=True)
            top20 = sorted([r for r in latest if 10 < r.get("position", 99) <= 20], key=lambda x: x.get("impressions", 0), reverse=True)
            top50 = sorted([r for r in latest if 20 < r.get("position", 99) <= 50], key=lambda x: x.get("impressions", 0), reverse=True)

            if top3:
                lines.append(f"\nTOP 1-3 ({len(top3)} keywords) — ya están posicionadas, optimizar CTR:")
                for r in top3[:8]:
                    lines.append(f"  '{r['keyword']}' → pos {r['position']:.1f} | {r.get('clicks',0)} clicks | {r.get('impressions',0)} imp | CTR {r.get('ctr',0)*100:.1f}%")
            if top10:
                lines.append(f"\nTOP 4-10 ({len(top10)} keywords) — zona de clics, mantener y mejorar:")
                for r in top10[:8]:
                    lines.append(f"  '{r['keyword']}' → pos {r['position']:.1f} | {r.get('clicks',0)} clicks | {r.get('impressions',0)} imp")
            if top20:
                lines.append(f"\nTOP 11-20 ({len(top20)} keywords) — OPORTUNIDAD RÁPIDA, un push puede llevarlas al TOP 10:")
                for r in top20[:10]:
                    lines.append(f"  '{r['keyword']}' → pos {r['position']:.1f} | {r.get('impressions',0)} imp | {r.get('clicks',0)} clicks")
            if top50:
                lines.append(f"\nTOP 21-50 ({len(top50)} keywords) — potencial a medio plazo:")
                for r in top50[:8]:
                    lines.append(f"  '{r['keyword']}' → pos {r['position']:.1f} | {r.get('impressions',0)} imp")

            # Calcular tendencia simple (si hay datos de fecha anterior)
            dates = sorted(rankings_history.keys())
            if len(dates) >= 2:
                prev_date = dates[-2]
                prev = rankings_history[prev_date]
                prev_clicks = sum(r.get("clicks", 0) or 0 for r in prev)
                delta = total_clicks - prev_clicks
                trend = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
                lines.append(f"\nTendencia clics ({prev_date} → {latest_date}): {trend} {delta:+d} clics")
        else:
            lines.append("\nGSC: no hay datos todavía. El usuario debe conectar Google Search Console en Credenciales.")

        return "\n".join(lines)

    def chat(self, user_message: str) -> str:
        """Envía un mensaje y obtiene respuesta del asistente."""
        self.conversation_history.append({"role": "user", "content": user_message})

        context = self._build_context()
        system = SYSTEM_PROMPT.format(context=context)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=self.conversation_history,
        )

        assistant_message = response.content[0].text
        self.conversation_history.append({"role": "assistant", "content": assistant_message})
        return assistant_message

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

        # Mensaje de bienvenida con análisis inicial
        console.print("\n[dim]Analizando tu situación SEO actual...[/dim]")
        welcome = self.chat(
            "Hola, analiza mi situación SEO actual con los datos disponibles y "
            "dime cuáles son mis 3 prioridades más importantes para mejorar el posicionamiento ahora mismo."
        )
        console.print(Panel(Markdown(welcome), title="[bold]EXPERTOSEO[/bold]", border_style="green"))

        # Bucle principal de chat
        while True:
            try:
                user_input = Prompt.ask("\n[bold cyan]Tú[/bold cyan]").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Hasta luego.[/yellow]")
                break

            if not user_input:
                continue

            # Comandos especiales
            if user_input.lower() in ("/salir", "/exit", "salir", "exit"):
                console.print("[yellow]Hasta luego.[/yellow]")
                break

            if user_input.lower() == "/rankings":
                self._show_rankings()
                continue

            if user_input.lower() == "/keywords":
                self._show_keywords()
                continue

            if user_input.lower() == "/publicar":
                self._run_pipeline()
                continue

            # Chat normal con Claude
            console.print("[dim]Pensando...[/dim]")
            try:
                response = self.chat(user_input)
                console.print(Panel(
                    Markdown(response),
                    title="[bold]EXPERTOSEO[/bold]",
                    border_style="green",
                ))
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

    def _show_rankings(self) -> None:
        """Muestra rankings actuales."""
        from .ranking_tracker import RankingTracker
        tracker = RankingTracker(self.config)
        tracker.print_report()

    def _show_keywords(self) -> None:
        """Muestra la cola de keywords."""
        queue = load_json("keywords.json")
        if isinstance(queue, list) and queue:
            console.print(f"\n[bold]Cola de keywords ({len(queue)}):[/bold]")
            for i, kw in enumerate(queue[:20], 1):
                console.print(f"  {i}. {kw}")
        else:
            console.print("[yellow]La cola de keywords está vacía.[/yellow]")

    def _run_pipeline(self) -> None:
        """Ejecuta el pipeline completo de publicación."""
        from .scheduler import run_full_pipeline
        console.print("\n[bold]Iniciando pipeline de publicación...[/bold]")
        result = run_full_pipeline(self.config)
        if result.get("status") == "success":
            console.print(f"[green]Publicado: {result.get('link')}[/green]")
        else:
            console.print(f"[red]Error: {result.get('error')}[/red]")

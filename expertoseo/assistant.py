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

Eres un experto en:
- SEO On-Page: optimización de contenido, metadatos, estructura HTML, schema markup
- SEO Off-Page: link building, autoridad de dominio, menciones de marca
- SEO Técnico: Core Web Vitals, indexación, sitemap, robots.txt, velocidad de carga
- Keyword Research: volumen, dificultad, intención de búsqueda, long-tail
- Content Marketing: estrategia de contenidos, pillar pages, topic clusters
- Google Search Console: análisis de datos, detección de problemas
- WordPress + RankMath: configuración óptima, checklist de publicación
- Algoritmos de Google: E-E-A-T, Helpful Content Update, Core Updates

DATOS DE CONTEXTO (actualizados):
{context}

CAPACIDADES DISPONIBLES:
- Puedes sugerir al usuario ejecutar comandos específicos de EXPERTOSEO
- Analizas datos de rankings y keywords del sistema
- Das recomendaciones concretas y priorizadas
- Generas estrategias SEO personalizadas para el nicho del usuario

REGLAS:
- Responde siempre en español
- Sé concreto y accionable. No des consejos genéricos
- Cuando detectes una oportunidad clara, priorízala y explica por qué
- Si el usuario pregunta sobre sus rankings, usa los datos de contexto
- Si necesitas datos que no tienes, díselo claramente
- Usa ejemplos reales y específicos cuando sea posible
- Al final de cada respuesta larga, resume los 3 próximos pasos prioritarios"""


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
        lines = []

        # Sitios configurados
        sites = self.config.get("sites", [])
        if sites:
            site_info = ", ".join(f"{s.get('name')} ({s.get('url')})" for s in sites)
            lines.append(f"Sitios web: {site_info}")

        # Nicho
        niche = self.config.get("keywords", {}).get("niche", "")
        if niche:
            lines.append(f"Nicho principal: {niche}")

        # Keywords en cola
        kw_queue = load_json("keywords.json")
        if isinstance(kw_queue, list) and kw_queue:
            lines.append(f"Keywords en cola ({len(kw_queue)}): {', '.join(kw_queue[:5])}")

        # Últimas publicaciones
        published = load_json("published.json")
        if isinstance(published, list) and published:
            lines.append(f"\nÚltimos artículos publicados ({len(published)} total):")
            for p in published[:5]:
                status = p.get("status", "?")
                score = p.get("seo_score", "-")
                lines.append(f"  - '{p.get('title', 'Sin título')}' | Score: {score}/100 | {p.get('date', '')[:10]}")

        # Rankings y datos GSC más recientes
        rankings_history = load_json("rankings.json")
        if isinstance(rankings_history, dict) and rankings_history:
            latest_date = max(rankings_history.keys())
            latest = rankings_history[latest_date]

            total_clicks = sum(r.get("clicks", 0) or 0 for r in latest)
            total_impressions = sum(r.get("impressions", 0) or 0 for r in latest)
            avg_pos = sum(r.get("position", 0) for r in latest) / len(latest) if latest else 0

            lines.append(f"\n=== Datos Google Search Console ({latest_date}) ===")
            lines.append(f"Keywords rastreadas: {len(latest)}")
            lines.append(f"Clics totales: {total_clicks} | Impresiones: {total_impressions} | Posición media: {avg_pos:.1f}")

            top3  = [r for r in latest if r.get("position", 99) <= 3]
            top10 = [r for r in latest if r.get("position", 99) <= 10]
            top20 = [r for r in latest if r.get("position", 99) <= 20]
            top50 = [r for r in latest if 20 < r.get("position", 99) <= 50]

            if top3:
                lines.append(f"\nKeywords TOP 1-3 ({len(top3)}):")
                for r in top3[:10]:
                    lines.append(f"  - '{r['keyword']}' → pos {r['position']} | {r.get('clicks',0)} clicks | {r.get('impressions',0)} impresiones")
            if top10:
                lines.append(f"\nKeywords TOP 4-10 ({len(top10)}):")
                for r in top10[:10]:
                    lines.append(f"  - '{r['keyword']}' → pos {r['position']} | {r.get('clicks',0)} clicks | {r.get('impressions',0)} impresiones")
            if top20:
                lines.append(f"\nKeywords TOP 11-20 (oportunidades rápidas) ({len(top20)}):")
                for r in top20[:10]:
                    lines.append(f"  - '{r['keyword']}' → pos {r['position']} | {r.get('impressions',0)} impresiones")
            if top50:
                lines.append(f"\nKeywords TOP 21-50 (potencial a medio plazo) ({len(top50)} keywords)")
                # Ordenar por impresiones descendente para priorizar
                for r in sorted(top50, key=lambda x: x.get("impressions", 0), reverse=True)[:5]:
                    lines.append(f"  - '{r['keyword']}' → pos {r['position']} | {r.get('impressions',0)} impresiones")
        else:
            lines.append("\nGSC no conectado todavía — anima al usuario a configurar las credenciales para ver sus rankings.")

        if not lines:
            lines.append("No hay datos disponibles aún. Configura los sitios y ejecuta los primeros análisis.")

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

#!/usr/bin/env python3
"""
EXPERTOSEO — Herramienta de automatización SEO impulsada por Claude AI.

Comandos:
  assistant       Chat con el asistente SEO
  generate        Generar un artículo SEO
  publish         Generar y publicar un artículo ahora
  schedule        Gestionar el scheduler automático
  keywords        Gestionar la cola de keywords
  rankings        Ver posiciones en Google
  audit           Auditar artículos publicados
  sites           Gestionar sitios WordPress
"""

import argparse
import sys

from rich.console import Console
from rich.panel import Panel

console = Console()


def cmd_assistant(args) -> None:
    """Inicia el chat con el asistente SEO."""
    from expertoseo.utils import load_env, load_config
    load_env()
    config = load_config()
    from expertoseo.assistant import SEOAssistant
    assistant = SEOAssistant(config)
    assistant.run_interactive()


def cmd_generate(args) -> None:
    """Genera un artículo SEO (sin publicar)."""
    from expertoseo.utils import load_env, load_config
    load_env()
    config = load_config()

    keyword = args.keyword
    if not keyword:
        from expertoseo.keyword_research import KeywordResearch
        kw = KeywordResearch(config, args.site)
        keyword, _ = kw.get_next_keyword()
        console.print(f"Keyword seleccionada: [bold cyan]{keyword}[/bold cyan]")

    from expertoseo.article_generator import ArticleGenerator
    from expertoseo.seo_optimizer import SEOOptimizer

    generator = ArticleGenerator(config)
    article = generator.generate(keyword)

    optimizer = SEOOptimizer(config)
    report = optimizer.analyze(article)
    optimizer.print_report(report)

    # Guardar artículo generado localmente
    import json
    from expertoseo.utils import DATA_DIR
    out_path = DATA_DIR / f"draft_{article.slug}.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "keyword": article.keyword,
                "seo_title": article.seo_title,
                "meta_description": article.meta_description,
                "slug": article.slug,
                "focus_keyword": article.focus_keyword,
                "article_html": article.article_html,
                "faq_items": article.faq_items,
                "image_prompt": article.image_prompt,
                "tags": article.tags,
                "seo_score": report.score,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    console.print(f"\n[green]Artículo guardado en:[/green] {out_path}")
    console.print(f"Para publicarlo: [bold]python main.py publish --from-draft {article.slug}[/bold]")


def cmd_publish(args) -> None:
    """Genera y publica un artículo (o publica uno ya generado)."""
    from expertoseo.utils import load_env, load_config
    load_env()
    config = load_config()

    if args.from_draft:
        # Publicar artículo guardado como borrador
        import json
        from expertoseo.utils import DATA_DIR
        draft_path = DATA_DIR / f"draft_{args.from_draft}.json"
        if not draft_path.exists():
            console.print(f"[red]Borrador no encontrado: {draft_path}[/red]")
            sys.exit(1)

        with open(draft_path, encoding="utf-8") as f:
            draft = json.load(f)

        from expertoseo.article_generator import ArticleData, ArticleGenerator
        from expertoseo.image_generator import ImageGenerator
        from expertoseo.publisher import WordPressPublisher
        from expertoseo.rankmath_controller import RankMathController

        article = ArticleData(
            keyword=draft["keyword"],
            seo_title=draft["seo_title"],
            meta_description=draft["meta_description"],
            slug=draft["slug"],
            focus_keyword=draft["focus_keyword"],
            secondary_keywords=draft.get("secondary_keywords", []),
            article_html=draft["article_html"],
            faq_items=draft.get("faq_items", []),
            image_prompt=draft["image_prompt"],
            suggested_internal_links=draft.get("suggested_internal_links", []),
            word_count_estimate=draft.get("word_count_estimate", 0),
            tags=draft.get("tags", []),
        )

        img_gen = ImageGenerator(config)
        image_path = img_gen.generate(article.image_prompt, article.slug)

        generator = ArticleGenerator(config)
        from expertoseo.utils import get_site_config
        site = get_site_config(config, args.site)
        schema_html = (
            generator.generate_article_schema(article, site["url"])
            + "\n"
            + generator.generate_faq_schema(article.faq_items)
        )

        status = "draft" if args.draft else "publish"
        publisher = WordPressPublisher(config, args.site)
        post = publisher.publish(article, image_path, status=status, schema_html=schema_html)

        rankmath = RankMathController(config, args.site)
        rankmath.configure_post(post["id"], article)

        console.print(f"\n[green]Publicado:[/green] {post.get('link')}")
    else:
        # Pipeline completo
        from expertoseo.scheduler import run_full_pipeline
        status_override = "draft" if args.draft else None
        if status_override:
            config.setdefault("schedule", {})["publish_status"] = status_override
        run_full_pipeline(config, args.site)


def cmd_schedule(args) -> None:
    """Gestiona el scheduler automático."""
    from expertoseo.utils import load_env, load_config
    load_env()
    config = load_config()

    if args.action == "start":
        from expertoseo.scheduler import ArticleScheduler
        scheduler = ArticleScheduler(config)
        scheduler.start()
    elif args.action == "run-now":
        from expertoseo.scheduler import run_full_pipeline
        run_full_pipeline(config, args.site)
    else:
        console.print("[red]Acción no reconocida. Usa: start | run-now[/red]")


def cmd_keywords(args) -> None:
    """Gestiona la cola de keywords."""
    from expertoseo.utils import load_env, load_config, load_json, save_json
    load_env()
    config = load_config()

    if args.action == "list":
        queue = load_json("keywords.json")
        if isinstance(queue, list) and queue:
            console.print(f"[bold]Cola de keywords ({len(queue)}):[/bold]")
            for i, kw in enumerate(queue, 1):
                console.print(f"  {i}. {kw}")
        else:
            console.print("[yellow]La cola está vacía.[/yellow]")

    elif args.action == "add":
        if not args.keywords:
            console.print("[red]Especifica keywords: python main.py keywords add 'kw1' 'kw2'[/red]")
            sys.exit(1)
        from expertoseo.keyword_research import KeywordResearch
        kw = KeywordResearch(config)
        kw.add_keywords_to_queue(args.keywords)

    elif args.action == "clear":
        save_json("keywords.json", [])
        console.print("[yellow]Cola de keywords vaciada.[/yellow]")

    elif args.action == "suggest":
        from expertoseo.keyword_research import KeywordResearch
        kw = KeywordResearch(config, args.site)
        console.print("[dim]Buscando oportunidades de keywords...[/dim]")
        gsc = kw.get_gsc_opportunities()
        trends = kw.get_trending_keywords()
        if gsc:
            console.print(f"\n[bold green]Oportunidades GSC (top {len(gsc)}):[/bold green]")
            for r in gsc[:10]:
                console.print(f"  • '{r['keyword']}' — pos {r['position']} | {r['impressions']} impresiones")
        if trends:
            console.print(f"\n[bold blue]Tendencias Google:[/bold blue]")
            for t in trends[:10]:
                console.print(f"  • {t}")


def cmd_rankings(args) -> None:
    """Muestra las posiciones actuales en Google."""
    from expertoseo.utils import load_env, load_config
    load_env()
    config = load_config()
    from expertoseo.ranking_tracker import RankingTracker
    tracker = RankingTracker(config, args.site)
    tracker.print_report()


def cmd_audit(args) -> None:
    """Audita los artículos publicados."""
    from expertoseo.utils import load_env, load_config, load_json
    from rich.table import Table
    from rich import box
    load_env()

    published = load_json("published.json")
    if not isinstance(published, list) or not published:
        console.print("[yellow]No hay artículos publicados aún.[/yellow]")
        return

    table = Table(title="Artículos Publicados", box=box.SIMPLE, show_header=True)
    table.add_column("Título", max_width=40)
    table.add_column("Keyword", max_width=25)
    table.add_column("Score", justify="center")
    table.add_column("Estado", justify="center")
    table.add_column("Fecha")
    table.add_column("URL", max_width=30)

    for p in published[:30]:
        score = p.get("seo_score", "-")
        score_color = "green" if isinstance(score, int) and score >= 70 else "yellow"
        table.add_row(
            p.get("title", "-")[:40],
            p.get("keyword", "-")[:25],
            f"[{score_color}]{score}[/{score_color}]",
            p.get("status", "-"),
            (p.get("date") or p.get("timestamp", ""))[:10],
            p.get("link", "-")[:30],
        )

    console.print(table)


def cmd_sites(args) -> None:
    """Gestiona los sitios WordPress."""
    from expertoseo.utils import load_env, load_config
    load_env()
    config = load_config()
    from expertoseo.site_manager import SiteManager
    manager = SiteManager(config)

    if args.action == "list":
        manager.list_sites()
    elif args.action == "test":
        manager.test_site(args.site)
    elif args.action == "test-all":
        manager.test_all_sites()
    elif args.action == "info":
        manager.print_site_info(args.site)
    else:
        manager.list_sites()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="expertoseo",
        description="EXPERTOSEO — Automatización SEO con IA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # assistant
    sub = subparsers.add_parser("assistant", help="Chat con el asistente SEO")

    # generate
    sub = subparsers.add_parser("generate", help="Generar un artículo SEO")
    sub.add_argument("--keyword", "-k", help="Keyword objetivo")
    sub.add_argument("--site", "-s", help="Slug del sitio")

    # publish
    sub = subparsers.add_parser("publish", help="Generar y publicar un artículo")
    sub.add_argument("--keyword", "-k", help="Keyword objetivo")
    sub.add_argument("--site", "-s", help="Slug del sitio")
    sub.add_argument("--draft", action="store_true", help="Publicar como borrador")
    sub.add_argument("--from-draft", help="Publicar desde borrador guardado (slug)")

    # schedule
    sub = subparsers.add_parser("schedule", help="Gestionar el scheduler automático")
    sub.add_argument("action", choices=["start", "run-now"], help="start | run-now")
    sub.add_argument("--site", "-s", help="Slug del sitio")

    # keywords
    sub = subparsers.add_parser("keywords", help="Gestionar cola de keywords")
    sub.add_argument("action", choices=["list", "add", "clear", "suggest"], help="Acción")
    sub.add_argument("keywords", nargs="*", help="Keywords a añadir (para 'add')")
    sub.add_argument("--site", "-s", help="Slug del sitio")

    # rankings
    sub = subparsers.add_parser("rankings", help="Ver posiciones en Google")
    sub.add_argument("--site", "-s", help="Slug del sitio")

    # audit
    sub = subparsers.add_parser("audit", help="Auditar artículos publicados")

    # sites
    sub = subparsers.add_parser("sites", help="Gestionar sitios WordPress")
    sub.add_argument("action", nargs="?", default="list",
                     choices=["list", "test", "test-all", "info"])
    sub.add_argument("--site", "-s", help="Slug del sitio")

    args = parser.parse_args()

    if not args.command:
        console.print(Panel(
            "[bold blue]EXPERTOSEO[/bold blue] — Automatización SEO con IA\n\n"
            "Comandos disponibles:\n"
            "  [cyan]python main.py assistant[/cyan]              Chat con el asistente SEO\n"
            "  [cyan]python main.py generate -k 'keyword'[/cyan]  Generar artículo\n"
            "  [cyan]python main.py publish[/cyan]                Publicar artículo ahora\n"
            "  [cyan]python main.py schedule start[/cyan]         Iniciar autopublicación\n"
            "  [cyan]python main.py keywords suggest[/cyan]       Descubrir keywords\n"
            "  [cyan]python main.py rankings[/cyan]               Ver posiciones Google\n"
            "  [cyan]python main.py audit[/cyan]                  Auditar publicaciones\n"
            "  [cyan]python main.py sites[/cyan]                  Gestionar sitios\n\n"
            "[dim]Usa --help en cualquier comando para más información.[/dim]",
            title="Bienvenido",
            border_style="blue",
        ))
        sys.exit(0)

    commands = {
        "assistant": cmd_assistant,
        "generate": cmd_generate,
        "publish": cmd_publish,
        "schedule": cmd_schedule,
        "keywords": cmd_keywords,
        "rankings": cmd_rankings,
        "audit": cmd_audit,
        "sites": cmd_sites,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        console.print(f"[red]Comando desconocido: {args.command}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()

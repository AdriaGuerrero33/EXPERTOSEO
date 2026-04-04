"""
Scheduler automático: publica un artículo SEO cada 2 días.
"""

from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from rich.console import Console

from .utils import load_config, load_json, save_json, logger, now_str

console = Console()


def run_full_pipeline(config: dict | None = None, site_slug: str | None = None) -> dict:
    """
    Ejecuta el pipeline completo de publicación de un artículo:
    keyword_research → article_generator → seo_optimizer → image_generator → publisher → rankmath

    Returns:
        Dict con el resultado de la publicación.
    """
    from .keyword_research import KeywordResearch
    from .article_generator import ArticleGenerator
    from .seo_optimizer import SEOOptimizer
    from .image_generator import ImageGenerator
    from .publisher import WordPressPublisher
    from .rankmath_controller import RankMathController

    cfg = config or load_config()
    result = {"timestamp": now_str(), "status": "error", "site": site_slug}

    try:
        logger.info("=" * 60)
        logger.info("EXPERTOSEO — Iniciando pipeline de publicación")
        logger.info("=" * 60)

        # 1. Seleccionar keyword
        kw_research = KeywordResearch(cfg, site_slug)
        keyword, kw_context = kw_research.get_next_keyword()
        context = kw_research.get_context_summary()
        result["keyword"] = keyword

        gsc_data = kw_context.get("gsc_data", {})
        current_position = str(gsc_data.get("position", "No disponible"))

        # 2. Generar artículo con Claude
        generator = ArticleGenerator(cfg)
        article = generator.generate(
            keyword=keyword,
            competitors_summary=context.get("competitors_summary", ""),
            trends_summary=context.get("trends_summary", ""),
            current_position=current_position,
        )
        result["title"] = article.seo_title

        # 3. Validar SEO
        optimizer = SEOOptimizer(cfg)
        seo_report = optimizer.analyze(article)
        optimizer.print_report(seo_report)
        result["seo_score"] = seo_report.score

        if not seo_report.passed:
            logger.warning(
                f"Score SEO insuficiente ({seo_report.score}). "
                f"El artículo se publicará igualmente como borrador."
            )
            publish_status = "draft"
        else:
            publish_status = cfg.get("schedule", {}).get("publish_status", "publish")

        # 4. Generar portada
        image_gen = ImageGenerator(cfg)
        image_path = image_gen.generate(
            prompt=article.image_prompt,
            filename=article.slug,
        )
        result["image_path"] = str(image_path)

        # 5. Generar schemas JSON-LD
        from .utils import get_site_config
        site = get_site_config(cfg, site_slug)
        schema_html = (
            generator.generate_article_schema(article, site["url"])
            + "\n"
            + generator.generate_faq_schema(article.faq_items)
        )

        # 6. Publicar en WordPress
        publisher = WordPressPublisher(cfg, site_slug)
        post_result = publisher.publish(
            article=article,
            image_path=image_path,
            status=publish_status,
            schema_html=schema_html,
        )
        result.update(post_result)
        result["status"] = "success"

        # 7. Configurar RankMath
        rankmath = RankMathController(cfg, site_slug)
        rankmath.configure_post(post_result["id"], article)

        # 8. Guardar en historial
        _save_to_log(result)

        console.print(f"\n[bold green]Artículo publicado correctamente:[/bold green]")
        console.print(f"  URL: {post_result.get('link')}")
        console.print(f"  SEO Score: {seo_report.score}/100")
        console.print(f"  Status: {publish_status}\n")

    except Exception as e:
        logger.error(f"Error en pipeline: {e}", exc_info=True)
        result["error"] = str(e)
        _save_to_log(result)

    return result


def _save_to_log(entry: dict) -> None:
    """Guarda el resultado de la publicación en published.json."""
    log = load_json("published.json")
    if not isinstance(log, list):
        log = []
    log.insert(0, entry)
    # Mantener solo las últimas 500 entradas
    save_json("published.json", log[:500])


class ArticleScheduler:
    """Scheduler APScheduler que ejecuta el pipeline cada N días."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        schedule_cfg = self.config.get("schedule", {})
        self.interval_days = schedule_cfg.get("interval_days", 2)
        self.publish_time = schedule_cfg.get("publish_time", "09:00")
        self.timezone = schedule_cfg.get("timezone", "Europe/Madrid")
        self.site_slug = schedule_cfg.get("active_site")
        self.scheduler = BlockingScheduler(timezone=self.timezone)

    def start(self) -> None:
        """Inicia el scheduler bloqueante."""
        hour, minute = map(int, self.publish_time.split(":"))

        # Trigger: cada interval_days días a la hora configurada
        trigger = IntervalTrigger(
            days=self.interval_days,
            start_date=datetime.now().replace(hour=hour, minute=minute, second=0),
            timezone=self.timezone,
        )

        self.scheduler.add_job(
            func=self._run_job,
            trigger=trigger,
            id="publish_article",
            name=f"Publicar artículo SEO cada {self.interval_days} días",
            max_instances=1,
            coalesce=True,
        )

        console.print(
            f"\n[bold blue]Scheduler iniciado[/bold blue]\n"
            f"  Intervalo: cada {self.interval_days} días\n"
            f"  Hora: {self.publish_time} ({self.timezone})\n"
            f"  Sitio: {self.site_slug or 'activo por defecto'}\n"
            f"\n[dim]Presiona Ctrl+C para detener[/dim]\n"
        )

        try:
            self.scheduler.start()
        except KeyboardInterrupt:
            console.print("\n[yellow]Scheduler detenido.[/yellow]")
            self.scheduler.shutdown()

    def _run_job(self) -> None:
        """Job que ejecuta el pipeline completo."""
        console.print(f"\n[bold]Ejecutando pipeline automático — {now_str()}[/bold]")
        run_full_pipeline(self.config, self.site_slug)


class BackgroundArticleScheduler:
    """
    Scheduler en background (no bloqueante) para usar dentro de Streamlit u otros frameworks.
    Inicia el scheduler en un hilo daemon y retorna inmediatamente.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        schedule_cfg = self.config.get("schedule", {})
        self.interval_days = schedule_cfg.get("interval_days", 2)
        self.publish_time = schedule_cfg.get("publish_time", "09:00")
        self.timezone = schedule_cfg.get("timezone", "Europe/Madrid")
        self.site_slug = schedule_cfg.get("active_site")
        self.scheduler = BackgroundScheduler(timezone=self.timezone)
        self._started = False

    def start(self) -> None:
        """Inicia el scheduler en background. Puede llamarse varias veces (idempotente)."""
        if self._started or self.scheduler.running:
            return

        hour, minute = map(int, self.publish_time.split(":"))
        trigger = IntervalTrigger(
            days=self.interval_days,
            start_date=datetime.now().replace(hour=hour, minute=minute, second=0),
            timezone=self.timezone,
        )
        self.scheduler.add_job(
            func=self._run_job,
            trigger=trigger,
            id="publish_article_bg",
            name=f"Auto-publicar cada {self.interval_days} días",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        self.scheduler.start()
        self._started = True
        logger.info(
            f"Scheduler en background iniciado — cada {self.interval_days} días a las {self.publish_time}"
        )

    def stop(self) -> None:
        """Detiene el scheduler en background."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            self._started = False

    def get_next_run(self) -> str | None:
        """Retorna la fecha/hora de la próxima publicación como string."""
        jobs = self.scheduler.get_jobs()
        if jobs:
            next_run = jobs[0].next_run_time
            return next_run.strftime("%d/%m/%Y %H:%M") if next_run else None
        return None

    def _run_job(self) -> None:
        logger.info(f"Scheduler: iniciando pipeline automático — {now_str()}")
        run_full_pipeline(self.config, self.site_slug)

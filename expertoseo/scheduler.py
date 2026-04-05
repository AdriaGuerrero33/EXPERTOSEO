"""
Scheduler automático: publica un artículo SEO cada 2 días.
Soporta plan de publicación programada guardado en data/schedule_plan.json.
"""

import uuid
from datetime import datetime, timedelta, date
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from rich.console import Console

from .utils import load_config, load_json, save_json, logger, now_str

console = Console()


# ── Plan de publicación programada ────────────────────────────────────────────

def load_schedule_plan() -> list:
    """Carga el plan de publicación desde schedule_plan.json."""
    data = load_json("schedule_plan.json")
    return data if isinstance(data, list) else []


def save_schedule_plan(plan: list) -> None:
    """Guarda el plan de publicación en schedule_plan.json."""
    save_json("schedule_plan.json", plan)


def generate_auto_schedule(
    config: dict | None = None,
    n_articles: int = 15,
    interval_days: int = 2,
    publish_time: str = "09:00",
    start_from: date | None = None,
) -> list:
    """
    Genera automáticamente un plan de publicación: 1 artículo cada interval_days días.
    Respeta los artículos ya programados y las fechas ya publicadas.
    Devuelve el plan actualizado (existentes + nuevas entradas pendientes).
    """
    cfg = config or load_config()
    interval_days = cfg.get("schedule", {}).get("interval_days", interval_days)
    publish_time = cfg.get("schedule", {}).get("publish_time", publish_time)

    existing_plan = load_schedule_plan()
    # Fechas ya ocupadas (programadas o publicadas)
    occupied: set[str] = {e["date"] for e in existing_plan if e.get("date")}

    # Cargar publicaciones ya hechas
    published = load_json("published.json")
    if isinstance(published, list):
        for p in published:
            d = (p.get("date") or "")[:10]
            if d:
                occupied.add(d)

    hour, minute = map(int, publish_time.split(":"))
    start = start_from or date.today()
    # Buscar el siguiente slot libre a partir de hoy
    current = start
    new_entries = []
    added = 0
    max_iterations = n_articles * 10

    while added < n_articles and max_iterations > 0:
        max_iterations -= 1
        date_str = current.strftime("%Y-%m-%d")
        if date_str not in occupied:
            new_entries.append({
                "id": f"plan_{uuid.uuid4().hex[:8]}",
                "date": date_str,
                "datetime": f"{date_str}T{hour:02d}:{minute:02d}:00",
                "keyword": None,     # None = auto-seleccionar de la cola
                "status": "pending",
                "created_at": date.today().strftime("%Y-%m-%d"),
            })
            occupied.add(date_str)
            added += 1
        current += timedelta(days=interval_days)

    plan = existing_plan + new_entries
    plan.sort(key=lambda e: e.get("date", ""))
    save_schedule_plan(plan)
    logger.info(f"Plan de publicación actualizado: {added} nuevas entradas, {len(plan)} total")
    return plan


def get_todays_scheduled_entry() -> dict | None:
    """Retorna la entrada del plan que debe publicarse hoy (si existe y está pendiente)."""
    today = date.today().strftime("%Y-%m-%d")
    for entry in load_schedule_plan():
        if entry.get("date") == today and entry.get("status") == "pending":
            return entry
    return None


def mark_plan_entry_published(entry_id: str, post_result: dict) -> None:
    """Marca una entrada del plan como publicada."""
    plan = load_schedule_plan()
    for entry in plan:
        if entry.get("id") == entry_id:
            entry["status"] = "published"
            entry["post_id"] = post_result.get("id")
            entry["post_link"] = post_result.get("link")
            entry["published_at"] = now_str()
            break
    save_schedule_plan(plan)


def run_full_pipeline(config: dict | None = None, site_slug: str | None = None,
                      custom_image_path: str | None = None,
                      scheduled_date: str | None = None,
                      plan_entry_id: str | None = None) -> dict:
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

        # 4. Portada: usar imagen personalizada o generar automáticamente
        if custom_image_path and Path(custom_image_path).exists():
            image_path = Path(custom_image_path)
            logger.info(f"Usando portada personalizada: {image_path.name}")
        else:
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

        # 6. Publicar en WordPress (con Elementor + fecha programada si aplica)
        publisher = WordPressPublisher(cfg, site_slug)
        post_result = publisher.publish(
            article=article,
            image_path=image_path,
            status=publish_status,
            schema_html=schema_html,
            scheduled_date=scheduled_date,
        )
        result.update(post_result)
        result["status"] = "success"

        # 7. Configurar RankMath
        rankmath = RankMathController(cfg, site_slug)
        rankmath.configure_post(post_result["id"], article)

        # 8. Marcar entrada del plan como publicada (si viene del scheduler automático)
        if plan_entry_id:
            mark_plan_entry_published(plan_entry_id, post_result)

        # 9. Guardar en historial
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
        logger.info(f"Scheduler: comprobando plan de publicación — {now_str()}")
        # Primero comprobar si hay una entrada programada para hoy
        entry = get_todays_scheduled_entry()
        if entry:
            keyword = entry.get("keyword")  # puede ser None (auto-selección)
            logger.info(f"Scheduler: publicando entrada del plan — {entry['date']} | keyword: {keyword or 'auto'}")
            if keyword:
                from .utils import load_json as _lj, save_json as _sj
                q = _lj("keywords.json")
                if not isinstance(q, list):
                    q = []
                q.insert(0, keyword)
                _sj("keywords.json", q)
            run_full_pipeline(self.config, self.site_slug, plan_entry_id=entry["id"])
        else:
            # Sin entrada en el plan para hoy: usar el intervalo regular
            logger.info(f"Scheduler: pipeline regular (sin entrada en plan) — {now_str()}")
            run_full_pipeline(self.config, self.site_slug)

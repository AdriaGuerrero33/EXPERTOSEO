"""
Optimizador y validador SEO de artículos antes de publicar.
"""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .article_generator import ArticleData
from .utils import load_config, logger


@dataclass
class SEOReport:
    """Resultado del análisis SEO de un artículo."""
    score: int                    # 0-100
    passed: bool                  # True si supera el score mínimo
    checks: list[dict]            # Lista de checks con status y mensaje
    suggestions: list[str]        # Sugerencias de mejora
    word_count: int
    keyword_density: float
    h1_count: int
    h2_count: int


class SEOOptimizer:
    """Valida y optimiza artículos antes de publicarlos."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.seo_config = self.config.get("seo", {})
        self.min_score = self.seo_config.get("min_score", 70)
        self.min_words = self.seo_config.get("min_words", 1500)
        self.kw_min = self.seo_config.get("keyword_density_min", 0.8)
        self.kw_max = self.seo_config.get("keyword_density_max", 2.0)

    def analyze(self, article: ArticleData) -> SEOReport:
        """
        Analiza el artículo y devuelve un SEOReport con score y sugerencias.
        """
        html = article.article_html
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(separator=" ")
        words = text.split()
        word_count = len(words)

        keyword = article.focus_keyword.lower()
        keyword_count = text.lower().count(keyword)
        keyword_density = (keyword_count / word_count * 100) if word_count > 0 else 0

        h1_tags = soup.find_all("h1")
        h2_tags = soup.find_all("h2")
        h3_tags = soup.find_all("h3")
        img_tags = soup.find_all("img")
        links = soup.find_all("a")

        checks = []
        suggestions = []
        total_points = 0
        max_points = 0

        def add_check(name: str, passed: bool, weight: int, detail: str, suggestion: str = ""):
            nonlocal total_points, max_points
            max_points += weight
            if passed:
                total_points += weight
            checks.append({"name": name, "passed": passed, "weight": weight, "detail": detail})
            if not passed and suggestion:
                suggestions.append(suggestion)

        # 1. Longitud del artículo (15 pts)
        add_check(
            "Longitud del artículo",
            word_count >= self.min_words,
            15,
            f"{word_count} palabras (mínimo {self.min_words})",
            f"Añade más contenido. Actualmente {word_count} palabras, mínimo {self.min_words}.",
        )

        # 2. Keyword en H1 (15 pts)
        h1_has_kw = any(keyword in h.get_text().lower() for h in h1_tags) if h1_tags else False
        add_check(
            "Keyword en H1",
            h1_has_kw,
            15,
            f"H1 encontrados: {len(h1_tags)}",
            "Incluye la keyword exacta en el título H1.",
        )

        # 3. Solo un H1 (5 pts)
        add_check(
            "Un único H1",
            len(h1_tags) == 1,
            5,
            f"{len(h1_tags)} etiquetas H1 encontradas",
            "El artículo debe tener exactamente un H1.",
        )

        # 4. Al menos 3 H2 (10 pts)
        add_check(
            "Estructura H2 adecuada",
            len(h2_tags) >= 3,
            10,
            f"{len(h2_tags)} etiquetas H2 encontradas",
            "Añade al menos 3 secciones H2 para mejorar la estructura.",
        )

        # 5. Keyword en primer párrafo (10 pts)
        first_para = soup.find("p")
        kw_in_intro = keyword in first_para.get_text().lower() if first_para else False
        add_check(
            "Keyword en introducción",
            kw_in_intro,
            10,
            "Keyword en primer párrafo",
            "Incluye la keyword en el primer párrafo del artículo.",
        )

        # 6. Densidad de keyword (10 pts)
        density_ok = self.kw_min <= keyword_density <= self.kw_max
        add_check(
            "Densidad de keyword",
            density_ok,
            10,
            f"{keyword_density:.2f}% (rango: {self.kw_min}-{self.kw_max}%)",
            f"Ajusta la densidad de keyword. Actual: {keyword_density:.2f}%, objetivo: {self.kw_min}-{self.kw_max}%.",
        )

        # 7. Meta título optimizado (10 pts)
        meta_title_ok = (
            len(article.seo_title) <= 60
            and keyword in article.seo_title.lower()
        )
        add_check(
            "Meta título",
            meta_title_ok,
            10,
            f"'{article.seo_title}' ({len(article.seo_title)} chars)",
            "El meta título debe incluir la keyword y tener máx 60 caracteres.",
        )

        # 8. Meta descripción optimizada (10 pts)
        meta_desc_ok = (
            len(article.meta_description) >= 120
            and len(article.meta_description) <= 155
            and keyword in article.meta_description.lower()
        )
        add_check(
            "Meta descripción",
            meta_desc_ok,
            10,
            f"{len(article.meta_description)} chars",
            "La meta descripción debe tener 120-155 chars e incluir la keyword.",
        )

        # 9. Imágenes con alt text (5 pts)
        imgs_with_alt = sum(1 for img in img_tags if img.get("alt"))
        imgs_alt_ok = (len(img_tags) == 0) or (imgs_with_alt == len(img_tags))
        add_check(
            "Alt text en imágenes",
            imgs_alt_ok,
            5,
            f"{imgs_with_alt}/{len(img_tags)} imágenes con alt",
            "Todas las imágenes deben tener atributo alt descriptivo.",
        )

        # 10. FAQ section (5 pts)
        has_faq = len(article.faq_items) >= 3
        add_check(
            "Sección FAQ",
            has_faq,
            5,
            f"{len(article.faq_items)} preguntas FAQ",
            "Añade al menos 3 preguntas FAQ para mejorar los featured snippets.",
        )

        # 11. Links internos (5 pts)
        add_check(
            "Links sugeridos",
            len(article.suggested_internal_links) > 0,
            5,
            f"{len(article.suggested_internal_links)} links internos sugeridos",
            "Añade links internos a otros artículos relevantes del sitio.",
        )

        score = int((total_points / max_points) * 100) if max_points > 0 else 0
        passed = score >= self.min_score

        if passed:
            logger.info(f"SEO Score: {score}/100 - APROBADO")
        else:
            logger.warning(f"SEO Score: {score}/100 - NO SUPERA EL MÍNIMO ({self.min_score})")

        return SEOReport(
            score=score,
            passed=passed,
            checks=checks,
            suggestions=suggestions,
            word_count=word_count,
            keyword_density=keyword_density,
            h1_count=len(h1_tags),
            h2_count=len(h2_tags),
        )

    def print_report(self, report: SEOReport) -> None:
        """Imprime el reporte SEO con Rich."""
        from rich.table import Table
        from rich.console import Console
        from rich import box

        con = Console()
        color = "green" if report.passed else "red"

        con.print(f"\n[bold]SEO Score: [{color}]{report.score}/100[/{color}][/bold]")
        con.print(f"Palabras: {report.word_count} | Densidad keyword: {report.keyword_density:.2f}%\n")

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold blue")
        table.add_column("Check", style="white")
        table.add_column("Estado", justify="center")
        table.add_column("Detalle", style="dim")

        for check in report.checks:
            status = "[green]✓[/green]" if check["passed"] else "[red]✗[/red]"
            table.add_row(check["name"], status, check["detail"])

        con.print(table)

        if report.suggestions:
            con.print("\n[bold yellow]Sugerencias de mejora:[/bold yellow]")
            for i, s in enumerate(report.suggestions, 1):
                con.print(f"  {i}. {s}")

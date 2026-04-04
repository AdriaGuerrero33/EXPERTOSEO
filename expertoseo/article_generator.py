"""
Generador de artículos SEO completos usando Claude API.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from .utils import load_config, load_template, require_env, logger, truncate


@dataclass
class ArticleData:
    """Resultado de un artículo generado."""
    keyword: str
    seo_title: str
    meta_description: str
    slug: str
    focus_keyword: str
    secondary_keywords: list[str]
    article_html: str
    faq_items: list[dict]
    image_prompt: str
    suggested_internal_links: list[str]
    word_count_estimate: int
    tags: list[str]
    raw_response: dict = field(default_factory=dict)


class ArticleGenerator:
    """Genera artículos SEO optimizados con Claude."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.client = anthropic.Anthropic(api_key=require_env("ANTHROPIC_API_KEY"))
        self.ai_config = self.config.get("ai", {})
        self.seo_config = self.config.get("seo", {})
        self.model = self.ai_config.get("article_model", "claude-sonnet-4-6")
        self.max_tokens = self.ai_config.get("max_tokens_article", 8000)

    def generate(
        self,
        keyword: str,
        niche: str = "",
        competitors_summary: str = "",
        trends_summary: str = "",
        current_position: str = "No disponible",
    ) -> ArticleData:
        """
        Genera un artículo SEO completo para la keyword dada.

        Args:
            keyword: Keyword objetivo del artículo.
            niche: Nicho del sitio web.
            competitors_summary: Resumen de lo que publica la competencia.
            trends_summary: Tendencias actuales relacionadas.
            current_position: Posición actual en GSC (si existe).

        Returns:
            ArticleData con todo el contenido generado.
        """
        logger.info(f"Generando artículo para keyword: '{keyword}'")

        template = load_template("article_prompt.md")
        min_words = self.seo_config.get("min_words", 1500)
        max_words = self.seo_config.get("max_words", 2500)

        prompt = template.format(
            keyword=keyword,
            niche=niche or self.config.get("keywords", {}).get("niche", "general"),
            min_words=min_words,
            max_words=max_words,
            competitors_summary=competitors_summary or "No analizado",
            trends_summary=trends_summary or "No disponible",
            current_position=current_position,
        )

        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text
        data = self._parse_response(response_text, keyword)
        logger.info(
            f"Artículo generado: '{data.seo_title}' (~{data.word_count_estimate} palabras)"
        )
        return data

    def _parse_response(self, response_text: str, keyword: str) -> ArticleData:
        """Extrae y valida el JSON de la respuesta de Claude."""
        # Buscar bloque JSON en la respuesta
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response_text)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Intentar parsear toda la respuesta como JSON
            json_str = response_text.strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Último recurso: buscar el primer { ... } de nivel superior
            brace_match = re.search(r"\{[\s\S]+\}", response_text)
            if not brace_match:
                raise ValueError("No se pudo extraer JSON válido de la respuesta de Claude")
            data = json.loads(brace_match.group(0))

        # Validar y limpiar campos obligatorios
        seo_title = truncate(data.get("seo_title", f"Guía completa: {keyword}"), 60)
        meta_description = truncate(
            data.get("meta_description", f"Aprende todo sobre {keyword}. Guía completa y actualizada."),
            155,
        )

        return ArticleData(
            keyword=keyword,
            seo_title=seo_title,
            meta_description=meta_description,
            slug=data.get("slug", self._keyword_to_slug(keyword)),
            focus_keyword=data.get("focus_keyword", keyword),
            secondary_keywords=data.get("secondary_keywords", []),
            article_html=data.get("article_html", ""),
            faq_items=data.get("faq_items", []),
            image_prompt=data.get("image_prompt", f"Professional blog cover image about {keyword}"),
            suggested_internal_links=data.get("suggested_internal_links", []),
            word_count_estimate=data.get("word_count_estimate", 0),
            tags=data.get("tags", [keyword]),
            raw_response=data,
        )

    @staticmethod
    def _keyword_to_slug(keyword: str) -> str:
        """Convierte una keyword a slug URL."""
        try:
            from slugify import slugify
            return slugify(keyword, separator="-")
        except ImportError:
            slug = keyword.lower().strip()
            slug = re.sub(r"[áàäâ]", "a", slug)
            slug = re.sub(r"[éèëê]", "e", slug)
            slug = re.sub(r"[íìïî]", "i", slug)
            slug = re.sub(r"[óòöô]", "o", slug)
            slug = re.sub(r"[úùüû]", "u", slug)
            slug = re.sub(r"[ñ]", "n", slug)
            slug = re.sub(r"[^a-z0-9\s-]", "", slug)
            slug = re.sub(r"[\s]+", "-", slug)
            return slug.strip("-")

    def generate_faq_schema(self, faq_items: list[dict]) -> str:
        """Genera el schema JSON-LD de FAQPage."""
        if not faq_items:
            return ""
        questions = [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": item["answer"],
                },
            }
            for item in faq_items
        ]
        schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": questions,
        }
        return f'<script type="application/ld+json">\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n</script>'

    def generate_article_schema(
        self,
        article: ArticleData,
        site_url: str,
        author_name: str = "EXPERTOSEO",
        publish_date: Optional[str] = None,
    ) -> str:
        """Genera el schema JSON-LD de Article."""
        from datetime import datetime
        pub_date = publish_date or datetime.now().isoformat()
        schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": article.seo_title,
            "description": article.meta_description,
            "keywords": ", ".join([article.focus_keyword] + article.secondary_keywords),
            "author": {"@type": "Person", "name": author_name},
            "publisher": {
                "@type": "Organization",
                "name": author_name,
                "url": site_url,
            },
            "datePublished": pub_date,
            "dateModified": pub_date,
            "url": f"{site_url.rstrip('/')}/{article.slug}/",
        }
        return f'<script type="application/ld+json">\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n</script>'

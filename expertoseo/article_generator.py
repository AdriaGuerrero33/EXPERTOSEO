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
        max_retries: int = 2,
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

        # Usar reemplazos manuales para evitar que el JSON del template
        # sea interpretado como placeholders de str.format()
        replacements = {
            "{keyword}": keyword,
            "{niche}": niche or self.config.get("keywords", {}).get("niche", "general"),
            "{min_words}": str(min_words),
            "{max_words}": str(max_words),
            "{competitors_summary}": competitors_summary or "No analizado",
            "{trends_summary}": trends_summary or "No disponible",
            "{current_position}": current_position,
        }
        prompt = template
        for placeholder, value in replacements.items():
            prompt = prompt.replace(placeholder, str(value))

        last_error = None
        for attempt in range(1, max_retries + 2):
            try:
                # En reintentos, añadir instrucción explícita de responder solo JSON
                retry_note = "" if attempt == 1 else (
                    "\n\n⚠️ IMPORTANTE: Responde ÚNICAMENTE con el bloque ```json ... ```. "
                    "Nada más. Ni texto previo ni explicaciones."
                )
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[{"role": "user", "content": prompt + retry_note}],
                )
                response_text = message.content[0].text
                data = self._parse_response(response_text, keyword)
                logger.info(
                    f"Artículo generado: '{data.seo_title}' (~{data.word_count_estimate} palabras)"
                )
                return data
            except (ValueError, json.JSONDecodeError) as e:
                last_error = e
                logger.warning(f"Intento {attempt} fallido al parsear JSON: {e}")

        raise ValueError(
            f"Claude no devolvió JSON válido tras {max_retries + 1} intentos. "
            f"Último error: {last_error}. Prueba con otra keyword."
        )

    def _parse_response(self, response_text: str, keyword: str) -> ArticleData:
        """Extrae y valida el JSON de la respuesta de Claude."""
        # Si Claude rechazó la keyword (respuesta muy corta o sin JSON)
        if len(response_text.strip()) < 100 and "{" not in response_text:
            raise ValueError(
                f"Claude no generó contenido para esta keyword. "
                f"Respuesta: {response_text[:200]}"
            )

        # 1. Bloque ```json ... ```
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response_text)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 2. Bloque ``` ... ``` genérico
            code_match = re.search(r"```\s*([\s\S]*?)\s*```", response_text)
            json_str = code_match.group(1) if code_match else response_text.strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # 3. Buscar el objeto JSON más grande en la respuesta
            brace_match = re.search(r"\{[\s\S]+\}", response_text)
            if not brace_match:
                raise ValueError(
                    "Claude no devolvió JSON. Puede que la keyword sea inapropiada o "
                    "que haya un problema con el template."
                )
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

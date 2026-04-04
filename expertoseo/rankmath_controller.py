"""
Control de RankMath SEO plugin via WordPress REST API.
"""

import requests

from .article_generator import ArticleData
from .utils import load_config, get_site_config, logger


class RankMathController:
    """
    Controla los metadatos SEO de RankMath via WordPress REST API.

    RankMath almacena sus metadatos como post meta en WordPress.
    Los campos se actualizan via el endpoint estándar de posts.
    """

    # Mapeo de campos de ArticleData a meta keys de RankMath
    RANKMATH_META_KEYS = {
        "rank_math_title": "seo_title",
        "rank_math_description": "meta_description",
        "rank_math_focus_keyword": "focus_keyword",
        "rank_math_og_title": "seo_title",
        "rank_math_og_description": "meta_description",
        "rank_math_twitter_title": "seo_title",
        "rank_math_twitter_description": "meta_description",
        "rank_math_schema_Article": None,  # Se activa manualmente
    }

    def __init__(self, config: dict | None = None, site_slug: str | None = None):
        self.config = config or load_config()
        self.site = get_site_config(self.config, site_slug)
        self.base_url = self.site["url"].rstrip("/")
        self.api_base = f"{self.base_url}/wp-json/wp/v2"
        self.session = requests.Session()
        self.session.auth = self._make_auth()
        self.session.headers.update({"User-Agent": "EXPERTOSEO/1.0"})

    def _make_auth(self):
        creds = self.site["wp_app_password"]
        if ":" not in creds:
            return (self.site["wp_user"].strip(), creds.strip())
        user, password = creds.split(":", 1)
        return (user.strip(), password.strip())

    def configure_post(self, post_id: int, article: ArticleData) -> bool:
        """
        Configura todos los metadatos SEO de RankMath para un post.

        Args:
            post_id: ID del post en WordPress.
            article: ArticleData con los datos SEO.

        Returns:
            True si se configuró correctamente.
        """
        logger.info(f"Configurando RankMath para post ID={post_id}")

        meta = {
            "rank_math_title": article.seo_title,
            "rank_math_description": article.meta_description,
            "rank_math_focus_keyword": article.focus_keyword,
            "rank_math_og_title": article.seo_title,
            "rank_math_og_description": article.meta_description,
            "rank_math_twitter_title": article.seo_title,
            "rank_math_twitter_description": article.meta_description,
            "rank_math_robots": ["index", "follow"],
        }

        # Activar schema Article en RankMath
        schema_data = self._build_article_schema(article)
        if schema_data:
            meta["rank_math_rich_snippet"] = "article"
            meta["rank_math_snippet_article_type"] = "BlogPosting"

        resp = self.session.post(
            f"{self.api_base}/posts/{post_id}",
            json={"meta": meta},
            timeout=15,
        )

        if resp.status_code in (200, 201):
            logger.info(f"RankMath configurado correctamente para post {post_id}")
            return True
        else:
            logger.warning(
                f"Advertencia configurando RankMath: {resp.status_code} - {resp.text[:300]}"
            )
            # No es fatal: los metadatos básicos ya se enviaron al publicar
            return False

    def _build_article_schema(self, article: ArticleData) -> dict:
        """Construye datos de schema para RankMath."""
        return {
            "type": "BlogPosting",
            "name": article.seo_title,
            "description": article.meta_description,
            "keywords": ", ".join([article.focus_keyword] + article.secondary_keywords[:3]),
        }

    def get_post_score(self, post_id: int) -> int | None:
        """
        Obtiene el score SEO de RankMath para un post.

        Returns:
            Score de 0-100 o None si no está disponible.
        """
        try:
            resp = self.session.get(
                f"{self.api_base}/posts/{post_id}",
                params={"_fields": "meta"},
                timeout=10,
            )
            resp.raise_for_status()
            meta = resp.json().get("meta", {})
            score = meta.get("rank_math_seo_score")
            if score is not None:
                return int(score)
        except Exception as e:
            logger.debug(f"No se pudo obtener score de RankMath: {e}")
        return None

    def check_rankmath_available(self) -> bool:
        """Verifica si RankMath está disponible via REST API."""
        try:
            resp = self.session.get(
                f"{self.base_url}/wp-json/rankmath/v1/getHead",
                params={"url": self.base_url},
                timeout=10,
            )
            available = resp.status_code == 200
            if available:
                logger.info("RankMath REST API disponible")
            else:
                logger.warning("RankMath REST API no responde (plugin desactivado o versión antigua)")
            return available
        except Exception:
            return False

    def update_focus_keyword(self, post_id: int, keyword: str) -> bool:
        """Actualiza solo la focus keyword de un post."""
        resp = self.session.post(
            f"{self.api_base}/posts/{post_id}",
            json={"meta": {"rank_math_focus_keyword": keyword}},
            timeout=10,
        )
        return resp.status_code in (200, 201)

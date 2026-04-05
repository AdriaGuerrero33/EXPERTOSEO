"""
Publicador de artículos en WordPress via REST API.
Soporta dos métodos de autenticación:
  1. Token secreto via header X-Expertoseo-Token (bypass nginx Basic Auth)
  2. Application Password via Basic Auth (fallback)
"""

import os
import base64
import mimetypes
from pathlib import Path
from datetime import datetime

import requests

from .article_generator import ArticleData
from .utils import load_config, get_site_config, logger


class WordPressPublisher:
    """Publica artículos en WordPress usando la REST API."""

    def __init__(self, config: dict | None = None, site_slug: str | None = None):
        self.config = config or load_config()
        self.site = get_site_config(self.config, site_slug)
        self._validate_site_config()
        self.base_url = self.site["url"].rstrip("/")
        self.api_base = f"{self.base_url}/wp-json/wp/v2"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "EXPERTOSEO/1.0"})
        self._setup_auth()

    def _validate_site_config(self) -> None:
        if not self.site.get("url"):
            raise ValueError(f"Config del sitio '{self.site.get('name')}' incompleta: falta 'url'")
        # Con token secreto no se necesita wp_app_password
        secret_token = os.getenv("EXPERTOSEO_SECRET_TOKEN", "")
        if not secret_token and not self.site.get("wp_app_password"):
            raise ValueError(
                "Falta autenticación WordPress: configura EXPERTOSEO_SECRET_TOKEN "
                "(recomendado) o WP_APP_PASSWORD_SITE1 en Railway Variables"
            )

    def _setup_auth(self) -> None:
        """Configura autenticación: token secreto o Basic Auth."""
        secret_token = os.getenv("EXPERTOSEO_SECRET_TOKEN", "")
        if secret_token:
            # Método 1: token secreto en header personalizado (bypasa nginx)
            self.session.headers.update({"X-Expertoseo-Token": secret_token})
            logger.info("WordPress auth: usando token secreto (X-Expertoseo-Token)")
        elif self.site.get("wp_app_password"):
            # Método 2: Application Password con Basic Auth
            creds = self.site["wp_app_password"]
            if ":" not in creds:
                user, password = self.site.get("wp_user", ""), creds
            else:
                user, password = creds.split(":", 1)
            self.session.auth = (user.strip(), password.strip())
            logger.info(f"WordPress auth: Basic Auth como '{user.strip()}'")
        else:
            raise ValueError("Sin método de autenticación WordPress configurado")

    def upload_image(self, image_path: Path, alt_text: str = "", caption: str = "") -> int:
        """
        Sube una imagen a la Media Library de WordPress.

        Returns:
            ID del attachment en WordPress.
        """
        mime_type, _ = mimetypes.guess_type(str(image_path))
        if not mime_type:
            mime_type = "image/webp"

        with open(image_path, "rb") as f:
            img_data = f.read()

        filename = image_path.name
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": mime_type,
        }

        resp = self.session.post(
            f"{self.api_base}/media",
            headers=headers,
            data=img_data,
            timeout=60,
        )
        resp.raise_for_status()
        media = resp.json()
        media_id = media["id"]

        # Actualizar alt text
        if alt_text:
            self.session.post(
                f"{self.api_base}/media/{media_id}",
                json={"alt_text": alt_text, "caption": caption},
                timeout=15,
            )

        logger.info(f"Imagen subida a WordPress: ID={media_id}, '{filename}'")
        return media_id

    def get_or_create_category(self, name: str) -> int:
        """Obtiene el ID de una categoría o la crea si no existe."""
        resp = self.session.get(
            f"{self.api_base}/categories",
            params={"search": name, "per_page": 5},
            timeout=10,
        )
        resp.raise_for_status()
        cats = resp.json()
        for cat in cats:
            if cat["name"].lower() == name.lower():
                return cat["id"]

        # Crear la categoría
        resp = self.session.post(
            f"{self.api_base}/categories",
            json={"name": name},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def get_or_create_tags(self, tag_names: list[str]) -> list[int]:
        """Obtiene o crea tags y retorna sus IDs."""
        tag_ids = []
        for name in tag_names:
            resp = self.session.get(
                f"{self.api_base}/tags",
                params={"search": name, "per_page": 5},
                timeout=10,
            )
            resp.raise_for_status()
            tags = resp.json()
            found = next((t for t in tags if t["name"].lower() == name.lower()), None)
            if found:
                tag_ids.append(found["id"])
            else:
                resp2 = self.session.post(
                    f"{self.api_base}/tags",
                    json={"name": name},
                    timeout=10,
                )
                if resp2.status_code in (200, 201):
                    tag_ids.append(resp2.json()["id"])
        return tag_ids

    def publish(
        self,
        article: ArticleData,
        image_path: Path | None = None,
        status: str = "publish",
        schema_html: str = "",
    ) -> dict:
        """
        Publica un artículo completo en WordPress.

        Args:
            article: ArticleData con el contenido generado.
            image_path: Path a la imagen de portada (opcional).
            status: "publish", "draft" o "pending".
            schema_html: Schema JSON-LD adicional (Article + FAQ).

        Returns:
            Dict con id, link y otros datos del post publicado.
        """
        logger.info(f"Publicando en WordPress: '{article.seo_title}' [{status}]")

        # 1. Subir imagen de portada
        featured_media_id = None
        if image_path and image_path.exists():
            featured_media_id = self.upload_image(
                image_path,
                alt_text=article.focus_keyword,
                caption=article.seo_title,
            )

        # 2. Obtener/crear categoría
        default_cat = self.site.get("default_category", "Blog")
        category_id = self.get_or_create_category(default_cat)

        # 3. Obtener/crear tags
        tag_ids = self.get_or_create_tags(article.tags[:5])

        # 4. Preparar contenido final con schema
        full_content = article.article_html
        if schema_html:
            full_content = schema_html + "\n" + full_content

        # 5. Crear el post
        post_data: dict = {
            "title": article.seo_title,
            "content": full_content,
            "slug": article.slug,
            "status": status,
            "categories": [category_id],
            "tags": tag_ids,
            "meta": {
                "rank_math_title": article.seo_title,
                "rank_math_description": article.meta_description,
                "rank_math_focus_keyword": article.focus_keyword,
            },
        }
        if featured_media_id:
            post_data["featured_media"] = featured_media_id
        if self.site.get("default_author_id"):
            post_data["author"] = self.site["default_author_id"]

        resp = self.session.post(
            f"{self.api_base}/posts",
            json=post_data,
            timeout=30,
        )
        resp.raise_for_status()
        post = resp.json()

        logger.info(f"Publicado correctamente: {post.get('link')}")
        return {
            "id": post["id"],
            "link": post["link"],
            "slug": post["slug"],
            "status": post["status"],
            "date": post.get("date"),
        }

    def test_connection(self) -> bool:
        """Verifica que las credenciales de WordPress son válidas."""
        try:
            resp = self.session.get(f"{self.api_base}/users/me", timeout=10)
            if resp.status_code == 200:
                user = resp.json()
                logger.info(f"Conexión WordPress OK: {user.get('name')} ({self.base_url})")
                return True
            logger.error(f"Error conexión WordPress: {resp.status_code} - {resp.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"No se pudo conectar a WordPress: {e}")
            return False

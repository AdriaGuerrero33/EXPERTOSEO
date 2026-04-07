"""
Publicador de artículos en WordPress via REST API.
Soporta dos métodos de autenticación:
  1. Token secreto via header X-Expertoseo-Token (bypass nginx Basic Auth)
  2. Application Password via Basic Auth (fallback)
"""

import json as _json
import os
import mimetypes
import uuid
from pathlib import Path
from datetime import datetime

import requests

from .article_generator import ArticleData
from .utils import load_config, get_site_config, logger


def _section(uid_fn, widgets: list, bg_color: str = "", padding: tuple = ("2", "0", "2", "0")) -> dict:
    """Helper para crear una sección Elementor de una columna."""
    settings: dict = {
        "gap": "no",
        "content_width": {"unit": "px", "size": 960, "sizes": {}},
        "padding": {"unit": "em", "top": padding[0], "right": padding[1], "bottom": padding[2], "left": padding[3], "isLinked": False},
    }
    if bg_color:
        settings["background_background"] = "classic"
        settings["background_color"] = bg_color
    return {
        "id": uid_fn(), "elType": "section",
        "settings": settings, "isInner": False,
        "elements": [{"id": uid_fn(), "elType": "column", "settings": {"_column_size": 100}, "elements": widgets}],
    }


def _text_widget(uid_fn, html: str, align: str = "left") -> dict:
    return {"id": uid_fn(), "elType": "widget", "widgetType": "text-editor",
            "settings": {"editor": html, "align": align}, "elements": []}


def _heading_widget(uid_fn, title: str, tag: str = "h2", color: str = "") -> dict:
    s: dict = {"title": title, "header_size": tag}
    if color:
        s["title_color"] = color
    return {"id": uid_fn(), "elType": "widget", "widgetType": "heading", "settings": s, "elements": []}


def _divider_widget(uid_fn) -> dict:
    return {"id": uid_fn(), "elType": "widget", "widgetType": "divider",
            "settings": {"color": "#e0e0e0", "gap": {"unit": "px", "size": 15, "sizes": {}}}, "elements": []}


def _build_elementor_data(article_html: str, intro_html: str = "", faq_items: list | None = None) -> str:
    """
    Genera el JSON de Elementor Page Builder para un artículo.
    Layout rico con secciones: intro destacada → contenido → FAQ (si hay) → separador final.
    Requiere que los meta fields _elementor_data/_elementor_edit_mode estén registrados
    con show_in_rest=true en WordPress (usar el snippet PHP de EXPERTOSEO).
    """
    def uid() -> str:
        return uuid.uuid4().hex[:8]

    import re as _re

    sections = []

    # ── 1. Sección intro (fondo gris muy claro) ───────────────────────────
    # Extraer primer párrafo del HTML para usarlo como intro destacada
    first_p_match = _re.search(r"<p[^>]*>(.*?)</p>", article_html, _re.DOTALL | _re.IGNORECASE)
    if first_p_match:
        intro_text = first_p_match.group(0)
        intro_box = (
            f'<div style="background:#f8f9fa;border-left:4px solid #2271b1;'
            f'padding:18px 22px;border-radius:0 8px 8px 0;font-size:1.05em;'
            f'line-height:1.7;color:#333">{first_p_match.group(1)}</div>'
        )
        sections.append(_section(uid, [_text_widget(uid, intro_box)], padding=("1", "0", "1", "0")))
        sections.append(_section(uid, [_divider_widget(uid)], padding=("0", "0", "0", "0")))

    # ── 2. Sección contenido principal ────────────────────────────────────
    sections.append(_section(uid, [_text_widget(uid, article_html)], padding=("2", "0", "2", "0")))

    # ── 3. Sección FAQ (si hay items, fondo azul muy claro) ───────────────
    if faq_items:
        faq_html_parts = ['<div style="background:#f0f7ff;border-radius:12px;padding:24px 28px;margin-top:8px">',
                          '<h2 style="color:#1e3a5f;margin-bottom:16px">❓ Preguntas Frecuentes</h2>']
        for item in faq_items[:8]:
            q = item.get("question", "") if isinstance(item, dict) else str(item)
            a = item.get("answer", "") if isinstance(item, dict) else ""
            if q:
                faq_html_parts.append(
                    f'<details style="margin-bottom:12px;border:1px solid #cde;border-radius:8px;overflow:hidden">'
                    f'<summary style="padding:12px 16px;background:#e8f3ff;cursor:pointer;font-weight:600;color:#1e3a5f">{q}</summary>'
                    f'<div style="padding:12px 16px;color:#444;line-height:1.6">{a}</div></details>'
                )
        faq_html_parts.append('</div>')
        sections.append(_section(uid, [_text_widget(uid, "".join(faq_html_parts))], padding=("1", "0", "2", "0")))

    return _json.dumps(sections, ensure_ascii=False)


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
        scheduled_date: str | None = None,
    ) -> dict:
        """
        Publica un artículo completo en WordPress con formato Elementor.

        Args:
            article: ArticleData con el contenido generado.
            image_path: Path a la imagen de portada (opcional).
            status: "publish", "draft", "future" o "pending".
            schema_html: Schema JSON-LD adicional (Article + FAQ).
            scheduled_date: ISO 8601 datetime para publicación programada (ej: "2026-04-09T09:00:00").

        Returns:
            Dict con id, link y otros datos del post publicado.
        """
        logger.info(f"Publicando en WordPress (Elementor): '{article.seo_title}' [{status}]")

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

        # 4. Preparar contenido — schema + HTML del artículo
        full_content = article.article_html
        if schema_html:
            full_content = schema_html + "\n" + full_content

        # 5. Generar Elementor JSON para que el post use el builder
        elementor_json = _build_elementor_data(full_content, faq_items=article.faq_items)
        logger.info("Elementor JSON generado para el post")

        # 6. Preparar datos del post
        post_data: dict = {
            "title": article.seo_title,
            "content": full_content,           # también en content por si el tema lo usa
            "slug": article.slug,
            "status": "future" if scheduled_date else status,
            "categories": [category_id],
            "tags": tag_ids,
            "meta": {
                # RankMath SEO
                "rank_math_title": article.seo_title,
                "rank_math_description": article.meta_description,
                "rank_math_focus_keyword": article.focus_keyword,
                # Elementor — activa el page builder en este post
                "_elementor_edit_mode": "builder",
                "_elementor_data": elementor_json,
                "_elementor_version": "3.x",
            },
        }
        if scheduled_date:
            post_data["date"] = scheduled_date        # hora local del servidor WP
        if featured_media_id:
            post_data["featured_media"] = featured_media_id
        if self.site.get("default_author_id"):
            post_data["author"] = self.site["default_author_id"]

        resp = self.session.post(
            f"{self.api_base}/posts",
            json=post_data,
            timeout=30,
        )
        if not resp.ok:
            try:
                err_body = resp.json()
                err_msg = f"HTTP {resp.status_code} — {err_body.get('code','?')}: {err_body.get('message','')}"
            except Exception:
                err_msg = f"HTTP {resp.status_code} — {resp.text[:400]}"
            logger.error(f"Error publicando en WordPress: {err_msg}")
            raise ValueError(err_msg)
        post = resp.json()

        logger.info(f"Post creado (ID={post['id']}): {post.get('link')}")

        # Verificar si Elementor meta se guardó (puede fallar silenciosamente si no está registrado)
        saved_meta = post.get("meta", {})
        if not saved_meta.get("_elementor_edit_mode"):
            logger.warning(
                "⚠️  _elementor_edit_mode NO se guardó en el post. "
                "Instala el snippet PHP de EXPERTOSEO en Code Snippets → 'Registrar Elementor REST API'. "
                "El artículo se publicó igualmente con HTML correcto en post_content."
            )
        else:
            logger.info("✅ Elementor builder activado en el post")

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

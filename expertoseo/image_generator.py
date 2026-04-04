"""
Generador de portadas para artículos usando DALL-E 3 (primario) y Unsplash (fallback).
"""

import os
import io
import requests
from pathlib import Path
from PIL import Image

from .utils import load_config, require_env, logger, DATA_DIR


class ImageGenerator:
    """Genera y optimiza imágenes de portada para artículos."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.img_config = self.config.get("images", {})
        self.provider = self.img_config.get("provider", "dalle")
        self.output_dir = DATA_DIR / "images"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, prompt: str, filename: str) -> Path:
        """
        Genera una imagen de portada y la guarda optimizada.
        Siempre intenta Unsplash como fallback si el proveedor principal falla.
        """
        logger.info(f"Generando portada: provider={self.provider}")

        # Si no hay clave de OpenAI configurada, forzar Unsplash
        import os
        if self.provider == "dalle" and not os.getenv("OPENAI_API_KEY"):
            logger.info("OPENAI_API_KEY no configurada, usando Unsplash")
            self.provider = "unsplash"

        if self.provider == "dalle":
            try:
                return self._generate_dalle(prompt, filename)
            except Exception as e:
                logger.warning(f"DALL-E falló ({e}), usando Unsplash como fallback")
                return self._generate_unsplash(prompt, filename)
        else:
            return self._generate_unsplash(prompt, filename)

    def _generate_dalle(self, prompt: str, filename: str) -> Path:
        """Genera imagen con DALL-E 3."""
        from openai import OpenAI

        client = OpenAI(api_key=require_env("OPENAI_API_KEY"))
        model = self.img_config.get("dalle_model", "dall-e-3")
        quality = self.img_config.get("dalle_quality", "standard")
        size = self.img_config.get("dalle_size", "1792x1024")

        # DALL-E 3 prompt engineering: más detallado y profesional
        enhanced_prompt = (
            f"Professional blog cover image, high quality photography style. "
            f"{prompt}. "
            f"Clean, modern design with space for text overlay. "
            f"No text or letters in the image. Wide format, sharp and vibrant."
        )

        response = client.images.generate(
            model=model,
            prompt=enhanced_prompt,
            size=size,
            quality=quality,
            n=1,
        )

        image_url = response.data[0].url
        img_bytes = requests.get(image_url, timeout=30).content
        return self._save_and_optimize(img_bytes, filename)

    def _generate_unsplash(self, prompt: str, filename: str) -> Path:
        """Busca y descarga foto de Unsplash. Si no hay clave, usa imagen de Picsum."""
        import os
        access_key = os.getenv("UNSPLASH_ACCESS_KEY")

        if access_key:
            query = " ".join(prompt.split()[:5])
            url = "https://api.unsplash.com/photos/random"
            params = {"query": query, "orientation": "landscape", "content_filter": "high"}
            headers = {"Authorization": f"Client-ID {access_key}"}
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                img_url = data["urls"]["regular"]
                img_bytes = requests.get(img_url, timeout=30).content
                logger.info(f"Imagen Unsplash: {data.get('alt_description', 'sin descripción')}")
                return self._save_and_optimize(img_bytes, filename)
            except Exception as e:
                logger.warning(f"Unsplash falló ({e}), usando imagen genérica")

        # Fallback sin ninguna API key: imagen aleatoria de Picsum (libre, sin auth)
        img_bytes = requests.get("https://picsum.photos/1200/630", timeout=15).content
        logger.info("Imagen genérica de Picsum (añade UNSPLASH_ACCESS_KEY para imágenes temáticas)")
        return self._save_and_optimize(img_bytes, filename)

    def _save_and_optimize(self, img_bytes: bytes, filename: str) -> Path:
        """Optimiza la imagen y la guarda en WebP."""
        target_w = self.img_config.get("optimize_width", 1200)
        target_h = self.img_config.get("optimize_height", 630)
        fmt = self.img_config.get("format", "webp").lower()

        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        # Redimensionar manteniendo aspect ratio y rellenando con crop central
        image = self._smart_crop(image, target_w, target_h)

        out_path = self.output_dir / f"{filename}.{fmt}"
        save_kwargs = {"format": fmt.upper(), "optimize": True}
        if fmt == "webp":
            save_kwargs["quality"] = 85
        elif fmt == "jpeg":
            save_kwargs["quality"] = 90

        image.save(out_path, **save_kwargs)
        logger.info(f"Imagen guardada: {out_path} ({image.size[0]}x{image.size[1]})")
        return out_path

    @staticmethod
    def _smart_crop(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Redimensiona y recorta la imagen al tamaño exacto."""
        orig_w, orig_h = image.size
        scale = max(target_w / orig_w, target_h / orig_h)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        image = image.resize((new_w, new_h), Image.LANCZOS)

        # Crop central
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        return image.crop((left, top, left + target_w, top + target_h))

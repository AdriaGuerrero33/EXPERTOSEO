"""
Utilidades comunes para EXPERTOSEO
v1.2 — carga credenciales desde data/credentials.yaml (Railway Volume)
"""

import os
import json
import yaml
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler

# Directorio raíz del proyecto
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
TEMPLATES_DIR = ROOT_DIR / "templates"
CREDENTIALS_DIR = ROOT_DIR / "credentials"

console = Console()


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configura logging con Rich handler."""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )
    return logging.getLogger("expertoseo")


logger = setup_logging()


def load_credentials_file() -> None:
    """
    Carga credenciales desde data/credentials.yaml (montado en Railway Volume).
    Esto evita el bug de Railway donde las variables de usuario no llegan al contenedor.
    Solo sobreescribe variables que NO estén ya definidas en el entorno.
    """
    creds_path = DATA_DIR / "credentials.yaml"
    if not creds_path.exists():
        return
    try:
        with open(creds_path, "r", encoding="utf-8") as f:
            creds = yaml.safe_load(f) or {}
        for key, value in creds.items():
            if value and not os.environ.get(key):
                os.environ[str(key)] = str(value)
        logger.debug(f"Credenciales cargadas desde {creds_path} ({len(creds)} variables)")
    except Exception as e:
        logger.warning(f"No se pudo cargar credentials.yaml: {e}")


def save_credentials_file(creds: dict) -> None:
    """Guarda credenciales en data/credentials.yaml (Railway Volume)."""
    DATA_DIR.mkdir(exist_ok=True)
    creds_path = DATA_DIR / "credentials.yaml"
    # Filtrar valores vacíos para no sobrescribir con nada
    filtered = {k: v for k, v in creds.items() if v and str(v).strip()}
    with open(creds_path, "w", encoding="utf-8") as f:
        yaml.dump(filtered, f, allow_unicode=True, default_flow_style=False)
    # Aplicar al entorno actual inmediatamente
    for key, value in filtered.items():
        os.environ[str(key)] = str(value)


def load_env() -> None:
    """Carga variables de entorno: primero credentials.yaml (Volume), luego .env."""
    # 1. Primero cargar desde el Volume (Railway) — máxima prioridad para bypass del bug
    load_credentials_file()
    # 2. Luego .env local (desarrollo)
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        logger.debug(".env no encontrado. Usando variables de entorno del sistema.")


def load_config() -> dict:
    """Carga y retorna la configuración desde config.yaml."""
    config_path = ROOT_DIR / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"config.yaml no encontrado en {ROOT_DIR}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    # Resolver variables de entorno en username y app_passwords
    for site in config.get("sites", []):
        slug = site.get("slug", "")
        # Username override (WP_USERNAME_SITE1, etc.)
        username_env = os.getenv(f"WP_USERNAME_{slug}")
        if username_env:
            site["wp_user"] = username_env
        # App password (WP_APP_PASSWORD_SITE1, etc.)
        env_val = os.getenv(f"WP_APP_PASSWORD_{slug}")
        if env_val:
            site["wp_app_password"] = env_val
    return config


def get_site_config(config: dict, slug: str | None = None) -> dict:
    """Retorna la config del sitio activo o el indicado por slug."""
    sites = config.get("sites", [])
    if not sites:
        raise ValueError("No hay sitios configurados en config.yaml")
    if slug:
        for site in sites:
            if site.get("slug") == slug:
                return site
        raise ValueError(f"Sitio '{slug}' no encontrado en config.yaml")
    # Usar sitio activo del schedule
    active_slug = config.get("schedule", {}).get("active_site")
    if active_slug:
        for site in sites:
            if site.get("slug") == active_slug:
                return site
    return sites[0]


# Archivos JSON que contienen listas (no dicts)
_LIST_JSON_FILES = {"published.json", "keywords.json", "schedule_plan.json"}


def load_json(filename: str) -> dict | list:
    """Carga un archivo JSON de data/."""
    path = DATA_DIR / filename
    if not path.exists():
        return [] if filename in _LIST_JSON_FILES else {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename: str, data: dict | list) -> None:
    """Guarda datos en data/<filename>."""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_template(name: str) -> str:
    """Carga un template desde templates/."""
    path = TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Template '{name}' no encontrado")
    return path.read_text(encoding="utf-8")


def now_str() -> str:
    """Retorna timestamp actual como string ISO."""
    return datetime.now().isoformat()


def require_env(key: str) -> str:
    """Obtiene variable de entorno o lanza error descriptivo."""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Variable de entorno '{key}' no configurada. "
            f"Añádela al archivo .env (ver .env.example)"
        )
    return val


def truncate(text: str, max_len: int) -> str:
    """Trunca texto a max_len caracteres, añadiendo '...' si es necesario."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."

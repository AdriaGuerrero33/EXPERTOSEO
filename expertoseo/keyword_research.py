"""
Investigación de keywords: Google Search Console, Google Trends y análisis de competencia.
"""

import os
import json
from datetime import date, timedelta
from typing import Optional

from .utils import load_config, load_json, save_json, logger


class KeywordResearch:
    """
    Combina múltiples fuentes para encontrar las mejores keywords a trabajar.

    Fuentes:
    - Keywords manuales del config.yaml
    - Google Search Console (oportunidades posición 4-20)
    - Google Trends (tendencias del nicho)
    - Análisis básico de competencia (SerpAPI)
    """

    def __init__(self, config: dict | None = None, site_slug: str | None = None):
        self.config = config or load_config()
        from .utils import get_site_config
        self.site = get_site_config(self.config, site_slug)
        self.kw_config = self.config.get("keywords", {})
        self.seo_config = self.config.get("seo", {})

    # ----------------------------------------------------------------
    # Fuente 1: Keywords manuales
    # ----------------------------------------------------------------

    def get_manual_keywords(self) -> list[str]:
        """Retorna las keywords manuales del config.yaml."""
        return self.kw_config.get("manual", [])

    # ----------------------------------------------------------------
    # Fuente 2: Google Search Console
    # ----------------------------------------------------------------

    def get_gsc_opportunities(self, days: int = 90) -> list[dict]:
        """
        Obtiene keywords con posición 4-20 en GSC (oportunidades quick win).

        Returns:
            Lista de dicts con: keyword, position, clicks, impressions, ctr
        """
        try:
            service = self._get_gsc_service()
            if not service:
                return []

            site_url = self.site.get("gsc_property", self.site.get("url"))
            end_date = date.today()
            start_date = end_date - timedelta(days=days)

            request_body = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "dimensions": ["query"],
                "dimensionFilterGroups": [
                    {
                        "filters": [
                            {
                                "dimension": "query",
                                "operator": "notContains",
                                "expression": "site:",
                            }
                        ]
                    }
                ],
                "rowLimit": 500,
            }

            response = (
                service.searchanalytics()
                .query(siteUrl=site_url, body=request_body)
                .execute()
            )

            rows = response.get("rows", [])
            opportunities = []
            for row in rows:
                pos = row.get("position", 99)
                if 3 < pos <= 20:  # Posición 4-20 = oportunidades
                    opportunities.append(
                        {
                            "keyword": row["keys"][0],
                            "position": round(pos, 1),
                            "clicks": row.get("clicks", 0),
                            "impressions": row.get("impressions", 0),
                            "ctr": round(row.get("ctr", 0) * 100, 2),
                        }
                    )

            # Ordenar por impresiones descendente
            opportunities.sort(key=lambda x: x["impressions"], reverse=True)
            logger.info(f"GSC: {len(opportunities)} oportunidades encontradas")
            return opportunities[:20]

        except Exception as e:
            logger.warning(f"Error obteniendo datos GSC: {e}")
            return []

    def _get_gsc_service(self):
        """Inicializa y retorna el servicio de Google Search Console."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "credentials/google_service_account.json")
            if not os.path.exists(creds_path):
                logger.warning(f"Credenciales GSC no encontradas: {creds_path}")
                return None

            scopes = ["https://www.googleapis.com/auth/webmasters.readonly"]
            credentials = service_account.Credentials.from_service_account_file(
                creds_path, scopes=scopes
            )
            return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
        except Exception as e:
            logger.warning(f"No se pudo inicializar GSC: {e}")
            return None

    # ----------------------------------------------------------------
    # Fuente 3: Google Trends
    # ----------------------------------------------------------------

    def get_trending_keywords(self, timeframe: str = "today 1-m") -> list[str]:
        """
        Obtiene keywords trending relacionadas con el nicho.

        Args:
            timeframe: Período de tiempo (ej: "today 1-m", "today 3-m", "today 7-d")

        Returns:
            Lista de keywords trending.
        """
        try:
            from pytrends.request import TrendReq

            niche = self.kw_config.get("niche", "marketing digital")
            country = self.seo_config.get("country", "ES")
            language = self.seo_config.get("language", "es")

            pytrends = TrendReq(hl=f"{language}-{country.upper()}", tz=60)

            # Buscar keywords relacionadas con el nicho
            seed_keywords = [niche] + self.get_manual_keywords()[:2]
            pytrends.build_payload(
                seed_keywords[:5],  # Máximo 5 keywords a la vez
                cat=0,
                timeframe=timeframe,
                geo=country.upper(),
            )

            related_queries = pytrends.related_queries()
            trending = []

            for kw, data in related_queries.items():
                if data and data.get("rising") is not None:
                    rising_df = data["rising"]
                    if not rising_df.empty:
                        trending.extend(rising_df["query"].tolist()[:5])

            logger.info(f"Google Trends: {len(trending)} keywords trending")
            return list(set(trending))[:10]

        except Exception as e:
            logger.warning(f"Error obteniendo Google Trends: {e}")
            return []

    # ----------------------------------------------------------------
    # Fuente 4: Análisis de competencia
    # ----------------------------------------------------------------

    def analyze_competitors(self, max_results: int = 10) -> list[dict]:
        """
        Analiza los artículos más recientes de la competencia.

        Returns:
            Lista de dicts con: title, url, keyword (estimada)
        """
        competitors = self.site.get("competitors", [])
        if not competitors:
            return []

        serpapi_key = os.getenv("SERPAPI_KEY")
        if not serpapi_key:
            logger.debug("SERPAPI_KEY no configurada, saltando análisis de competencia")
            return []

        results = []
        for competitor_url in competitors[:3]:
            try:
                domain = competitor_url.replace("https://", "").replace("http://", "").split("/")[0]
                resp = __import__("requests").get(
                    "https://serpapi.com/search",
                    params={
                        "api_key": serpapi_key,
                        "engine": "google",
                        "q": f"site:{domain}",
                        "num": 10,
                        "hl": self.seo_config.get("language", "es"),
                        "gl": self.seo_config.get("country", "es"),
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("organic_results", [])[:max_results]:
                    results.append(
                        {
                            "title": item.get("title", ""),
                            "url": item.get("link", ""),
                            "snippet": item.get("snippet", ""),
                            "competitor": domain,
                        }
                    )
            except Exception as e:
                logger.debug(f"Error analizando competidor {competitor_url}: {e}")

        logger.info(f"Competencia: {len(results)} artículos analizados")
        return results

    # ----------------------------------------------------------------
    # Método principal: selecciona la mejor keyword
    # ----------------------------------------------------------------

    def get_next_keyword(self) -> tuple[str, dict]:
        """
        Selecciona la siguiente keyword a trabajar usando todas las fuentes.

        Prioridad:
        1. Keywords manuales de la cola (data/keywords.json)
        2. Oportunidades GSC (posición 4-20)
        3. Keywords trending de Google Trends
        4. Keywords manuales del config.yaml

        Returns:
            Tuple (keyword, contexto) donde contexto incluye datos de apoyo.
        """
        # Cargar cola de keywords
        queue = load_json("keywords.json")
        if isinstance(queue, list) and queue:
            keyword = queue.pop(0)
            save_json("keywords.json", queue)
            logger.info(f"Keyword de la cola: '{keyword}'")
            return keyword, {"source": "queue"}

        # Intentar GSC
        gsc_opps = self.get_gsc_opportunities()
        if gsc_opps:
            best = gsc_opps[0]
            logger.info(f"Keyword de GSC: '{best['keyword']}' (pos {best['position']})")
            return best["keyword"], {"source": "gsc", "gsc_data": best}

        # Intentar Trends
        trending = self.get_trending_keywords()
        if trending:
            logger.info(f"Keyword de Trends: '{trending[0]}'")
            return trending[0], {"source": "trends"}

        # Fallback: keywords manuales del config
        manual = self.get_manual_keywords()
        if manual:
            # Rotar: usar la primera y moverla al final
            keyword = manual[0]
            logger.info(f"Keyword manual del config: '{keyword}'")
            return keyword, {"source": "manual"}

        raise ValueError("No hay keywords disponibles. Añade keywords en config.yaml o data/keywords.json")

    def get_context_summary(self) -> dict:
        """Retorna un resumen de contexto para la generación del artículo."""
        competitors_data = self.analyze_competitors(max_results=5)
        trends = self.get_trending_keywords()

        competitors_summary = ""
        if competitors_data:
            titles = [f"- {d['title']}" for d in competitors_data[:5]]
            competitors_summary = "Artículos de competencia:\n" + "\n".join(titles)

        trends_summary = ""
        if trends:
            trends_summary = "Tendencias actuales: " + ", ".join(trends[:5])

        return {
            "competitors_summary": competitors_summary,
            "trends_summary": trends_summary,
        }

    def add_keywords_to_queue(self, keywords: list[str]) -> None:
        """Añade keywords a la cola de publicación."""
        queue = load_json("keywords.json")
        if not isinstance(queue, list):
            queue = []
        existing = set(queue)
        new_kws = [k for k in keywords if k not in existing]
        queue.extend(new_kws)
        save_json("keywords.json", queue)
        logger.info(f"Añadidas {len(new_kws)} keywords a la cola. Total: {len(queue)}")

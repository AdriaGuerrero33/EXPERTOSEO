"""
Tracker de posiciones SEO via Google Search Console.
"""

import os
from datetime import date, timedelta, datetime
from typing import Optional

from .utils import load_config, load_json, save_json, logger


class RankingTracker:
    """
    Rastrea posiciones de keywords usando Google Search Console.
    Guarda historial local para detectar tendencias.
    """

    def __init__(self, config: dict | None = None, site_slug: str | None = None):
        self.config = config or load_config()
        from .utils import get_site_config
        self.site = get_site_config(self.config, site_slug)
        self.seo_config = self.config.get("seo", {})

    def fetch_rankings(self, days: int = 28) -> list[dict]:
        """
        Obtiene las posiciones actuales de todas las keywords desde GSC.

        Returns:
            Lista de dicts con: keyword, position, clicks, impressions, ctr, date
        """
        try:
            service = self._get_gsc_service()
            if not service:
                logger.warning("GSC no disponible. Retornando datos cacheados.")
                return self._load_cached()

            site_url = self.site.get("gsc_property", self.site.get("url"))
            end_date = date.today()
            start_date = end_date - timedelta(days=days)

            request_body = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "dimensions": ["query"],
                "rowLimit": 1000,
            }

            response = (
                service.searchanalytics()
                .query(siteUrl=site_url, body=request_body)
                .execute()
            )

            rows = response.get("rows", [])
            rankings = []
            today = date.today().isoformat()

            for row in rows:
                rankings.append(
                    {
                        "keyword": row["keys"][0],
                        "position": round(row.get("position", 99), 1),
                        "clicks": row.get("clicks", 0),
                        "impressions": row.get("impressions", 0),
                        "ctr": round(row.get("ctr", 0) * 100, 2),
                        "date": today,
                    }
                )

            rankings.sort(key=lambda x: x["position"])
            self._save_to_history(rankings)
            logger.info(f"Rankings obtenidos: {len(rankings)} keywords")
            return rankings

        except Exception as e:
            logger.warning(f"Error obteniendo rankings GSC: {e}")
            return self._load_cached()

    def _get_gsc_service(self):
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            import json as _json

            scopes = ["https://www.googleapis.com/auth/webmasters.readonly"]
            json_val = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

            if json_val.strip().startswith("{"):
                # Valor es JSON inline (forma recomendada en Railway)
                info = _json.loads(json_val)
                credentials = service_account.Credentials.from_service_account_info(info, scopes=scopes)
            elif json_val and os.path.exists(json_val):
                # Valor es ruta a archivo
                credentials = service_account.Credentials.from_service_account_file(json_val, scopes=scopes)
            else:
                logger.debug("GOOGLE_SERVICE_ACCOUNT_JSON no configurada")
                return None

            return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
        except Exception as e:
            logger.debug(f"No se pudo inicializar GSC: {e}")
            return None

    def _save_to_history(self, rankings: list[dict]) -> None:
        """Guarda los rankings en el historial local."""
        history = load_json("rankings.json")
        if not isinstance(history, dict):
            history = {}

        today = date.today().isoformat()
        history[today] = rankings
        # Mantener solo los últimos 90 días
        if len(history) > 90:
            oldest = sorted(history.keys())[0]
            del history[oldest]

        save_json("rankings.json", history)

    def _load_cached(self) -> list[dict]:
        """Carga el ranking más reciente del historial local."""
        history = load_json("rankings.json")
        if not isinstance(history, dict) or not history:
            return []
        latest_date = max(history.keys())
        return history[latest_date]

    def get_report(self) -> dict:
        """
        Genera un reporte de posiciones categorizado.

        Returns:
            Dict con: top3, top10, top20, improvements, drops, total
        """
        rankings = self.fetch_rankings()
        if not rankings:
            return {"error": "No hay datos de rankings disponibles"}

        top3 = [r for r in rankings if r["position"] <= 3]
        top10 = [r for r in rankings if 3 < r["position"] <= 10]
        top20 = [r for r in rankings if 10 < r["position"] <= 20]

        # Detectar mejoras vs semana anterior
        improvements, drops = self._detect_changes()

        return {
            "total_keywords": len(rankings),
            "top3": top3[:10],
            "top10": top10[:15],
            "top20": top20[:15],
            "improvements": improvements[:10],
            "drops": drops[:10],
            "best_keyword": rankings[0] if rankings else None,
            "date": date.today().isoformat(),
        }

    def _detect_changes(self) -> tuple[list, list]:
        """Detecta keywords que mejoraron o bajaron posición esta semana."""
        history = load_json("rankings.json")
        if not isinstance(history, dict) or len(history) < 2:
            return [], []

        dates = sorted(history.keys())
        if len(dates) < 2:
            return [], []

        current = {r["keyword"]: r["position"] for r in history[dates[-1]]}
        previous_date = dates[-2]
        previous = {r["keyword"]: r["position"] for r in history[previous_date]}

        improvements = []
        drops = []

        for kw, pos in current.items():
            if kw in previous:
                prev_pos = previous[kw]
                change = prev_pos - pos  # Positivo = mejoró
                if change >= 2:
                    improvements.append({"keyword": kw, "position": pos, "change": change})
                elif change <= -2:
                    drops.append({"keyword": kw, "position": pos, "change": change})

        improvements.sort(key=lambda x: x["change"], reverse=True)
        drops.sort(key=lambda x: x["change"])
        return improvements, drops

    def print_report(self) -> None:
        """Imprime el reporte de rankings con Rich."""
        from rich.table import Table
        from rich.console import Console
        from rich import box
        from rich.panel import Panel

        con = Console()
        report = self.get_report()

        if "error" in report:
            con.print(f"[red]{report['error']}[/red]")
            return

        con.print(Panel(
            f"[bold]Rankings SEO — {report['date']}[/bold]\n"
            f"Total keywords: {report['total_keywords']} | "
            f"Top 3: {len(report['top3'])} | "
            f"Top 10: {len(report['top10'])} | "
            f"Top 20: {len(report['top20'])}",
            style="blue",
        ))

        def make_table(title: str, rows: list[dict], color: str) -> Table:
            t = Table(title=title, box=box.SIMPLE, show_header=True, header_style=f"bold {color}")
            t.add_column("Keyword")
            t.add_column("Pos.", justify="right")
            t.add_column("Clicks", justify="right")
            t.add_column("Impresiones", justify="right")
            t.add_column("CTR %", justify="right")
            for r in rows:
                t.add_row(
                    r["keyword"],
                    str(r["position"]),
                    str(r.get("clicks", "-")),
                    str(r.get("impressions", "-")),
                    str(r.get("ctr", "-")),
                )
            return t

        if report["top3"]:
            con.print(make_table("TOP 3", report["top3"], "green"))
        if report["top10"]:
            con.print(make_table("TOP 4-10", report["top10"], "yellow"))
        if report["improvements"]:
            t = Table(title="Mejoras esta semana", box=box.SIMPLE, header_style="bold green")
            t.add_column("Keyword")
            t.add_column("Posición", justify="right")
            t.add_column("Mejora", justify="right")
            for r in report["improvements"]:
                t.add_row(r["keyword"], str(r["position"]), f"+{r['change']}")
            con.print(t)
        if report["drops"]:
            t = Table(title="Bajadas esta semana", box=box.SIMPLE, header_style="bold red")
            t.add_column("Keyword")
            t.add_column("Posición", justify="right")
            t.add_column("Cambio", justify="right")
            for r in report["drops"]:
                t.add_row(r["keyword"], str(r["position"]), str(r["change"]))
            con.print(t)

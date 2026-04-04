"""
Gestión de múltiples sitios WordPress.
"""

from rich.console import Console
from rich.table import Table
from rich import box

from .utils import load_config, logger
from .publisher import WordPressPublisher

console = Console()


class SiteManager:
    """Gestiona la configuración y conexión de múltiples sitios WordPress."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()

    def list_sites(self) -> None:
        """Muestra todos los sitios configurados."""
        sites = self.config.get("sites", [])
        if not sites:
            console.print("[yellow]No hay sitios configurados. Edita config.yaml[/yellow]")
            return

        active_slug = self.config.get("schedule", {}).get("active_site", "")

        table = Table(title="Sitios WordPress", box=box.SIMPLE, show_header=True)
        table.add_column("Slug", style="cyan")
        table.add_column("Nombre")
        table.add_column("URL")
        table.add_column("Usuario")
        table.add_column("Activo", justify="center")
        table.add_column("App Password", justify="center")

        for site in sites:
            is_active = "✓" if site.get("slug") == active_slug else ""
            has_password = "✓" if site.get("wp_app_password") else "[red]✗[/red]"
            table.add_row(
                site.get("slug", "-"),
                site.get("name", "-"),
                site.get("url", "-"),
                site.get("wp_user", "-"),
                is_active,
                has_password,
            )

        console.print(table)

    def test_site(self, slug: str | None = None) -> bool:
        """Prueba la conexión con un sitio específico o el activo."""
        try:
            publisher = WordPressPublisher(self.config, slug)
            result = publisher.test_connection()
            if result:
                console.print(f"[green]Conexión exitosa con {publisher.site['name']}[/green]")
            else:
                console.print(f"[red]Error de conexión con {publisher.site['name']}[/red]")
            return result
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return False

    def test_all_sites(self) -> dict[str, bool]:
        """Prueba la conexión con todos los sitios configurados."""
        sites = self.config.get("sites", [])
        results = {}
        for site in sites:
            slug = site.get("slug")
            console.print(f"\nProbando sitio: [bold]{site.get('name')}[/bold] ({slug})")
            results[slug] = self.test_site(slug)
        return results

    def get_site_info(self, slug: str | None = None) -> dict:
        """Retorna info del sitio (categorías, plugins disponibles, etc.)."""
        from .utils import get_site_config
        site = get_site_config(self.config, slug)
        publisher = WordPressPublisher(self.config, slug)

        info = {
            "name": site.get("name"),
            "url": site.get("url"),
            "slug": site.get("slug"),
        }

        # Obtener categorías disponibles
        try:
            resp = publisher.session.get(
                f"{publisher.api_base}/categories",
                params={"per_page": 50},
                timeout=10,
            )
            if resp.status_code == 200:
                cats = resp.json()
                info["categories"] = [{"id": c["id"], "name": c["name"], "count": c["count"]} for c in cats]
        except Exception as e:
            logger.debug(f"No se pudieron obtener categorías: {e}")

        # Verificar RankMath
        from .rankmath_controller import RankMathController
        rankmath = RankMathController(self.config, slug)
        info["rankmath_available"] = rankmath.check_rankmath_available()

        return info

    def print_site_info(self, slug: str | None = None) -> None:
        """Imprime información detallada del sitio."""
        from rich.panel import Panel
        info = self.get_site_info(slug)

        console.print(Panel(
            f"[bold]{info['name']}[/bold]\n"
            f"URL: {info['url']}\n"
            f"RankMath: {'[green]Activo[/green]' if info.get('rankmath_available') else '[red]No disponible[/red]'}",
            title=f"Sitio: {info['slug']}",
        ))

        if "categories" in info:
            console.print("\n[bold]Categorías disponibles:[/bold]")
            for cat in info["categories"][:10]:
                console.print(f"  • {cat['name']} ({cat['count']} posts)")

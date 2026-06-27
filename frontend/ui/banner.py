"""Alchemy CLI banner and branding helpers."""

from __future__ import annotations

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from backend.app import __version__

_LOGO = r"""
 █████╗ ██╗      ██████╗██╗  ██╗███████╗███╗   ███╗██╗   ██╗
██╔══██╗██║     ██╔════╝██║  ██║██╔════╝████╗ ████║╚██╗ ██╔╝
███████║██║     ██║     ███████║█████╗  ██╔████╔██║ ╚████╔╝
██╔══██║██║     ██║     ██╔══██║██╔══╝  ██║╚██╔╝██║  ╚██╔╝
██║  ██║███████╗╚██████╗██║  ██║███████╗██║ ╚═╝ ██║   ██║
╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝   ╚═╝
"""

_TAGLINE = "Adaptive Cost-Aware AI Gateway"
_SUBTITLE = "The right model, at the right cost, at the right time — every time."


def render_banner(console: Console) -> None:
    """Print the Alchemy banner to the given console.

    Args:
        console: The Rich console to render into.
    """
    body = Text()
    body.append(_LOGO, style="bold magenta")
    body.append(f"\n{_TAGLINE}", style="bold cyan")
    body.append(f"   v{__version__}\n", style="dim")
    body.append(_SUBTITLE, style="italic green")

    console.print(
        Panel(
            Align.center(body),
            border_style="magenta",
            padding=(1, 4),
            title="[bold]⚗  ALCHEMY[/bold]",
            subtitle="[dim]powered by Mozilla Otari[/dim]",
        )
    )

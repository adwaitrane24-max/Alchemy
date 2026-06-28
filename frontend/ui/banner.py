"""Alchemy CLI banner and home screen."""

from __future__ import annotations

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from backend.app import __version__
from frontend.ui.theme import (
    BORDER_PRIMARY,
    CYAN,
    DIM,
    GREEN,
    PURPLE,
    YELLOW,
)

_LOGO = r"""
 █████╗ ██╗      ██████╗██╗  ██╗███████╗███╗   ███╗██╗   ██╗
██╔══██╗██║     ██╔════╝██║  ██║██╔════╝████╗ ████║╚██╗ ██╔╝
███████║██║     ██║     ███████║█████╗  ██╔████╔██║ ╚████╔╝
██╔══██║██║     ██║     ██╔══██║██╔══╝  ██║╚██╔╝██║  ╚██╔╝
██║  ██║███████╗╚██████╗██║  ██║███████╗██║ ╚═╝ ██║   ██║
╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝   ╚═╝
"""

_GRADIENT = ["#e040fb", "#d500f9", "#aa00ff", "#b388ff", "#7c4dff", "#651fff"]


def _gradient_logo() -> Text:
    lines = _LOGO.strip("\n").split("\n")
    text = Text()
    for i, line in enumerate(lines):
        text.append(line + "\n", style=f"bold {_GRADIENT[i % len(_GRADIENT)]}")
    return text


def render_banner(console: Console) -> None:
    """Print the ALCHEMY banner with system status."""
    body = Text()
    body.append_text(_gradient_logo())
    body.append("\n")
    body.append("AI Gateway", style=f"bold {CYAN}")
    body.append("  •  ", style=DIM)
    body.append("Mozilla Otari Powered", style=f"italic {DIM}")

    console.print(
        Panel(
            Align.center(body),
            border_style=BORDER_PRIMARY,
            padding=(1, 4),
            title="[bold]⚗  ALCHEMY[/bold]",
            subtitle=f"[{DIM}]v{__version__}[/{DIM}]",
        )
    )


def render_status_bar(
    console: Console,
    *,
    voice_ready: bool = False,
    budget_state: str = "HEALTHY",
    model_label: str = "Auto",
) -> None:
    """Print the system status bar below the banner."""
    budget_style = (
        f"bold {GREEN}" if budget_state == "HEALTHY"
        else f"bold {YELLOW}" if budget_state == "LOW"
        else "bold red"
    )
    table = Table.grid(padding=(0, 1))
    table.add_column(style=f"bold {CYAN}", min_width=18)
    table.add_column(min_width=20)

    table.add_row("  Status", Text("  🟢 Online", style=f"bold {GREEN}"))
    table.add_row(
        "  Voice",
        Text("  🎤 Ready", style=f"bold {GREEN}") if voice_ready
        else Text("  🎤 Unavailable", style=f"{DIM}"),
    )
    table.add_row("  Cache", Text("  ⚡ Enabled", style=f"bold {GREEN}"))
    table.add_row("  Budget", Text(f"  💰 {budget_state.title()}", style=budget_style))
    table.add_row("  Model", Text(f"  🤖 {model_label}", style=f"bold {PURPLE}"))

    console.print(
        Panel(table, border_style=DIM, title=f"[{DIM}]System[/{DIM}]", padding=(0, 1))
    )
    console.print()

"""Main Typer CLI application for user-facing interactions."""

from __future__ import annotations

import contextlib
import sys

import typer
from rich.console import Console

from backend.app import __version__
from backend.app.config.settings import get_settings
from backend.app.core import setup_logging
from backend.app.models.budget import BudgetSnapshot
from frontend.cli.session import InteractiveSession
from frontend.dashboard import Dashboard


def _force_utf8_streams() -> None:
    """Reconfigure stdio to UTF-8 so Rich glyphs render on legacy consoles.

    On Windows the default console codec (cp1252) cannot encode the box-drawing
    and symbol characters used by the banner/dashboard, which would crash the
    CLI when piped or run on a non-UTF-8 terminal.
    """
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            # Some streams (e.g. already-detached pipes) cannot be reconfigured.
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


_force_utf8_streams()

app = typer.Typer(
    name="alchemy",
    help="Alchemy — Adaptive Cost-Aware AI Gateway CLI",
    invoke_without_command=True,
    no_args_is_help=False,
)

_console = Console()


def _init_logging() -> None:
    """Configure logging from settings (CLI logs are quiet by default)."""
    settings = get_settings()
    setup_logging(log_level=settings.alchemy_log_level, is_production=settings.is_production)


@app.callback()
def main(ctx: typer.Context) -> None:
    """Launch the interactive session when no subcommand is provided."""
    if ctx.invoked_subcommand is None:
        _init_logging()
        InteractiveSession(console=_console).run()


@app.command()
def chat(
    voice: bool = typer.Option(False, "--voice", "-v", help="Enable voice input (later milestone)"),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override model selection [local|mini|gpt4o]"
    ),
) -> None:
    """Start an interactive chat session with Alchemy."""
    if voice:
        _console.print("[yellow]Voice input is not available yet; using text input.[/yellow]")
    _init_logging()
    InteractiveSession(console=_console).run(model_override=model)


@app.command()
def budget() -> None:
    """Display the budget dashboard."""
    _init_logging()
    settings = get_settings()
    snapshot = BudgetSnapshot(
        daily_limit_usd=settings.budget_daily_limit_usd,
        spent_usd=0.0,
        warning_threshold=settings.budget_warning_threshold,
        critical_threshold=settings.budget_critical_threshold,
    )
    Dashboard(_console).render_placeholder(snapshot)


@app.command()
def version() -> None:
    """Display version information."""
    _console.print(f"[bold magenta]Alchemy[/bold magenta] v{__version__}")


if __name__ == "__main__":
    app()

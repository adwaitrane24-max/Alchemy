"""Backend management CLI — database, cache, and server operations."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="alchemy",
    help="Alchemy — Adaptive Cost-Aware AI Gateway",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Alchemy CLI entry point."""


if __name__ == "__main__":
    app()

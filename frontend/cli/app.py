"""Main Typer CLI application for user-facing interactions."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="alchemy",
    help="Alchemy — Adaptive Cost-Aware AI Gateway CLI",
    no_args_is_help=True,
)


@app.command()
def chat(
    voice: bool = typer.Option(False, "--voice", "-v", help="Enable voice input via Smallest.ai"),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override model selection [local|mini|gpt4o]"
    ),
) -> None:
    """Start an interactive chat session with Alchemy."""
    # Implementation in Milestone 5
    typer.echo("Chat session not yet implemented.")


@app.command()
def budget() -> None:
    """Display the budget dashboard."""
    # Implementation in Milestone 5
    typer.echo("Budget dashboard not yet implemented.")


@app.command()
def version() -> None:
    """Display version information."""
    typer.echo("Alchemy v0.1.0")


if __name__ == "__main__":
    app()

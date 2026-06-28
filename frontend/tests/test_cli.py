"""Integration tests for the frontend CLI, dashboard, and interactive session."""

from __future__ import annotations

import io

from rich.console import Console
from typer.testing import CliRunner

from backend.app.models.budget import BudgetSnapshot
from backend.app.models.request import PromptRequest
from backend.app.services import AlchemyPipeline
from frontend.cli.app import app
from frontend.cli.session import InteractiveSession
from frontend.dashboard import Dashboard
from frontend.ui import render_banner

runner = CliRunner()


def _console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, width=100, force_terminal=False), buffer


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Alchemy" in result.stdout


def test_budget_command_renders() -> None:
    result = runner.invoke(app, ["budget"])
    assert result.exit_code == 0
    assert "Budget" in result.stdout


def test_banner_renders() -> None:
    console, buffer = _console()
    render_banner(console)
    assert "ALCHEMY" in buffer.getvalue()


def test_dashboard_renders_processed_response() -> None:
    console, buffer = _console()
    pipeline = AlchemyPipeline()
    response = pipeline.process(PromptRequest(prompt="Explain quicksort in detail with code."))
    budget = BudgetSnapshot(daily_limit_usd=5.0, spent_usd=0.0)

    Dashboard(console).render(response, budget)
    out = buffer.getvalue()
    assert "Routing" in out
    assert "Budget" in out
    assert "Analysis" in out


def test_interactive_session_runs_and_exits() -> None:
    """Drive the session with scripted input: one prompt, then 'exit'."""
    console, out_buffer = _console()
    session = InteractiveSession(console=console, pipeline=AlchemyPipeline())

    # Rich's Prompt.ask reads via console.input; feed scripted lines.
    lines = iter(["1", "hello", "exit"])
    console.input = lambda *args, **kwargs: next(lines)  # type: ignore[method-assign]

    session.run(model_override="local")
    out = out_buffer.getvalue()
    assert "ALCHEMY" in out  # banner rendered
    assert "alchemy" in out  # answer panel rendered for the 'hello' prompt

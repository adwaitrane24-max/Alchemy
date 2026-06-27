"""Interactive Alchemy CLI session.

Implements the read-eval-print loop: banner, mode selection, input box, and the
exit option. Each prompt is run through the backend pipeline and the resulting
decision trace is rendered via the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from backend.app.config.settings import get_settings
from backend.app.models.budget import BudgetSnapshot
from backend.app.models.request import PromptRequest
from backend.app.services import AlchemyPipeline
from frontend.dashboard import Dashboard
from frontend.ui import render_banner

_EXIT_WORDS = frozenset({"exit", "quit", ":q", "q"})


@dataclass(frozen=True)
class Mode:
    """A selectable routing mode shown at session start."""

    key: str
    label: str
    model_override: str | None


_MODES: tuple[Mode, ...] = (
    Mode("1", "Auto (let Alchemy route)", None),
    Mode("2", "Force Local 2B", "local"),
    Mode("3", "Force GPT-4o-mini", "mini"),
    Mode("4", "Force GPT-4o", "gpt4o"),
)


class InteractiveSession:
    """Drives the interactive CLI experience."""

    def __init__(
        self,
        console: Console | None = None,
        pipeline: AlchemyPipeline | None = None,
    ) -> None:
        self._console = console or Console()
        self._pipeline = pipeline or AlchemyPipeline()
        self._dashboard = Dashboard(self._console)
        self._settings = get_settings()

    def _budget_snapshot(self) -> BudgetSnapshot:
        """Static budget snapshot mirroring the pipeline's (spend tracking TBD)."""
        return BudgetSnapshot(
            daily_limit_usd=self._settings.budget_daily_limit_usd,
            spent_usd=0.0,
            warning_threshold=self._settings.budget_warning_threshold,
            critical_threshold=self._settings.budget_critical_threshold,
        )

    def _select_mode(self) -> Mode:
        """Prompt the user to choose a routing mode."""
        table = Text()
        for mode in _MODES:
            table.append(f"  [{mode.key}] ", style="bold cyan")
            table.append(f"{mode.label}\n")
        self._console.print(Panel(table, title="[bold]Select Mode[/bold]", border_style="cyan"))
        choice = Prompt.ask(
            "[bold magenta]Mode[/bold magenta]",
            choices=[m.key for m in _MODES],
            default="1",
            console=self._console,
        )
        return next(m for m in _MODES if m.key == choice)

    def run(self, model_override: str | None = None) -> None:
        """Run the interactive loop until the user exits.

        Args:
            model_override: If provided, skips the mode menu and forces this
                model alias (``local`` | ``mini`` | ``gpt4o``) for the session.
        """
        render_banner(self._console)
        if model_override is not None:
            mode = Mode("override", f"Forced: {model_override}", model_override)
        else:
            mode = self._select_mode()
        self._console.print(
            f"[dim]Mode:[/dim] [bold]{mode.label}[/bold]   "
            "[dim]Type your prompt, or 'exit' to quit.[/dim]\n"
        )
        self._dashboard.render_placeholder(self._budget_snapshot())

        while True:
            try:
                user_input = Prompt.ask("[bold green]you[/bold green]", console=self._console)
            except (EOFError, KeyboardInterrupt):
                self._console.print("\n[dim]Session ended.[/dim]")
                return

            if user_input.strip().lower() in _EXIT_WORDS:
                self._console.print("[dim]Goodbye! 👋[/dim]")
                return
            if not user_input.strip():
                continue

            self._handle(user_input, mode)

    def _handle(self, user_input: str, mode: Mode) -> None:
        """Process one prompt and render the answer plus dashboard."""
        request = PromptRequest(prompt=user_input, model_override=mode.model_override)
        response = self._pipeline.process(request)

        answer_style = "red" if response.blocked else "white"
        self._console.print(
            Panel(
                Text(response.text, style=answer_style),
                title="[bold]alchemy[/bold]",
                border_style="red" if response.blocked else "green",
                padding=(1, 2),
            )
        )
        self._dashboard.render(response, self._budget_snapshot())
        self._console.print()

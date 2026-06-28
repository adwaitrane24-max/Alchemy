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

from backend.app.budget import BudgetManager
from backend.app.config.settings import get_settings
from backend.app.metrics import ModelMetrics
from backend.app.models.budget import BudgetSnapshot
from backend.app.models.request import PromptRequest
from backend.app.pricing import PricingCache, PricingService, ProviderRegistry
from backend.app.services import AlchemyPipeline
from backend.app.usage import UsageCollector, UsageService
from backend.app.voice.exceptions import VoiceError
from backend.app.voice.voice_manager import VoiceManager
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

        # Initialize budget services
        self._pricing_cache = PricingCache()
        self._provider_registry = ProviderRegistry()
        self._pricing_service = PricingService(self._provider_registry, self._pricing_cache)
        self._usage_service = UsageService()
        self._budget_manager = BudgetManager(self._settings.budget_session_limit_usd)
        self._model_metrics = ModelMetrics()
        self._usage_collector = UsageCollector()

        # Track manual override for current request
        self._current_model_override: str | None = None

        # Voice input
        self._voice_manager = VoiceManager(settings=self._settings)
        self._voice_mode = False

    def _budget_snapshot(self) -> BudgetSnapshot:
        """Return budget snapshot from actual session budget manager."""
        return BudgetSnapshot(
            daily_limit_usd=self._budget_manager.total_budget_usd,
            spent_usd=self._budget_manager.used_budget_usd,
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

    def _select_input_mode(self) -> str:
        """Prompt the user to choose keyboard or voice input."""
        table = Text()
        table.append("  [1] ", style="bold cyan")
        table.append("Keyboard\n")
        table.append("  [2] ", style="bold cyan")
        table.append("Voice\n")
        table.append("  [3] ", style="bold cyan")
        table.append("Exit\n")
        self._console.print(
            Panel(table, title="[bold]Select Input Mode[/bold]", border_style="cyan")
        )
        choice = Prompt.ask(
            "[bold magenta]Input[/bold magenta]",
            choices=["1", "2", "3"],
            default="1",
            console=self._console,
        )
        return choice

    def run(self, model_override: str | None = None) -> None:
        """Run the interactive loop until the user exits.

        Args:
            model_override: If provided, skips the mode menu and forces this
                model alias (``local`` | ``mini`` | ``gpt4o``) for the session.
        """
        render_banner(self._console)

        # Input mode selection
        input_choice = self._select_input_mode()
        if input_choice == "3":
            self._console.print("[dim]Goodbye![/dim]")
            return
        if input_choice == "2":
            ready, reason = self._voice_manager.check_readiness()
            if ready:
                self._voice_mode = True
                self._console.print("[green]Voice input enabled.[/green]\n")
            else:
                self._console.print(
                    f"[yellow]Voice unavailable: {reason}. Falling back to keyboard.[/yellow]\n"
                )
                self._voice_mode = False

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
            if self._voice_mode:
                user_input = self._voice_input_loop()
            else:
                user_input = self._keyboard_input()

            if user_input is None:
                continue

            if user_input.strip().lower() in _EXIT_WORDS:
                self._console.print("[dim]Goodbye![/dim]")
                return
            if not user_input.strip():
                continue

            # Check for :model command
            if user_input.strip().startswith(":model"):
                self._handle_model_command(user_input.strip())
                continue

            # Check for :voice / :keyboard toggle
            if user_input.strip() == ":voice":
                ready, reason = self._voice_manager.check_readiness()
                if ready:
                    self._voice_mode = True
                    self._console.print("[green]Switched to voice input.[/green]")
                else:
                    self._console.print(f"[yellow]Voice unavailable: {reason}[/yellow]")
                continue
            if user_input.strip() == ":keyboard":
                self._voice_mode = False
                self._console.print("[green]Switched to keyboard input.[/green]")
                continue

            self._handle(user_input, mode)

    def _keyboard_input(self) -> str | None:
        """Read one line from the keyboard."""
        try:
            return Prompt.ask("[bold green]you[/bold green]", console=self._console)
        except (EOFError, KeyboardInterrupt):
            self._console.print("\n[dim]Session ended.[/dim]")
            return "exit"

    def _voice_input_loop(self) -> str | None:
        """Record, transcribe, and confirm a voice input."""
        try:
            self._console.print()
            result = self._voice_manager.record_and_transcribe(
                on_listening=lambda: self._console.print(
                    "[bold yellow]🎤 Listening...[/bold yellow] (speak now, silence to stop)"
                ),
            )
        except VoiceError as exc:
            self._console.print(f"[red]Voice error: {exc}[/red]")
            self._console.print("[yellow]Falling back to keyboard for this prompt.[/yellow]")
            return self._keyboard_input()

        self._console.print("[dim]🧠 Converting speech to text...[/dim]")
        self._console.print()
        self._console.print(
            Panel(
                Text(result.text),
                title="[bold]Recognized Text[/bold]",
                border_style="cyan",
                padding=(0, 2),
            )
        )

        action = Prompt.ask(
            "[bold][Y][/bold] Send  [bold][R][/bold] Record Again  "
            "[bold][E][/bold] Edit  [bold][C][/bold] Cancel",
            choices=["Y", "R", "E", "C", "y", "r", "e", "c"],
            default="Y",
            console=self._console,
        ).upper()

        if action == "Y":
            return result.text
        if action == "R":
            return self._voice_input_loop()
        if action == "E":
            edited = Prompt.ask(
                "[bold green]edit[/bold green]",
                default=result.text,
                console=self._console,
            )
            return edited
        return None

    def _handle_model_command(self, command: str) -> None:
        """Handle :model command for model selection."""
        parts = command.split()

        if len(parts) == 1:
            # :model → Show available models
            self._display_available_models()
        elif len(parts) == 2:
            model_arg = parts[1].lower()
            if model_arg == "auto":
                self._current_model_override = None
                self._console.print("[green]✓ Automatic routing enabled[/green]")
            else:
                # Validate model
                valid_models = {
                    "gpt-4o": "gpt-4o",
                    "gpt4o": "gpt-4o",
                    "claude": "claude-sonnet",
                    "sonnet": "claude-sonnet",
                    "gemini": "gemini-1.5-flash",
                    "flash": "gemini-1.5-flash",
                    "grok": "grok-1",
                    "qwen": "qwen-plus",
                    "gemma": "gemma:2b",
                    "deepseek": "deepseek-chat",
                    "perplexity": "pplx-7b-online",
                    "local": "local_2b",
                    "mini": "gpt-4o-mini",
                }
                if model_arg in valid_models:
                    self._current_model_override = model_arg
                    self._console.print(f"[green]✓ Model override set to {model_arg}[/green]")
                else:
                    self._console.print(
                        f"[red]✗ Unknown model: {model_arg}. Try :model for list.[/red]"
                    )
        else:
            self._console.print("[red]Usage: :model or :model <name> or :model auto[/red]")

    def _display_available_models(self) -> None:
        """Display available models with pricing and latency."""
        models = [
            ("GPT-4o", "openai", "gpt-4o", "$0.005/$0.015 per 1K tokens"),
            ("GPT-4o-mini", "openai", "gpt-4o-mini", "$0.00015/$0.0006 per 1K tokens"),
            ("Claude Sonnet", "anthropic", "claude-sonnet", "$0.003/$0.015 per 1K tokens"),
            ("Gemini 1.5 Flash", "gemini", "gemini-1.5-flash", "$0.075/$0.30 per 1M tokens"),
            ("Grok", "grok", "grok-1", "$0.005/$0.015 per 1K tokens"),
            ("Qwen Plus", "qwen", "qwen-plus", "$0.0008/$0.002 per 1K tokens"),
            ("Gemma 2B", "gemma", "gemma:2b", "$0.00005/$0.00015 per 1K tokens"),
            ("DeepSeek", "deepseek", "deepseek-chat", "$0.00014/$0.00028 per 1K tokens"),
            ("Perplexity", "perplexity", "pplx-7b-online", "$0.002/$0.002 per 1K tokens"),
            ("Ollama (Local)", "ollama", "gemma:2b", "FREE"),
        ]

        table_text = Text("\nAvailable Models\n\n", style="bold cyan")
        for name, provider, model, pricing in models:
            latency = self._model_metrics.get_average_latency(model)
            latency_str = (
                f"{latency:.0f}ms (based on {self._model_metrics.get_metric(model).request_count} requests)"
                if latency
                else "Unknown"
            )
            table_text.append(f"{name}\n", style="bold")
            table_text.append(f"  Provider    {provider}\n")
            table_text.append(f"  Pricing     {pricing}\n")
            table_text.append(f"  Speed       {latency_str}\n\n")

        self._console.print(Panel(table_text, border_style="cyan"))

    def _handle(self, user_input: str, mode: Mode) -> None:
        """Process one prompt and render the answer plus dashboard."""
        # Use manual override if set, otherwise use mode's override
        override = self._current_model_override or mode.model_override

        request = PromptRequest(prompt=user_input, model_override=override)
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

        # Update budget manager with the cost BEFORE displaying
        budget_warning = self._budget_manager.update(response.cost_usd)

        # Update usage service
        self._usage_service.update_total_cost(response.cost_usd)

        # Update metrics if we have response data
        if response.latency_ms and response.model:
            self._model_metrics.update(response.model.value, response.latency_ms)

        # Display budget warning if threshold crossed
        if budget_warning:
            if budget_warning.level == "warning":
                self._console.print(f"\n[yellow]{budget_warning.message}[/yellow]")
                enable_eco = Prompt.ask(
                    "Would you like to switch to Economic Mode?",
                    choices=["Y", "N"],
                    default="N",
                    console=self._console,
                )
                if enable_eco.upper() == "Y":
                    self._budget_manager.enable_economic_mode()
                    self._console.print("[green]Economic Mode Enabled[/green]\n")
            elif budget_warning.level == "critical" or budget_warning.level == "exhausted":
                self._console.print(f"\n[red bold]{budget_warning.message}[/red bold]\n")

        self._dashboard.render(response, self._budget_snapshot())

        # Clear manual override for next request
        self._current_model_override = None
        self._console.print()

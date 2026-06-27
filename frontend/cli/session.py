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

            # Check for :model command
            if user_input.strip().startswith(":model"):
                self._handle_model_command(user_input.strip())
                continue

            self._handle(user_input, mode)

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
                    self._console.print(f"[red]✗ Unknown model: {model_arg}. Try :model for list.[/red]")
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

        # Display budget summary with UPDATED values
        if response.model:
            budget_text = Text()
            budget_text.append("Budget Summary\n", style="bold")
            budget_text.append(f"Model          {response.model.value}\n")
            budget_text.append(f"Prompt Tokens  {response.prompt_tokens}\n")
            budget_text.append(f"Completion Tokens {response.completion_tokens}\n")
            budget_text.append(f"Request Cost   ${response.cost_usd:.4f}\n")
            budget_text.append(f"Used Budget    ${self._budget_manager.used_budget_usd:.2f}\n")
            budget_text.append(f"Remaining      ${self._budget_manager.remaining_budget_usd:.2f}\n")
            budget_text.append(f"Economic Mode  {'ON' if self._budget_manager.economic_mode else 'OFF'}\n")

            self._console.print(Panel(budget_text, border_style="cyan", padding=(0, 2)))

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
            elif budget_warning.level == "critical":
                self._console.print(f"\n[red bold]{budget_warning.message}[/red bold]\n")
            elif budget_warning.level == "exhausted":
                self._console.print(f"\n[red bold]{budget_warning.message}[/red bold]\n")

        self._dashboard.render(response, self._budget_snapshot())

        # Clear manual override for next request
        self._current_model_override = None
        self._console.print()

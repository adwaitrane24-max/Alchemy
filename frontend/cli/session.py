"""Interactive Alchemy CLI session.

Premium terminal experience with animated pipeline, model routing, and
decision reporting. All output is Rich-based — no web UI.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from rich.console import Console
from rich.live import Live
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
from frontend.dashboard.dashboard import animate_model_selection, animate_pipeline
from frontend.ui import render_banner, render_status_bar
from frontend.ui.theme import CYAN, DIM, GREEN, PURPLE, RED, YELLOW

_EXIT_WORDS = frozenset({"exit", "quit", ":q", "q"})


@dataclass(frozen=True)
class Mode:
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

        self._pricing_cache = PricingCache()
        self._provider_registry = ProviderRegistry()
        self._pricing_service = PricingService(self._provider_registry, self._pricing_cache)
        self._usage_service = UsageService()
        self._budget_manager = BudgetManager(self._settings.budget_session_limit_usd)
        self._model_metrics = ModelMetrics()
        self._usage_collector = UsageCollector()

        self._current_model_override: str | None = None
        self._voice_manager = VoiceManager(settings=self._settings)
        self._voice_mode = False

    def _budget_snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            daily_limit_usd=self._budget_manager.total_budget_usd,
            spent_usd=self._budget_manager.used_budget_usd,
            warning_threshold=self._settings.budget_warning_threshold,
            critical_threshold=self._settings.budget_critical_threshold,
        )

    def _select_mode(self) -> Mode:
        table = Text()
        for mode in _MODES:
            table.append(f"  [{mode.key}] ", style=f"bold {CYAN}")
            table.append(f"{mode.label}\n")
        self._console.print(
            Panel(table, title=f"[bold {PURPLE}]Select Mode[/bold {PURPLE}]", border_style=PURPLE)
        )
        choice = Prompt.ask(
            f"[bold {PURPLE}]Mode[/bold {PURPLE}]",
            choices=[m.key for m in _MODES],
            default="1",
            console=self._console,
        )
        return next(m for m in _MODES if m.key == choice)

    def _select_input_mode(self) -> str:
        table = Text()
        table.append("  [1] ", style=f"bold {CYAN}")
        table.append("⌨  Keyboard\n")
        table.append("  [2] ", style=f"bold {CYAN}")
        table.append("🎤 Voice\n")
        table.append("  [3] ", style=f"bold {CYAN}")
        table.append("✕  Exit\n")
        self._console.print(
            Panel(table, title=f"[bold {PURPLE}]Input Mode[/bold {PURPLE}]", border_style=PURPLE)
        )
        choice = Prompt.ask(
            f"[bold {PURPLE}]Input[/bold {PURPLE}]",
            choices=["1", "2", "3"],
            default="1",
            console=self._console,
        )
        return choice

    def run(self, model_override: str | None = None) -> None:
        render_banner(self._console)

        input_choice = self._select_input_mode()
        if input_choice == "3":
            self._console.print(f"[{DIM}]Goodbye![/{DIM}]")
            return
        if input_choice == "2":
            ready, reason = self._voice_manager.check_readiness()
            if ready:
                self._voice_mode = True
                self._console.print(f"[{GREEN}]✓ Voice input enabled.[/{GREEN}]\n")
            else:
                self._console.print(
                    f"[{YELLOW}]Voice unavailable: {reason}. Falling back to keyboard.[/{YELLOW}]\n"
                )
                self._voice_mode = False

        if model_override is not None:
            mode = Mode("override", f"Forced: {model_override}", model_override)
        else:
            mode = self._select_mode()

        voice_ready = self._voice_manager.check_readiness()[0]
        budget_state = self._budget_snapshot().state.value
        model_label = mode.label if mode.model_override else "Auto"
        render_status_bar(
            self._console,
            voice_ready=voice_ready,
            budget_state=budget_state,
            model_label=model_label,
        )

        self._console.print(
            f"[{DIM}]Type your prompt or 'exit' to quit.  "
            f":voice / :keyboard to switch input.  :model to change model.[/{DIM}]\n"
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
                self._console.print(f"\n[{DIM}]Goodbye![/{DIM}]")
                return
            if not user_input.strip():
                continue

            if user_input.strip().startswith(":model"):
                self._handle_model_command(user_input.strip())
                continue
            if user_input.strip() == ":voice":
                ready, reason = self._voice_manager.check_readiness()
                if ready:
                    self._voice_mode = True
                    self._console.print(f"[{GREEN}]✓ Switched to voice input.[/{GREEN}]")
                else:
                    self._console.print(f"[{YELLOW}]Voice unavailable: {reason}[/{YELLOW}]")
                continue
            if user_input.strip() == ":keyboard":
                self._voice_mode = False
                self._console.print(f"[{GREEN}]✓ Switched to keyboard input.[/{GREEN}]")
                continue

            self._handle(user_input, mode)

    def _keyboard_input(self) -> str | None:
        try:
            return Prompt.ask(f"[bold {GREEN}]you[/bold {GREEN}]", console=self._console)
        except (EOFError, KeyboardInterrupt):
            self._console.print(f"\n[{DIM}]Session ended.[/{DIM}]")
            return "exit"

    def _voice_input_loop(self) -> str | None:
        try:
            self._console.print()
            result = self._voice_manager.record_and_transcribe(
                on_listening=lambda: self._console.print(
                    f"[bold {YELLOW}]🎤 Listening...[/bold {YELLOW}] [dim](speak now, silence to stop)[/dim]"
                ),
            )
        except VoiceError as exc:
            self._console.print(f"[{RED}]Voice error: {exc}[/{RED}]")
            self._console.print(f"[{YELLOW}]Falling back to keyboard.[/{YELLOW}]")
            return self._keyboard_input()

        self._console.print(f"[{DIM}]🧠 Converting speech to text...[/{DIM}]")
        self._console.print()
        self._console.print(
            Panel(
                Text(result.text),
                title=f"[bold {CYAN}]Recognized Text[/bold {CYAN}]",
                border_style=CYAN,
                padding=(0, 2),
            )
        )

        action = Prompt.ask(
            f"[bold][Y][/bold] Send  [bold][R][/bold] Record Again  "
            f"[bold][E][/bold] Edit  [bold][C][/bold] Cancel",
            choices=["Y", "R", "E", "C", "y", "r", "e", "c"],
            default="Y",
            console=self._console,
        ).upper()

        if action == "Y":
            return result.text
        if action == "R":
            return self._voice_input_loop()
        if action == "E":
            return Prompt.ask(
                f"[bold {GREEN}]edit[/bold {GREEN}]",
                default=result.text,
                console=self._console,
            )
        return None

    def _handle_model_command(self, command: str) -> None:
        parts = command.split()
        if len(parts) == 1:
            self._display_available_models()
        elif len(parts) == 2:
            model_arg = parts[1].lower()
            if model_arg == "auto":
                self._current_model_override = None
                self._console.print(f"[{GREEN}]✓ Automatic routing enabled[/{GREEN}]")
            else:
                valid_models = {
                    "gpt-4o": "gpt-4o", "gpt4o": "gpt-4o",
                    "claude": "claude-sonnet", "sonnet": "claude-sonnet",
                    "gemini": "gemini-1.5-flash", "flash": "gemini-1.5-flash",
                    "grok": "grok-1", "qwen": "qwen-plus",
                    "gemma": "gemma:2b", "deepseek": "deepseek-chat",
                    "perplexity": "pplx-7b-online",
                    "local": "local_2b", "mini": "gpt-4o-mini",
                }
                if model_arg in valid_models:
                    self._current_model_override = model_arg
                    self._console.print(f"[{GREEN}]✓ Model override: {model_arg}[/{GREEN}]")
                else:
                    self._console.print(f"[{RED}]✗ Unknown model: {model_arg}. Try :model[/{RED}]")
        else:
            self._console.print(f"[{RED}]Usage: :model or :model <name> or :model auto[/{RED}]")

    def _display_available_models(self) -> None:
        from rich.table import Table

        table = Table(
            title=f"[bold {CYAN}]Available Models[/bold {CYAN}]",
            border_style=DIM,
            header_style=f"bold {CYAN}",
            padding=(0, 1),
        )
        table.add_column("Model", style=f"bold {PURPLE}", min_width=18)
        table.add_column("Provider", style=DIM)
        table.add_column("Pricing", style=YELLOW)
        table.add_column("Latency", style=GREEN)

        models = [
            ("GPT-4o", "openai", "gpt-4o", "$0.005/$0.015 /1K"),
            ("GPT-4o-mini", "openai", "gpt-4o-mini", "$0.00015/$0.0006 /1K"),
            ("Claude Sonnet", "anthropic", "claude-sonnet", "$0.003/$0.015 /1K"),
            ("Gemini Flash", "gemini", "gemini-1.5-flash", "$0.075/$0.30 /1M"),
            ("Qwen Plus", "qwen", "qwen-plus", "$0.0008/$0.002 /1K"),
            ("DeepSeek", "deepseek", "deepseek-chat", "$0.00014/$0.00028 /1K"),
            ("Ollama", "ollama", "gemma:2b", "FREE"),
        ]
        for name, provider, model_id, pricing in models:
            latency = self._model_metrics.get_average_latency(model_id)
            lat_str = f"{latency:.0f}ms" if latency else "—"
            table.add_row(name, provider, pricing, lat_str)

        self._console.print(table)
        self._console.print()

    def _handle(self, user_input: str, mode: Mode) -> None:
        override = self._current_model_override or mode.model_override
        request = PromptRequest(prompt=user_input, model_override=override)

        # Animated thinking
        c = self._console
        if c.is_terminal:
            animate_pipeline(c)

        with c.status(f"[bold {PURPLE}]🧠 Thinking...", spinner="dots") if c.is_terminal else _noop_context():
            response = self._pipeline.process(request)

        # Model selection animation
        if c.is_terminal and response.model and not response.cached and not response.blocked:
            animate_model_selection(c, response)

        # Response
        answer_style = RED if response.blocked else GREEN
        c.print(
            Panel(
                Text(response.text, style="white" if not response.blocked else RED),
                title=f"[bold]alchemy[/bold]",
                border_style=answer_style,
                padding=(1, 2),
            )
        )

        budget_warning = self._budget_manager.update(response.cost_usd)
        self._usage_service.update_total_cost(response.cost_usd)

        if response.latency_ms and response.model:
            self._model_metrics.update(response.model.value, response.latency_ms)

        if budget_warning:
            if budget_warning.level == "warning":
                c.print(f"\n[{YELLOW}]{budget_warning.message}[/{YELLOW}]")
                enable_eco = Prompt.ask(
                    "Switch to Economic Mode?",
                    choices=["Y", "N"],
                    default="N",
                    console=c,
                )
                if enable_eco.upper() == "Y":
                    self._budget_manager.enable_economic_mode()
                    c.print(f"[{GREEN}]Economic Mode Enabled[/{GREEN}]\n")
            elif budget_warning.level in ("critical", "exhausted"):
                c.print(f"\n[bold {RED}]{budget_warning.message}[/bold {RED}]\n")

        self._dashboard.render(response, self._budget_snapshot())

        self._current_model_override = None
        c.print()


class _noop_context:
    """No-op context manager for non-terminal consoles."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        pass

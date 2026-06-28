"""Premium CLI dashboard — pipeline animation, model routing, decision report.

All rendering is synchronous Rich output — no threads, no async, no flicker.
The dashboard reads from PromptResponse / BudgetSnapshot and renders after
the pipeline completes. Animated stages are simulated from the execution trace
that the pipeline already provides.
"""

from __future__ import annotations

import time

from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from backend.app.constants.enums import BudgetState, SecurityStatus, ThreatType
from backend.app.constants.models import ModelID
from backend.app.models.budget import BudgetSnapshot
from backend.app.models.response import PromptResponse
from frontend.ui.theme import (
    BORDER_ACCENT,
    BORDER_DIM,
    BORDER_ERROR,
    BORDER_PRIMARY,
    BORDER_SUCCESS,
    BORDER_WARNING,
    CYAN,
    DIM,
    GREEN,
    PURPLE,
    RED,
    WHITE,
    YELLOW,
)

_PLACEHOLDER = "—"

_BUDGET_STYLES: dict[BudgetState, str] = {
    BudgetState.HEALTHY: GREEN,
    BudgetState.LOW: YELLOW,
    BudgetState.CRITICAL: RED,
}

_STAGE_NAMES = [
    "Fast Detector",
    "Security Scanner",
    "Task Analyzer",
    "Decision Engine",
    "Budget Manager",
    "Semantic Cache",
    "Context Manager",
    "Response Generation",
    "Cache Store",
]

_MODEL_DISPLAY: dict[str, tuple[str, str]] = {
    "llama-3.3-70b-versatile": ("Llama 3.3 70B", "Heavy reasoning & coding"),
    "llama-3.1-8b-instant": ("Llama 3.1 8B", "Fast & lightweight"),
    "qwen/qwen3-32b": ("Qwen3 32B", "Balanced power"),
    "meta-llama/llama-4-scout-17b-16e-instruct": ("Llama 4 Scout", "Instruction tuned"),
    "gpt-4o-mini": ("GPT-4o Mini", "OpenAI balanced"),
    "gpt4o": ("GPT-4o", "OpenAI flagship"),
    "local_2b": ("Local 2B", "Offline / free"),
}


def _kv(label: str, value: str | Text, label_style: str = f"bold {CYAN}") -> Table:
    t = Table.grid(padding=(0, 2))
    t.add_column(justify="right", style=label_style, min_width=18, no_wrap=True)
    t.add_column()
    t.add_row(label, value if isinstance(value, Text) else Text(value))
    return t


def _kv_table(rows: list[tuple[str, Text | str]]) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", style=f"bold {CYAN}", no_wrap=True, min_width=18)
    table.add_column(justify="left")
    for key, value in rows:
        table.add_row(key, value if isinstance(value, (Text, Table)) else Text(str(value)))
    return table


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pipeline animation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _pipeline_panel(response: PromptResponse) -> Panel:
    """Build the live pipeline execution panel from the response trace."""
    table = Table.grid(padding=(0, 1))
    table.add_column(min_width=3, justify="center")
    table.add_column(min_width=22)
    table.add_column(min_width=14, justify="right")

    completed_stages = set()
    skipped_stages = set()

    if response.fast_detector is not None:
        completed_stages.add("Fast Detector")
    if response.security is not None:
        completed_stages.add("Security Scanner")
    if response.analysis is not None:
        completed_stages.add("Task Analyzer")
        completed_stages.add("Decision Engine")
        completed_stages.add("Budget Manager")
    if response.routing is not None:
        completed_stages.add("Decision Engine")

    is_fast = response.fast_detector and response.fast_detector.is_fast_path
    is_blocked = response.blocked
    is_cached = response.cached

    if response.model is not None and not is_cached:
        completed_stages.update([
            "Semantic Cache", "Context Manager", "Response Generation", "Cache Store"
        ])

    if is_cached:
        completed_stages.add("Semantic Cache")
        skipped_stages.update(["Context Manager", "Response Generation", "Cache Store"])

    if is_fast:
        skipped_stages.update([
            "Task Analyzer", "Decision Engine", "Budget Manager",
            "Semantic Cache", "Context Manager", "Response Generation", "Cache Store",
        ])

    if is_blocked:
        skipped_stages.update([
            "Task Analyzer", "Decision Engine", "Budget Manager",
            "Semantic Cache", "Context Manager", "Response Generation", "Cache Store",
        ])

    for name in _STAGE_NAMES:
        if name in skipped_stages:
            icon = Text("○", style=DIM)
            label = Text(name, style=f"italic {DIM}")
            status = Text("SKIPPED", style=DIM)
        elif name in completed_stages:
            icon = Text("●", style=f"bold {GREEN}")
            label = Text(name, style=GREEN)
            if name == "Semantic Cache" and is_cached:
                status = Text("CACHE HIT", style=f"bold {GREEN}")
            else:
                status = Text("Completed", style=GREEN)
        else:
            icon = Text("○", style=DIM)
            label = Text(name, style=DIM)
            status = Text("—", style=DIM)

        table.add_row(icon, label, status)

    return Panel(
        table,
        title=f"[bold {PURPLE}]Pipeline[/bold {PURPLE}]",
        border_style=BORDER_PRIMARY,
        padding=(1, 2),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Model routing card
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _model_card(response: PromptResponse) -> Panel:
    """Show which model was selected and the routing reason."""
    if response.model is None:
        return Panel(
            Text("No model selected", style=DIM),
            title=f"[bold {CYAN}]Routing[/bold {CYAN}]",
            border_style=BORDER_DIM,
            padding=(1, 2),
        )

    model_val = response.model.value
    display_name, desc = _MODEL_DISPLAY.get(model_val, (model_val, ""))

    # Build candidate list showing selected vs others
    rows = Text()
    for mid in ModelID:
        if mid.value in ("gpt4o", "gpt-4o-mini", "local_2b"):
            continue
        name, _ = _MODEL_DISPLAY.get(mid.value, (mid.value, ""))
        if mid == response.model:
            rows.append(f"  ▸ {name}", style=f"bold {GREEN}")
            rows.append("  ✓ Selected\n", style=f"bold {GREEN}")
        else:
            rows.append(f"  · {name}", style=DIM)
            rows.append("  ─ skipped\n", style=DIM)

    reason = response.routing.reason if response.routing else _PLACEHOLDER
    score = ""
    if response.routing and response.routing.score_breakdown:
        sb = response.routing.score_breakdown
        score = f"Score {sb.total_score:.0f}/100 [{sb.band}]"

    detail_rows: list[tuple[str, Text | str]] = [
        ("Model", Text(display_name, style=f"bold {GREEN}")),
        ("ID", Text(model_val, style=DIM)),
    ]
    if score:
        detail_rows.append(("Score", Text(score, style=f"bold {CYAN}")))
    detail_rows.append(("Reason", Text(str(reason), style=f"italic {YELLOW}")))

    content = Group(rows, Text(), _kv_table(detail_rows))

    return Panel(
        content,
        title=f"[bold {CYAN}]Routing[/bold {CYAN}]",
        border_style=BORDER_SUCCESS if response.model else BORDER_DIM,
        padding=(1, 2),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cache panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _cache_panel(response: PromptResponse) -> Panel:
    if response.cached:
        rows: list[tuple[str, Text | str]] = [
            ("Status", Text("⚡ CACHE HIT", style=f"bold {GREEN}")),
            ("Cost Saved", Text("$0.00 (free)", style=GREEN)),
        ]
        return Panel(
            _kv_table(rows),
            title=f"[bold {GREEN}]Cache[/bold {GREEN}]",
            border_style=BORDER_SUCCESS,
            padding=(1, 2),
        )

    status = "MISS" if response.model else _PLACEHOLDER
    style = YELLOW if response.model else DIM
    return Panel(
        _kv_table([("Status", Text(f"○ {status}", style=style))]),
        title=f"[{DIM}]Cache[/{DIM}]",
        border_style=BORDER_DIM,
        padding=(1, 2),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Analysis panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _analysis_panel(response: PromptResponse) -> Panel:
    if response.analysis is not None:
        a = response.analysis
        flags = [
            name for name, on in (
                ("reasoning", a.needs_reasoning),
                ("coding", a.needs_coding),
                ("planning", a.needs_planning),
                ("context", a.needs_context),
                ("vision", a.needs_vision),
            )
            if on
        ]
        complexity_bar = _complexity_bar(a.complexity)
        rows: list[tuple[str, Text | str]] = [
            ("Task", Text(a.task_type.value.title(), style=f"bold {WHITE}")),
            ("Complexity", complexity_bar),
            ("Needs", ", ".join(flags) if flags else "—"),
        ]
    else:
        path = "fast-path" if response.fast_detector and response.fast_detector.is_fast_path else "—"
        rows = [
            ("Task", Text(path, style=DIM)),
            ("Complexity", Text(_PLACEHOLDER, style=DIM)),
            ("Needs", _PLACEHOLDER),
        ]

    return Panel(
        _kv_table(rows),
        title=f"[bold {PURPLE}]Analysis[/bold {PURPLE}]",
        border_style=BORDER_PRIMARY,
        padding=(1, 2),
    )


def _complexity_bar(value: float) -> Text:
    width = 20
    filled = int(value * width)
    if value < 0.3:
        color = GREEN
    elif value < 0.65:
        color = YELLOW
    else:
        color = RED
    bar = Text()
    bar.append("█" * filled, style=color)
    bar.append("░" * (width - filled), style=DIM)
    bar.append(f" {value:.2f}", style=color)
    return bar


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Budget panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _budget_panel(budget: BudgetSnapshot, response: PromptResponse | None = None) -> Panel:
    style = _BUDGET_STYLES.get(budget.state, WHITE)
    pct = budget.fraction_used * 100.0

    budget_bar = Text()
    bar_width = 20
    filled = int(pct / 100 * bar_width)
    budget_bar.append("█" * filled, style=style)
    budget_bar.append("░" * (bar_width - filled), style=DIM)
    budget_bar.append(f" {pct:.1f}%", style=style)

    rows: list[tuple[str, Text | str]] = [
        ("State", Text(f"💰 {budget.state.value}", style=f"bold {style}")),
        ("Usage", budget_bar),
        ("Spent", Text(f"${budget.spent_usd:.4f} / ${budget.daily_limit_usd:.2f}", style=YELLOW)),
        ("Remaining", Text(f"${budget.remaining_usd:.4f}", style=GREEN)),
    ]

    if response is not None and response.model is not None:
        rows.append(("Request Cost", Text(f"${response.cost_usd:.6f}", style=YELLOW)))
        rows.append((
            "Tokens",
            f"{response.prompt_tokens} + {response.completion_tokens} = {response.total_tokens}",
        ))

    return Panel(
        _kv_table(rows),
        title=f"[bold {style}]Budget[/bold {style}]",
        border_style=style,
        padding=(1, 2),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Security badge
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _security_badge(response: PromptResponse) -> Text:
    if response.security is None:
        return Text(_PLACEHOLDER, style=DIM)
    if response.security.status is SecurityStatus.BLOCK:
        threats = ", ".join(t.value for t in response.security.threats) or "threat"
        return Text(f"🛡 BLOCKED ({threats})", style=f"bold {RED}")
    return Text("🛡 Clear", style=GREEN)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Decision Report Table
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _decision_report(response: PromptResponse, budget: BudgetSnapshot) -> Panel:
    table = Table(
        show_header=True,
        header_style=f"bold {CYAN}",
        border_style=DIM,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Metric", style=f"bold {CYAN}", min_width=14)
    table.add_column("Value", min_width=30)

    model_val = response.model.value if response.model else _PLACEHOLDER
    display_name = _MODEL_DISPLAY.get(model_val, (model_val, ""))[0] if response.model else _PLACEHOLDER

    task = response.analysis.task_type.value.title() if response.analysis else (
        "Fast-path" if response.fast_detector and response.fast_detector.is_fast_path else "—"
    )
    complexity = f"{response.analysis.complexity:.2f}" if response.analysis else _PLACEHOLDER
    reason = response.routing.reason if response.routing else _PLACEHOLDER

    table.add_row("Task", task)
    table.add_row("Complexity", complexity)
    table.add_row("Model", display_name)
    table.add_row("Latency", f"{response.latency_ms:.1f} ms" if response.latency_ms else _PLACEHOLDER)
    table.add_row("Cost", f"${response.cost_usd:.6f}")
    table.add_row("Cache", "⚡ HIT" if response.cached else "○ MISS")
    table.add_row("Security", _security_badge(response).plain)
    table.add_row("Budget", budget.state.value)
    table.add_row("Reason", str(reason))

    return Panel(
        table,
        title=f"[bold {CYAN}]Decision Report[/bold {CYAN}]",
        border_style=BORDER_ACCENT,
        padding=(0, 1),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pipeline Summary
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _pipeline_summary(response: PromptResponse) -> Panel:
    is_fast = response.fast_detector and response.fast_detector.is_fast_path
    is_blocked = response.blocked
    is_cached = response.cached

    if is_blocked:
        termination = "Security Blocked"
    elif is_fast:
        termination = "Fast Detector Response"
    elif is_cached:
        termination = "Semantic Cache HIT"
    else:
        termination = "Full Pipeline"

    executed = 0
    skipped = 0
    for name in _STAGE_NAMES:
        if is_fast and name not in ("Fast Detector", "Security Scanner"):
            skipped += 1
        elif is_blocked and name not in ("Fast Detector", "Security Scanner"):
            skipped += 1
        elif is_cached and name in ("Context Manager", "Response Generation", "Cache Store"):
            skipped += 1
        else:
            executed += 1

    model = _MODEL_DISPLAY.get(
        response.model.value, (response.model.value, "")
    )[0] if response.model else "None"

    rows: list[tuple[str, Text | str]] = [
        ("Status", Text("✓ Success", style=f"bold {GREEN}") if not is_blocked else Text("✗ Blocked", style=f"bold {RED}")),
        ("Termination", termination),
        ("Executed", str(executed)),
        ("Skipped", str(skipped)),
        ("Latency", f"{response.latency_ms:.2f} ms"),
        ("Model", model),
        ("Cost", f"${response.cost_usd:.6f}"),
        ("Cache", "HIT" if is_cached else "MISS"),
    ]

    return Panel(
        _kv_table(rows),
        title=f"[bold {PURPLE}]Summary[/bold {PURPLE}]",
        border_style=BORDER_PRIMARY,
        padding=(1, 2),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pipeline animation (optional — for interactive console)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def animate_pipeline(console: Console) -> None:
    """Show a brief animated pipeline progress before the response arrives."""
    if not console.is_terminal:
        return

    stages = [
        "Fast Detector", "Security Scanner", "Task Analyzer",
        "Decision Engine", "Budget Manager", "Semantic Cache",
    ]
    with Progress(
        SpinnerColumn("dots", style=PURPLE),
        TextColumn("[bold {task.fields[color]}]{task.description}"),
        BarColumn(bar_width=20, complete_style=GREEN, finished_style=GREEN),
        console=console,
        transient=True,
    ) as progress:
        for stage in stages:
            task = progress.add_task(stage, total=1, color=YELLOW)
            time.sleep(0.04)
            progress.update(task, advance=1, color=GREEN)


def animate_model_selection(console: Console, response: PromptResponse) -> None:
    """Show an animated model evaluation sequence."""
    if not console.is_terminal or response.model is None:
        return

    selected = response.model.value
    candidates = [
        mid for mid in ModelID
        if mid.value not in ("gpt4o", "gpt-4o-mini", "local_2b")
    ]

    with console.status(f"[bold {YELLOW}]Searching best model...", spinner="dots") as status:
        time.sleep(0.15)
        for mid in candidates:
            name = _MODEL_DISPLAY.get(mid.value, (mid.value, ""))[0]
            status.update(f"[bold {YELLOW}]Evaluating {name}...")
            time.sleep(0.08)
            if mid.value == selected:
                break

    console.print(f"  [bold {GREEN}]✓[/bold {GREEN}] Model selected: [{GREEN}]{_MODEL_DISPLAY.get(selected, (selected, ''))[0]}[/{GREEN}]")
    console.print()


def animate_thinking(console: Console) -> None:
    """Show a thinking indicator. Call before pipeline.process()."""
    pass  # Handled inline by the session


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dashboard class (public API)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class Dashboard:
    """Renders the complete Alchemy dashboard for a processed request."""

    def __init__(self, console: Console) -> None:
        self._console = console

    def render(self, response: PromptResponse, budget: BudgetSnapshot) -> None:
        """Render the full dashboard for a completed request."""
        c = self._console

        # Pipeline + Model Routing side by side
        left = _pipeline_panel(response)
        right = _model_card(response)

        c.print(Columns([left, right], equal=True, expand=True))

        # Analysis + Cache + Budget row
        c.print(Columns([
            _analysis_panel(response),
            _cache_panel(response),
            _budget_panel(budget, response),
        ], equal=True, expand=True))

        # Decision report
        c.print(_decision_report(response, budget))

        # Pipeline summary
        c.print(_pipeline_summary(response))

    def render_placeholder(self, budget: BudgetSnapshot) -> None:
        """Render the dashboard with placeholders (no request yet)."""
        empty = PromptResponse(request_id="-", text="")
        c = self._console
        c.print(Columns([
            _budget_panel(budget),
            _cache_panel(empty),
        ], equal=True, expand=True))

"""Routing dashboard.

Renders an explainable, real-time view of how a request was processed:
selected model, latency, budget state, token usage, cost, routing reason, and
cache status. Built entirely from Rich panels so it works in any terminal.

The dashboard reads from the shared :class:`PromptResponse` model, so it shows
real pipeline values once Step 10 wires the pipeline into the CLI; before any
request is processed it renders neutral placeholders.
"""

from __future__ import annotations

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from backend.app.constants.enums import BudgetState, SecurityStatus, ThreatType
from backend.app.models.budget import BudgetSnapshot
from backend.app.models.response import PromptResponse

_PLACEHOLDER = "—"

_BUDGET_STYLES: dict[BudgetState, str] = {
    BudgetState.HEALTHY: "green",
    BudgetState.LOW: "yellow",
    BudgetState.CRITICAL: "red",
}


def _kv_table(rows: list[tuple[str, Text | str]]) -> Table:
    """Build a borderless two-column key/value table."""
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", style="bold cyan", no_wrap=True)
    table.add_column(justify="left")
    for key, value in rows:
        table.add_row(key, value)
    return table


def _security_text(response: PromptResponse) -> Text:
    """Render the security verdict with color."""
    if response.security is None:
        return Text(_PLACEHOLDER, style="dim")
    if response.security.status is SecurityStatus.BLOCK:
        threats = response.security.threats
        has_harmful = any(t is ThreatType.HARMFUL_CONTENT for t in threats)
        label = "RISK" if has_harmful else "BLOCK"
        threat_names = ", ".join(t.value for t in threats) or "threat"
        return Text(f"{label} ({threat_names})", style="bold red")
    return Text("CLEAR", style="green")


def _routing_panel(response: PromptResponse) -> Panel:
    """Panel summarizing model, cost, latency, and tokens."""
    model = response.model.value if response.model is not None else _PLACEHOLDER
    cache = "HIT" if response.cached else ("—" if response.model is None else "MISS")
    rows: list[tuple[str, Text | str]] = [
        ("Model", Text(model, style="bold white")),
        ("Latency", f"{response.latency_ms:.1f} ms" if response.latency_ms else _PLACEHOLDER),
        (
            "Tokens",
            f"{response.prompt_tokens} + {response.completion_tokens} = {response.total_tokens}",
        ),
        ("Cost", f"${response.cost_usd:.5f}"),
        ("Cache", Text(cache, style="green" if cache == "HIT" else "dim")),
        ("Security", _security_text(response)),
    ]
    return Panel(_kv_table(rows), title="[bold]Routing[/bold]", border_style="cyan", padding=(1, 2))


def _budget_panel(budget: BudgetSnapshot, response: PromptResponse | None = None) -> Panel:
    """Panel summarizing the budget snapshot with request cost details."""
    style = _BUDGET_STYLES.get(budget.state, "white")
    pct = budget.fraction_used * 100.0
    rows: list[tuple[str, Text | str]] = []

    if response is not None and response.model is not None:
        rows.append(("Model", Text(response.model.value, style="bold white")))
        rows.append(("Prompt Tokens", str(response.prompt_tokens)))
        rows.append(("Completion Tokens", str(response.completion_tokens)))
        rows.append(("Request Cost", Text(f"${response.cost_usd:.6f}", style="yellow")))
        rows.append(("", ""))

    rows.extend(
        [
            ("State", Text(budget.state.value, style=f"bold {style}")),
            (
                "Spent",
                Text(f"${budget.spent_usd:.6f} / ${budget.daily_limit_usd:.2f}", style="yellow"),
            ),
            ("Used", f"{pct:.2f}%"),
            ("Remaining", Text(f"${budget.remaining_usd:.6f}", style="yellow")),
        ]
    )
    return Panel(_kv_table(rows), title="[bold]Budget[/bold]", border_style=style, padding=(1, 2))


def _analysis_panel(response: PromptResponse) -> Panel:
    """Panel summarizing the task analysis and routing reason."""
    if response.analysis is not None:
        a = response.analysis
        flags = [
            name
            for name, on in (
                ("reasoning", a.needs_reasoning),
                ("coding", a.needs_coding),
                ("planning", a.needs_planning),
                ("context", a.needs_context),
                ("vision", a.needs_vision),
            )
            if on
        ]
        rows: list[tuple[str, Text | str]] = [
            ("Task", Text(a.task_type.value, style="bold white")),
            ("Complexity", f"{a.complexity:.2f}"),
            ("Needs", ", ".join(flags) if flags else "—"),
        ]
    else:
        path = (
            "fast-path" if response.fast_detector and response.fast_detector.is_fast_path else "—"
        )
        rows = [
            ("Task", Text(path, style="dim")),
            ("Complexity", _PLACEHOLDER),
            ("Needs", _PLACEHOLDER),
        ]

    reason = response.routing.reason if response.routing is not None else _PLACEHOLDER
    rows.append(("Reason", Text(reason, style="italic yellow")))
    return Panel(
        _kv_table(rows), title="[bold]Analysis[/bold]", border_style="magenta", padding=(1, 2)
    )


class Dashboard:
    """Renders the routing dashboard for a processed request."""

    def __init__(self, console: Console) -> None:
        self._console = console

    def render(self, response: PromptResponse, budget: BudgetSnapshot) -> None:
        """Render the dashboard panels for a completed request.

        Args:
            response: The completed pipeline response.
            budget: The budget snapshot used for the decision.
        """
        group = Group(
            _routing_panel(response),
            _analysis_panel(response),
            _budget_panel(budget, response),
        )
        self._console.print(group)

    def render_placeholder(self, budget: BudgetSnapshot) -> None:
        """Render the dashboard with neutral placeholders (no request yet)."""
        empty = PromptResponse(request_id="-", text="")
        self.render(empty, budget)

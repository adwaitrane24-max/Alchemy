"""Centralized color theme for the Alchemy CLI."""

from __future__ import annotations

from rich.style import Style
from rich.theme import Theme

# ── Brand colors ─────────────────────────────────
PURPLE = "#b388ff"
CYAN = "#18ffff"
BLUE = "#448aff"
GREEN = "#69f0ae"
YELLOW = "#ffd740"
RED = "#ff5252"
WHITE = "#e0e0e0"
DIM = "#616161"
BG = "#121212"

# ── Semantic styles ──────────────────────────────
STYLE_BRAND = Style(color=PURPLE, bold=True)
STYLE_ACCENT = Style(color=CYAN)
STYLE_SUCCESS = Style(color=GREEN)
STYLE_WARNING = Style(color=YELLOW)
STYLE_ERROR = Style(color=RED, bold=True)
STYLE_DIM = Style(color=DIM)
STYLE_LABEL = Style(color=CYAN, bold=True)
STYLE_VALUE = Style(color=WHITE)
STYLE_MUTED = Style(color=DIM, italic=True)

# ── Stage status styles ──────────────────────────
STAGE_PENDING = Style(color=DIM)
STAGE_RUNNING = Style(color=YELLOW, bold=True)
STAGE_COMPLETED = Style(color=GREEN)
STAGE_FAILED = Style(color=RED, bold=True)
STAGE_SKIPPED = Style(color=DIM, italic=True)

# ── Border styles ────────────────────────────────
BORDER_PRIMARY = PURPLE
BORDER_ACCENT = CYAN
BORDER_SUCCESS = GREEN
BORDER_WARNING = YELLOW
BORDER_ERROR = RED
BORDER_DIM = DIM

# ── Model card colors ────────────────────────────
MODEL_SELECTED = Style(color=GREEN, bold=True)
MODEL_REJECTED = Style(color=DIM, dim=True)
MODEL_CANDIDATE = Style(color=YELLOW)

ALCHEMY_THEME = Theme(
    {
        "brand": PURPLE,
        "accent": CYAN,
        "info": BLUE,
        "success": GREEN,
        "warning": YELLOW,
        "error": RED,
        "muted": DIM,
    }
)

# ── Box characters ───────────────────────────────
SEPARATOR_HEAVY = "━"
SEPARATOR_LIGHT = "─"
SEPARATOR_DOT = "┄"
ARROW_DOWN = "↓"
BULLET = "●"
BULLET_EMPTY = "○"
CHECK = "✓"
CROSS = "✗"
SKIP = "○"
DIAMOND = "◆"

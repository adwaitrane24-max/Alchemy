"""Pipeline thresholds and configuration defaults from the PRD."""

from __future__ import annotations

# ── Fast Request Detector ────────────────────
FAST_REQUEST_MAX_WORDS: int = 5
ENTROPY_THRESHOLD: float = 2.5

# ── Prompt Structurer ────────────────────────
STRUCTURER_MIN_TOKENS: int = 20
STRUCTURER_CONFIDENCE_THRESHOLD: float = 0.7
STRUCTURER_MAX_OUTPUT_MULTIPLIER: int = 2

# ── Parallel Analysis Layer ──────────────────
PARALLEL_ANALYSIS_TIMEOUT_MS: int = 200
SECURITY_TIMEOUT_MS: int = 50
TASK_ANALYZER_TIMEOUT_MS: int = 100
BUDGET_TIMEOUT_MS: int = 20
CACHE_TIMEOUT_MS: int = 150

# ── Task Analyzer ────────────────────────────
COMPLEXITY_LOW_THRESHOLD: float = 0.3
COMPLEXITY_HIGH_THRESHOLD: float = 0.65

# ── Routing Engine ───────────────────────────
VISION_REQUIRES_GPT4O: bool = True
LONG_CONTEXT_COMPLEXITY_THRESHOLD: float = 0.5

# ── Context Manager ─────────────────────────
CHUNK_SIZE_TOKENS: int = 200

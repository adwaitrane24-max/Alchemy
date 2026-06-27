"""Rule-based task analyzer.

Classifies a prompt into a :class:`TaskType`, estimates a normalized complexity
score, and flags capability requirements (reasoning, coding, planning, context,
vision) using keyword and structural heuristics. No local LLM is used.
"""

from __future__ import annotations

from loguru import logger

from backend.app.constants.enums import TaskType
from backend.app.constants.thresholds import (
    COMPLEXITY_HIGH_THRESHOLD,
    COMPLEXITY_LOW_THRESHOLD,
)
from backend.app.models.analysis import PromptAnalysis
from backend.app.models.request import PromptRequest

# Keyword signals per task type. Order matters: earlier entries win ties.
_CODING_KEYWORDS = (
    "code",
    "function",
    "bug",
    "debug",
    "python",
    "javascript",
    "java",
    "c++",
    "compile",
    "error",
    "stack trace",
    "regex",
    "api",
    "class",
    "method",
    "implement",
    "refactor",
    "algorithm",
    "sql",
    "html",
    "css",
    "syntax",
)
_REASONING_KEYWORDS = (
    "why",
    "prove",
    "explain why",
    "reason",
    "logic",
    "deduce",
    "infer",
    "analyze",
    "compare",
    "evaluate",
    "justify",
    "implication",
)
_PLANNING_KEYWORDS = (
    "plan",
    "steps",
    "roadmap",
    "strategy",
    "organize",
    "schedule",
    "outline",
    "design a",
    "break down",
    "milestones",
    "checklist",
    "workflow",
)
_CREATIVE_KEYWORDS = (
    "write a story",
    "poem",
    "creative",
    "imagine",
    "fiction",
    "song",
    "lyrics",
    "brainstorm",
    "tagline",
    "slogan",
    "narrative",
)
_QA_KEYWORDS = (
    "what is",
    "who is",
    "when did",
    "where is",
    "define",
    "how many",
    "what are",
    "which",
    "tell me about",
)
_VISION_KEYWORDS = (
    "image",
    "picture",
    "photo",
    "screenshot",
    "diagram",
    "this image",
    "the attached",
    "look at this",
    "see the",
    "ocr",
)
_CONTEXT_KEYWORDS = (
    "as we discussed",
    "earlier you said",
    "previous",
    "above",
    "the document",
    "this file",
    "the context",
    "continue",
    "follow up",
    "follow-up",
)

# Words that suggest higher reasoning depth / complexity.
_COMPLEXITY_SIGNALS = (
    "architecture",
    "distributed",
    "optimize",
    "trade-off",
    "tradeoff",
    "concurrency",
    "asynchronous",
    "scalable",
    "prove",
    "derive",
    "theorem",
    "end-to-end",
    "production",
    "multi-step",
    "comprehensive",
    "in detail",
    "step by step",
    "step-by-step",
)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    """True if any keyword appears as a substring of the (lowercased) text."""
    return any(kw in text for kw in keywords)


def _count_hits(text: str, keywords: tuple[str, ...]) -> int:
    """Count how many keywords appear in the text."""
    return sum(1 for kw in keywords if kw in text)


class TaskAnalyzer:
    """Classifies prompts by task type, complexity, and capability needs."""

    def analyze(self, request: PromptRequest) -> PromptAnalysis:
        """Analyze a prompt and return a structured classification.

        Args:
            request: The inbound prompt request.

        Returns:
            A :class:`PromptAnalysis` describing task type, complexity, and the
            capability flags relevant to routing.
        """
        text = request.prompt.lower()
        word_count = request.word_count

        needs_coding = _contains_any(text, _CODING_KEYWORDS)
        needs_planning = _contains_any(text, _PLANNING_KEYWORDS)
        needs_reasoning = _contains_any(text, _REASONING_KEYWORDS)
        needs_vision = _contains_any(text, _VISION_KEYWORDS)
        needs_context = _contains_any(text, _CONTEXT_KEYWORDS)

        task_type = self._classify_task_type(
            text,
            needs_coding=needs_coding,
            needs_planning=needs_planning,
            needs_reasoning=needs_reasoning,
        )
        complexity = self._score_complexity(
            text,
            word_count=word_count,
            needs_coding=needs_coding,
            needs_planning=needs_planning,
            needs_reasoning=needs_reasoning,
        )

        reason = (
            f"type={task_type.value}, complexity={complexity:.2f}, "
            f"coding={needs_coding}, reasoning={needs_reasoning}, "
            f"planning={needs_planning}, context={needs_context}, vision={needs_vision}"
        )
        logger.debug("Task analysis request_id={} {}", request.request_id, reason)

        return PromptAnalysis(
            task_type=task_type,
            complexity=complexity,
            needs_reasoning=needs_reasoning,
            needs_coding=needs_coding,
            needs_planning=needs_planning,
            needs_context=needs_context,
            needs_vision=needs_vision,
            reason=reason,
        )

    def _classify_task_type(
        self,
        text: str,
        *,
        needs_coding: bool,
        needs_planning: bool,
        needs_reasoning: bool,
    ) -> TaskType:
        """Pick the dominant task type using keyword hit counts."""
        scores: dict[TaskType, int] = {
            TaskType.CODING: _count_hits(text, _CODING_KEYWORDS),
            TaskType.PLANNING: _count_hits(text, _PLANNING_KEYWORDS),
            TaskType.REASONING: _count_hits(text, _REASONING_KEYWORDS),
            TaskType.CREATIVE: _count_hits(text, _CREATIVE_KEYWORDS),
            TaskType.QA: _count_hits(text, _QA_KEYWORDS),
        }
        best_type = max(scores, key=lambda t: scores[t])
        if scores[best_type] == 0:
            return TaskType.GENERAL
        return best_type

    def _score_complexity(
        self,
        text: str,
        *,
        word_count: int,
        needs_coding: bool,
        needs_planning: bool,
        needs_reasoning: bool,
    ) -> float:
        """Estimate a normalized [0, 1] complexity score from heuristics.

        Combines prompt length, explicit complexity signal words, and capability
        flags. The thresholds in :mod:`constants.thresholds` define the LOW/HIGH
        bands the routing engine later consumes.
        """
        # Length contribution: saturates around ~80 words.
        length_score = min(word_count / 80.0, 1.0)

        # Signal-word contribution: each distinct signal adds weight.
        signal_hits = _count_hits(text, _COMPLEXITY_SIGNALS)
        signal_score = min(signal_hits / 3.0, 1.0)

        # Capability contribution: reasoning/coding/planning raise the floor.
        capability_score = 0.0
        if needs_reasoning:
            capability_score += 0.34
        if needs_coding:
            capability_score += 0.33
        if needs_planning:
            capability_score += 0.33
        capability_score = min(capability_score, 1.0)

        raw = 0.35 * length_score + 0.30 * signal_score + 0.35 * capability_score
        score = round(min(max(raw, 0.0), 1.0), 4)

        # Clamp into named bands only for logging clarity; value stays continuous.
        if score < COMPLEXITY_LOW_THRESHOLD:
            band = "low"
        elif score >= COMPLEXITY_HIGH_THRESHOLD:
            band = "high"
        else:
            band = "medium"
        logger.trace("complexity={} band={}", score, band)
        return score

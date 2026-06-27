"""Rule-based fast request detector.

Identifies trivial prompts — greetings, acknowledgements, farewells, simple
arithmetic, and very short low-information inputs — that can bypass the full
analysis pipeline. Pure rules only: no model calls, no I/O.
"""

from __future__ import annotations

import re

from loguru import logger

from backend.app.constants.enums import FastRequestCategory
from backend.app.models.analysis import FastDetectorResult
from backend.app.models.request import PromptRequest

# Prompts at or below this word count (and not phrased as a question) are
# treated as low-information fragments and fast-pathed.
_TRIVIAL_WORD_COUNT = 2

# Normalized exact-match phrase tables (lowercased, punctuation-stripped).
_GREETINGS: frozenset[str] = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "yo",
        "hiya",
        "howdy",
        "greetings",
        "good morning",
        "good afternoon",
        "good evening",
        "sup",
        "hello there",
    }
)
_ACKNOWLEDGEMENTS: frozenset[str] = frozenset(
    {
        "thanks",
        "thank you",
        "thank you so much",
        "thx",
        "ty",
        "cheers",
        "much appreciated",
        "appreciate it",
        "thankyou",
    }
)
_FAREWELLS: frozenset[str] = frozenset(
    {
        "bye",
        "goodbye",
        "good bye",
        "see you",
        "see ya",
        "cya",
        "later",
        "farewell",
        "good night",
        "goodnight",
        "take care",
    }
)
_CONFIRMATIONS: frozenset[str] = frozenset(
    {
        "ok",
        "okay",
        "k",
        "yes",
        "no",
        "yep",
        "nope",
        "sure",
        "fine",
        "got it",
        "understood",
        "cool",
        "nice",
        "great",
    }
)

# Simple arithmetic: e.g. "2 + 2", "10 * 3", "what is 5 - 1". Integers/decimals
# with a single binary operator and optional surrounding whitespace/question.
_ARITHMETIC_RE = re.compile(
    r"""
    ^\s*
    (?:what(?:'s|\s+is)\s+)?      # optional "what is" / "what's"
    (-?\d+(?:\.\d+)?)             # first operand
    \s*([+\-*/x])\s*             # operator (+ - * / or x)
    (-?\d+(?:\.\d+)?)            # second operand
    \s*=?\s*\??\s*$               # optional trailing = or ?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_PUNCT_RE = re.compile(r"[!.?,]+$")


def _normalize(text: str) -> str:
    """Lowercase, collapse internal whitespace, and strip trailing punctuation."""
    collapsed = " ".join(text.lower().split())
    return _PUNCT_RE.sub("", collapsed).strip()


def _try_arithmetic(text: str) -> str | None:
    """Return the evaluated result string for a simple arithmetic prompt, else None."""
    match = _ARITHMETIC_RE.match(text.strip())
    if match is None:
        return None
    lhs, op, rhs = match.groups()
    left, right = float(lhs), float(rhs)
    op = op.lower()
    try:
        if op == "+":
            result = left + right
        elif op == "-":
            result = left - right
        elif op in {"*", "x"}:
            result = left * right
        else:  # division
            if right == 0:
                return None
            result = left / right
    except ArithmeticError:
        return None
    # Render integers without a trailing ".0".
    rendered = str(int(result)) if result.is_integer() else str(result)
    return rendered


class FastRequestDetector:
    """Classifies whether a prompt is trivial enough to skip the full pipeline."""

    def detect(self, request: PromptRequest) -> FastDetectorResult:
        """Classify a request as fast-path or full-pipeline.

        Args:
            request: The inbound prompt request.

        Returns:
            A :class:`FastDetectorResult` describing the decision. When
            ``is_fast_path`` is True a ``canned_response`` is usually provided.
        """
        normalized = _normalize(request.prompt)

        if not normalized:
            return FastDetectorResult(
                is_fast_path=True,
                category=FastRequestCategory.LOW_INFO,
                reason="Empty or punctuation-only prompt",
                canned_response="Could you say a bit more about what you need?",
            )

        # 1. Simple arithmetic — deterministic, answerable without a model.
        arithmetic = _try_arithmetic(request.prompt)
        if arithmetic is not None:
            logger.debug("Fast-path: arithmetic '{}' = {}", request.prompt, arithmetic)
            return FastDetectorResult(
                is_fast_path=True,
                category=FastRequestCategory.LOW_INFO,
                reason="Simple arithmetic expression",
                canned_response=arithmetic,
            )

        # 2. Exact-match conversational phrases.
        phrase_tables: tuple[tuple[frozenset[str], FastRequestCategory, str, str], ...] = (
            (
                _GREETINGS,
                FastRequestCategory.GREETING,
                "Greeting",
                "Hello! How can I help you today?",
            ),
            (
                _ACKNOWLEDGEMENTS,
                FastRequestCategory.ACKNOWLEDGEMENT,
                "Acknowledgement",
                "You're welcome!",
            ),
            (_FAREWELLS, FastRequestCategory.FILLER, "Farewell", "Goodbye! Take care."),
            (_CONFIRMATIONS, FastRequestCategory.CONFIRMATION, "Confirmation", "Got it."),
        )
        for table, category, label, canned in phrase_tables:
            if normalized in table:
                logger.debug("Fast-path: {} ('{}')", label, normalized)
                return FastDetectorResult(
                    is_fast_path=True,
                    category=category,
                    reason=label,
                    canned_response=canned,
                )

        # 3. Very short, low-information prompts. Short questions may still need
        # the full pipeline, so only non-question fragments are fast-pathed.
        if request.word_count <= _TRIVIAL_WORD_COUNT and "?" not in request.prompt:
            return FastDetectorResult(
                is_fast_path=True,
                category=FastRequestCategory.LOW_INFO,
                reason=f"Very short prompt ({request.word_count} words)",
                canned_response="Could you give me a little more detail?",
            )

        return FastDetectorResult(
            is_fast_path=False,
            category=None,
            reason="Non-trivial prompt requires full pipeline",
        )

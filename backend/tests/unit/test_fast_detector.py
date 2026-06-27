"""Unit tests for the rule-based fast request detector."""

from __future__ import annotations

import pytest

from backend.app.models.request import PromptRequest
from backend.app.modules.fast_detector import FastRequestDetector


@pytest.fixture
def detector() -> FastRequestDetector:
    return FastRequestDetector()


@pytest.mark.parametrize("text", ["hello", "Hi!", "hey there", "good morning"])
def test_greetings_are_fast_path(detector: FastRequestDetector, text: str) -> None:
    result = detector.detect(PromptRequest(prompt=text))
    assert result.is_fast_path is True
    assert result.canned_response


@pytest.mark.parametrize("text", ["thanks", "thank you so much", "ty"])
def test_acknowledgements_are_fast_path(detector: FastRequestDetector, text: str) -> None:
    assert detector.detect(PromptRequest(prompt=text)).is_fast_path is True


@pytest.mark.parametrize("text", ["bye", "goodbye", "see you"])
def test_farewells_are_fast_path(detector: FastRequestDetector, text: str) -> None:
    assert detector.detect(PromptRequest(prompt=text)).is_fast_path is True


@pytest.mark.parametrize(
    ("text", "expected"),
    [("2 + 2", "4"), ("what is 10 * 3", "30"), ("9 / 3", "3"), ("7 - 10", "-3")],
)
def test_simple_arithmetic_is_evaluated(
    detector: FastRequestDetector, text: str, expected: str
) -> None:
    result = detector.detect(PromptRequest(prompt=text))
    assert result.is_fast_path is True
    assert result.canned_response == expected


def test_division_by_zero_is_not_fast_path(detector: FastRequestDetector) -> None:
    result = detector.detect(PromptRequest(prompt="5 / 0"))
    assert result.is_fast_path is False


def test_complex_prompt_requires_full_pipeline(detector: FastRequestDetector) -> None:
    result = detector.detect(
        PromptRequest(prompt="Explain how a hash map handles collisions in detail.")
    )
    assert result.is_fast_path is False


def test_short_question_is_not_fast_path(detector: FastRequestDetector) -> None:
    # Short but a genuine question -> should go through the full pipeline.
    result = detector.detect(PromptRequest(prompt="why recursion?"))
    assert result.is_fast_path is False

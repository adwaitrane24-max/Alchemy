"""Unit tests for the rule-based task analyzer."""

from __future__ import annotations

import pytest

from backend.app.constants.enums import TaskType
from backend.app.models.request import PromptRequest
from backend.app.modules.task_analyzer import TaskAnalyzer


@pytest.fixture
def analyzer() -> TaskAnalyzer:
    return TaskAnalyzer()


def test_coding_prompt_is_classified(analyzer: TaskAnalyzer) -> None:
    result = analyzer.analyze(PromptRequest(prompt="Write a Python function to debug this code."))
    assert result.task_type is TaskType.CODING
    assert result.needs_coding is True


def test_planning_prompt_is_classified(analyzer: TaskAnalyzer) -> None:
    result = analyzer.analyze(
        PromptRequest(prompt="Give me a step by step plan and roadmap to launch.")
    )
    assert result.task_type is TaskType.PLANNING
    assert result.needs_planning is True


def test_reasoning_prompt_flags_reasoning(analyzer: TaskAnalyzer) -> None:
    result = analyzer.analyze(PromptRequest(prompt="Why does this prove the theorem? Justify."))
    assert result.needs_reasoning is True


def test_vision_prompt_flags_vision(analyzer: TaskAnalyzer) -> None:
    result = analyzer.analyze(PromptRequest(prompt="Look at this image and describe the diagram."))
    assert result.needs_vision is True


def test_general_prompt_defaults_to_general(analyzer: TaskAnalyzer) -> None:
    result = analyzer.analyze(PromptRequest(prompt="Hmm okay then sounds alright to me."))
    assert result.task_type is TaskType.GENERAL


def test_complexity_is_bounded_and_higher_for_complex(analyzer: TaskAnalyzer) -> None:
    simple = analyzer.analyze(PromptRequest(prompt="hello there"))
    complex_ = analyzer.analyze(
        PromptRequest(
            prompt=(
                "Design a scalable distributed architecture and prove the "
                "concurrency guarantees step by step in detail."
            )
        )
    )
    assert 0.0 <= simple.complexity <= 1.0
    assert 0.0 <= complex_.complexity <= 1.0
    assert complex_.complexity > simple.complexity

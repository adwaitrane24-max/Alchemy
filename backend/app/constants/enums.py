"""Enumerations used across the Alchemy pipeline."""

from __future__ import annotations

from enum import StrEnum


class BudgetState(StrEnum):
    """Budget manager state machine states."""

    HEALTHY = "HEALTHY"
    LOW = "LOW"
    CRITICAL = "CRITICAL"


class SecurityStatus(StrEnum):
    """Security module scan result."""

    CLEAR = "CLEAR"
    BLOCK = "BLOCK"


class ThreatType(StrEnum):
    """Categories of security threats detected."""

    INJECTION = "injection"
    JAILBREAK = "jailbreak"
    LEAKAGE = "leakage"
    ROLE_OVERRIDE = "role_override"
    EXFILTRATION = "exfiltration"


class TaskType(StrEnum):
    """Prompt task classification categories."""

    CODING = "coding"
    REASONING = "reasoning"
    PLANNING = "planning"
    QA = "qa"
    CREATIVE = "creative"
    GENERAL = "general"
    SUMMARIZATION = "summarization"
    EXTRACTION = "extraction"
    EMBEDDING = "embedding"
    MATH = "math"
    CONVERSATION = "conversation"
    CLASSIFICATION = "classification"


class FastRequestCategory(StrEnum):
    """Categories of fast-path trivial requests."""

    GREETING = "greeting"
    ACKNOWLEDGEMENT = "acknowledgement"
    CONFIRMATION = "confirmation"
    FILLER = "filler"
    LOW_INFO = "low_info"


class RoutingAction(StrEnum):
    """Actions the routing engine can take."""

    MODEL_CALL = "MODEL_CALL"
    CACHE_RETURN = "CACHE_RETURN"
    BLOCK = "BLOCK"


class ContextStrategy(StrEnum):
    """Context assembly strategies based on budget state."""

    CHUNKS = "chunks"
    SUMMARY = "summary"

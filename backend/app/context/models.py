"""Data models for the Context Manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


class ChunkType(StrEnum):
    """Types of semantic chunks."""

    USER_QUERY = "user_query"
    MODEL_RESPONSE = "model_response"
    SESSION_SUMMARY = "session_summary"
    SYSTEM = "system"


class Speaker(StrEnum):
    """Conversation participants."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class SemanticChunk:
    """A semantically coherent chunk of conversation."""

    chunk_id: str = field(default_factory=lambda: uuid4().hex[:16])
    session_id: str = ""
    text: str = ""
    embedding: list[float] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    token_count: int = 0
    topic: str = ""
    summary: str = ""
    importance_score: float = 0.5
    chunk_type: ChunkType = ChunkType.USER_QUERY
    speaker: Speaker = Speaker.USER
    model_used: str = ""

    def to_metadata(self) -> dict:
        """Convert to metadata dict for vector storage."""
        return {
            "chunk_id": self.chunk_id,
            "session_id": self.session_id,
            "text": self.text,
            "timestamp": self.timestamp,
            "token_count": self.token_count,
            "topic": self.topic,
            "summary": self.summary,
            "importance_score": self.importance_score,
            "chunk_type": self.chunk_type.value,
            "speaker": self.speaker.value,
            "model_used": self.model_used,
        }

    @classmethod
    def from_metadata(cls, metadata: dict, embedding: list[float] | None = None) -> SemanticChunk:
        """Reconstruct from metadata dict."""
        return cls(
            chunk_id=metadata.get("chunk_id", uuid4().hex[:16]),
            session_id=metadata.get("session_id", ""),
            text=metadata.get("text", ""),
            embedding=embedding or [],
            timestamp=metadata.get("timestamp", datetime.now(UTC).isoformat()),
            token_count=metadata.get("token_count", 0),
            topic=metadata.get("topic", ""),
            summary=metadata.get("summary", ""),
            importance_score=metadata.get("importance_score", 0.5),
            chunk_type=ChunkType(metadata.get("chunk_type", "user_query")),
            speaker=Speaker(metadata.get("speaker", "user")),
            model_used=metadata.get("model_used", ""),
        )


@dataclass
class RankedChunk:
    """A chunk with its computed relevance score."""

    chunk: SemanticChunk
    relevance_score: float = 0.0
    similarity_score: float = 0.0
    recency_score: float = 0.0
    continuity_score: float = 0.0


@dataclass
class SessionSummary:
    """Structured summary of a completed session."""

    session_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    project_info: str = ""
    completed_work: str = ""
    pending_work: str = ""
    key_decisions: str = ""
    user_preferences: str = ""
    architecture_notes: str = ""
    goals: str = ""
    constraints: str = ""
    total_queries: int = 0
    models_used: list[str] = field(default_factory=list)
    topics_discussed: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        """Serialize summary to a readable text block."""
        sections = []
        if self.project_info:
            sections.append(f"Project: {self.project_info}")
        if self.completed_work:
            sections.append(f"Completed: {self.completed_work}")
        if self.pending_work:
            sections.append(f"Pending: {self.pending_work}")
        if self.key_decisions:
            sections.append(f"Decisions: {self.key_decisions}")
        if self.user_preferences:
            sections.append(f"Preferences: {self.user_preferences}")
        if self.architecture_notes:
            sections.append(f"Architecture: {self.architecture_notes}")
        if self.goals:
            sections.append(f"Goals: {self.goals}")
        if self.constraints:
            sections.append(f"Constraints: {self.constraints}")
        if self.topics_discussed:
            sections.append(f"Topics: {', '.join(self.topics_discussed)}")
        return "\n".join(sections) if sections else "No session summary available."


@dataclass
class ContextResult:
    """Result of context preparation for an LLM call."""

    system_prompt: str = ""
    context_text: str = ""
    user_query: str = ""
    chunks_used: int = 0
    chunks_retrieved: int = 0
    total_context_tokens: int = 0
    strategy_used: str = "chunks"
    session_restored: bool = False

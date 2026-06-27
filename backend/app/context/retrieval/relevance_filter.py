"""Context Relevance Filter — ranks and filters retrieved chunks.

Pinecone returns candidate chunks by embedding similarity alone. This filter
applies a multi-signal ranking (similarity, recency, continuity, importance)
and forwards only the highest-scoring chunks to the Prompt Builder.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from loguru import logger

from backend.app.context.models import RankedChunk, SemanticChunk


class ContextRelevanceFilter:
    """Configurable multi-signal ranking engine for retrieved chunks."""

    def __init__(
        self,
        similarity_weight: float = 0.4,
        recency_weight: float = 0.25,
        continuity_weight: float = 0.2,
        importance_weight: float = 0.15,
        min_relevance_score: float = 0.1,
    ) -> None:
        self._w_sim = similarity_weight
        self._w_rec = recency_weight
        self._w_cont = continuity_weight
        self._w_imp = importance_weight
        self._min_score = min_relevance_score

    def rank(
        self,
        candidates: list[tuple[SemanticChunk, float]],
        max_chunks: int = 10,
        current_session_id: str = "",
    ) -> list[RankedChunk]:
        """Rank candidate chunks and return the top-scoring ones."""
        start = time.perf_counter()

        if not candidates:
            return []

        now = datetime.now(UTC)
        ranked: list[RankedChunk] = []

        for chunk, similarity in candidates:
            recency = self._recency_score(chunk.timestamp, now)
            continuity = 1.0 if chunk.session_id == current_session_id else 0.3
            importance = chunk.importance_score

            relevance = (
                self._w_sim * similarity
                + self._w_rec * recency
                + self._w_cont * continuity
                + self._w_imp * importance
            )

            if relevance >= self._min_score:
                ranked.append(RankedChunk(
                    chunk=chunk,
                    relevance_score=relevance,
                    similarity_score=similarity,
                    recency_score=recency,
                    continuity_score=continuity,
                ))

        ranked.sort(key=lambda r: r.relevance_score, reverse=True)
        result = ranked[:max_chunks]

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "Relevance filter: {} candidates → {} selected in {:.1f}ms",
            len(candidates),
            len(result),
            elapsed_ms,
        )
        return result

    @staticmethod
    def _recency_score(timestamp_str: str, now: datetime) -> float:
        """Compute a recency score (0-1) based on time elapsed."""
        try:
            chunk_time = datetime.fromisoformat(timestamp_str)
            age_seconds = (now - chunk_time).total_seconds()
            if age_seconds <= 0:
                return 1.0
            if age_seconds > 86400:
                return 0.1
            return max(0.1, 1.0 - (age_seconds / 86400))
        except (ValueError, TypeError):
            return 0.5

"""Unified Memory Service — Repository Pattern abstraction over vector storage.

The Context Manager interacts ONLY with this service. The underlying vector DB
(local or Pinecone) is an implementation detail hidden behind the adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from loguru import logger

from backend.app.context.models import SemanticChunk, SessionSummary, ChunkType, Speaker
from backend.app.context.memory.vector_store_adapter import VectorStoreAdapter
from backend.app.embeddings.engine import EmbeddingEngine


class UnifiedMemoryService:
    """Repository-pattern service abstracting all persistent memory operations."""

    def __init__(
        self,
        vector_adapter: VectorStoreAdapter,
        embedding_engine: EmbeddingEngine,
    ) -> None:
        self._adapter = vector_adapter
        self._embedding = embedding_engine

    def store_chunk(self, chunk: SemanticChunk) -> str:
        """Store a semantic chunk with its embedding in the vector store."""
        if not chunk.embedding:
            chunk.embedding = self._embedding.encode(chunk.text)

        self._adapter.upsert(
            chunk_id=chunk.chunk_id,
            embedding=chunk.embedding,
            metadata=chunk.to_metadata(),
        )
        logger.debug("Stored chunk {} ({} tokens)", chunk.chunk_id, chunk.token_count)
        return chunk.chunk_id

    def store_chunks(self, chunks: list[SemanticChunk]) -> list[str]:
        """Store multiple chunks."""
        return [self.store_chunk(c) for c in chunks]

    def retrieve_chunks(
        self,
        query_text: str,
        top_k: int = 10,
        session_id: str | None = None,
    ) -> list[tuple[SemanticChunk, float]]:
        """Retrieve top-K semantically similar chunks for a query."""
        query_embedding = self._embedding.encode(query_text)

        filter_dict = {"session_id": session_id} if session_id else None
        results = self._adapter.query(query_embedding, top_k=top_k, filter_dict=filter_dict)

        chunks_with_scores: list[tuple[SemanticChunk, float]] = []
        for r in results:
            chunk = SemanticChunk.from_metadata(r.metadata)
            chunks_with_scores.append((chunk, r.similarity))

        logger.debug(
            "Retrieved {} chunks for query (top_k={})",
            len(chunks_with_scores),
            top_k,
        )
        return chunks_with_scores

    def update_chunk(self, chunk: SemanticChunk) -> None:
        """Update an existing chunk in storage."""
        if not chunk.embedding:
            chunk.embedding = self._embedding.encode(chunk.text)
        self._adapter.upsert(
            chunk_id=chunk.chunk_id,
            embedding=chunk.embedding,
            metadata=chunk.to_metadata(),
        )

    def delete_chunk(self, chunk_id: str) -> None:
        """Delete a specific chunk."""
        self._adapter.delete(chunk_id)
        logger.debug("Deleted chunk {}", chunk_id)

    def delete_session(self, session_id: str) -> None:
        """Delete all chunks belonging to a session."""
        self._adapter.delete_by_session(session_id)
        logger.debug("Deleted all chunks for session {}", session_id)

    def generate_session_summary(
        self,
        session_id: str,
        chunks: list[SemanticChunk],
    ) -> SessionSummary:
        """Generate a structured session summary from conversation chunks."""
        topics: list[str] = []
        models: set[str] = set()
        user_texts: list[str] = []
        assistant_texts: list[str] = []

        for chunk in chunks:
            if chunk.topic and chunk.topic not in topics:
                topics.append(chunk.topic)
            if chunk.model_used:
                models.add(chunk.model_used)
            if chunk.speaker == Speaker.USER:
                user_texts.append(chunk.text)
            elif chunk.speaker == Speaker.ASSISTANT:
                assistant_texts.append(chunk.text)

        summary = SessionSummary(
            session_id=session_id,
            timestamp=datetime.now(UTC).isoformat(),
            project_info=f"Session with {len(chunks)} exchanges",
            completed_work=f"Processed {len(user_texts)} user queries",
            topics_discussed=topics,
            models_used=list(models),
            total_queries=len(user_texts),
        )

        logger.debug(
            "Generated session summary: {} topics, {} models",
            len(topics),
            len(models),
        )
        return summary

    def store_session_summary(self, summary: SessionSummary) -> str:
        """Store a session summary as a special chunk in unified memory."""
        chunk = SemanticChunk(
            session_id=summary.session_id,
            text=summary.to_text(),
            token_count=len(summary.to_text()) // 4,
            topic="session_summary",
            chunk_type=ChunkType.SESSION_SUMMARY,
            speaker=Speaker.SYSTEM,
            timestamp=summary.timestamp,
        )
        return self.store_chunk(chunk)

    def restore_session(self, session_id: str) -> list[SemanticChunk]:
        """Restore chunks from a previous session."""
        results = self._adapter.query(
            embedding=self._embedding.encode(f"session {session_id}"),
            top_k=100,
            filter_dict={"session_id": session_id},
        )
        chunks = [SemanticChunk.from_metadata(r.metadata) for r in results]
        logger.info("Restored {} chunks for session {}", len(chunks), session_id)
        return chunks

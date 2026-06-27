"""Semantic chunking engine.

Splits conversation text into semantically coherent chunks of ~200-300 tokens
based on sentence boundaries and topic continuity rather than fixed message counts.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from loguru import logger

from backend.app.context.models import ChunkType, SemanticChunk, Speaker

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_CHARS_PER_TOKEN = 4
_TARGET_MIN_TOKENS = 200
_TARGET_MAX_TOKENS = 300


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


class SemanticChunker:
    """Splits text into semantic chunks of configurable token size."""

    def __init__(
        self,
        min_tokens: int = _TARGET_MIN_TOKENS,
        max_tokens: int = _TARGET_MAX_TOKENS,
    ) -> None:
        self._min_tokens = min_tokens
        self._max_tokens = max_tokens

    def chunk_message(
        self,
        text: str,
        session_id: str,
        speaker: Speaker,
        chunk_type: ChunkType = ChunkType.USER_QUERY,
        model_used: str = "",
        topic: str = "",
    ) -> list[SemanticChunk]:
        """Split a single message into semantic chunks."""
        text = text.strip()
        if not text:
            return []

        token_count = _estimate_tokens(text)

        if token_count <= self._max_tokens:
            chunk = SemanticChunk(
                session_id=session_id,
                text=text,
                token_count=token_count,
                topic=topic,
                chunk_type=chunk_type,
                speaker=speaker,
                model_used=model_used,
                timestamp=datetime.now(UTC).isoformat(),
            )
            logger.debug("Created single chunk: {} tokens", token_count)
            return [chunk]

        sentences = _SENTENCE_RE.split(text)
        chunks: list[SemanticChunk] = []
        current_sentences: list[str] = []
        current_tokens = 0

        for sentence in sentences:
            s_tokens = _estimate_tokens(sentence)

            if current_tokens + s_tokens > self._max_tokens and current_sentences:
                chunk_text = " ".join(current_sentences)
                chunks.append(SemanticChunk(
                    session_id=session_id,
                    text=chunk_text,
                    token_count=_estimate_tokens(chunk_text),
                    topic=topic,
                    chunk_type=chunk_type,
                    speaker=speaker,
                    model_used=model_used,
                    timestamp=datetime.now(UTC).isoformat(),
                ))
                current_sentences = []
                current_tokens = 0

            current_sentences.append(sentence)
            current_tokens += s_tokens

        if current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append(SemanticChunk(
                session_id=session_id,
                text=chunk_text,
                token_count=_estimate_tokens(chunk_text),
                topic=topic,
                chunk_type=chunk_type,
                speaker=speaker,
                model_used=model_used,
                timestamp=datetime.now(UTC).isoformat(),
            ))

        logger.debug("Created {} chunks from {} tokens", len(chunks), token_count)
        return chunks

    def chunk_conversation(
        self,
        messages: list[tuple[Speaker, str, str]],
        session_id: str,
    ) -> list[SemanticChunk]:
        """Chunk a series of (speaker, text, model_used) messages."""
        all_chunks: list[SemanticChunk] = []
        for speaker, text, model in messages:
            chunk_type = (
                ChunkType.USER_QUERY if speaker == Speaker.USER else ChunkType.MODEL_RESPONSE
            )
            all_chunks.extend(
                self.chunk_message(text, session_id, speaker, chunk_type, model_used=model)
            )
        return all_chunks

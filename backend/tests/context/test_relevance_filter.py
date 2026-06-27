"""Unit tests for ContextRelevanceFilter."""

import pytest
from datetime import UTC, datetime

from backend.app.context.retrieval.relevance_filter import ContextRelevanceFilter
from backend.app.context.models import SemanticChunk, Speaker


class TestContextRelevanceFilter:
    def setup_method(self):
        self.filter = ContextRelevanceFilter()

    def test_empty_candidates(self):
        result = self.filter.rank([])
        assert result == []

    def test_ranks_by_relevance(self):
        now = datetime.now(UTC).isoformat()
        c1 = SemanticChunk(session_id="s1", text="high sim", timestamp=now, speaker=Speaker.USER)
        c2 = SemanticChunk(session_id="s1", text="low sim", timestamp=now, speaker=Speaker.USER)
        candidates = [(c1, 0.9), (c2, 0.3)]
        ranked = self.filter.rank(candidates, max_chunks=2, current_session_id="s1")
        assert len(ranked) == 2
        assert ranked[0].similarity_score > ranked[1].similarity_score

    def test_max_chunks_limit(self):
        now = datetime.now(UTC).isoformat()
        candidates = [
            (SemanticChunk(session_id="s1", text=f"chunk-{i}", timestamp=now, speaker=Speaker.USER), 0.5)
            for i in range(10)
        ]
        ranked = self.filter.rank(candidates, max_chunks=3)
        assert len(ranked) == 3

    def test_current_session_boost(self):
        now = datetime.now(UTC).isoformat()
        c_current = SemanticChunk(session_id="current", text="current session", timestamp=now, speaker=Speaker.USER)
        c_other = SemanticChunk(session_id="other", text="other session", timestamp=now, speaker=Speaker.USER)
        candidates = [(c_current, 0.5), (c_other, 0.5)]
        ranked = self.filter.rank(candidates, current_session_id="current")
        assert ranked[0].chunk.session_id == "current"
        assert ranked[0].continuity_score > ranked[1].continuity_score

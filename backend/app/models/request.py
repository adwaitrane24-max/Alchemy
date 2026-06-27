"""Inbound request model — the entry point of the Alchemy pipeline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class PromptRequest(BaseModel):
    """A single user request flowing into the gateway.

    This is the canonical input every pipeline stage receives. It carries the
    raw prompt text plus lightweight metadata used for routing and auditing.
    """

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    prompt: str = Field(min_length=1, description="Raw user prompt text.")
    session_id: str | None = Field(
        default=None, description="Optional conversation/session identifier."
    )
    model_override: str | None = Field(
        default=None, description="Optional caller-forced model id (bypasses routing)."
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def word_count(self) -> int:
        """Number of whitespace-delimited words in the prompt."""
        return len(self.prompt.split())

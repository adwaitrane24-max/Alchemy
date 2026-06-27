"""Model identifiers and cost constants as defined in the PRD."""

from __future__ import annotations

from enum import StrEnum


class ModelID(StrEnum):
    """Supported model identifiers for routing."""

    # Mozilla Otari models (primary routing targets)
    GEMMA_3_27B = "mozilla/gemma-3-27b-it"
    LLAMA_3_3_70B = "mozilla/llama-3.3-70b-instruct"
    QWEN3_32B = "mozilla/qwen3-32b"
    HERMES_4_70B = "mozilla/hermes-4-70b"
    QWEN3_EMBEDDING_8B = "mozilla/qwen3-embedding-8b"

    # Groq models (free API — used as fast-path / budget fallback)
    GROQ_LLAMA2_13B = "groq/llama2-13b-chat"
    GROQ_MIXTRAL = "groq/mixtral-8x7b-32768"
    GROQ_LLAMA2_70B = "groq/llama2-70b-chat"

    # Legacy (kept for backwards compatibility)
    LOCAL_2B = "local_2b"
    GPT4O_MINI = "gpt4o_mini"
    GPT4O = "gpt4o"


# Cost per 1K tokens (USD) — Mozilla Otari pricing via gateway
MODEL_COSTS: dict[str, dict[str, float]] = {
    # Mozilla Otari
    ModelID.GEMMA_3_27B: {"input": 0.00010, "output": 0.00020},
    ModelID.LLAMA_3_3_70B: {"input": 0.00035, "output": 0.00080},
    ModelID.QWEN3_32B: {"input": 0.00030, "output": 0.00060},
    ModelID.HERMES_4_70B: {"input": 0.00040, "output": 0.00090},
    ModelID.QWEN3_EMBEDDING_8B: {"input": 0.00005, "output": 0.0},
    # Groq (free)
    ModelID.GROQ_LLAMA2_13B: {"input": 0.0, "output": 0.0},
    ModelID.GROQ_MIXTRAL: {"input": 0.0, "output": 0.0},
    ModelID.GROQ_LLAMA2_70B: {"input": 0.0, "output": 0.0},
    # Legacy
    ModelID.LOCAL_2B: {"input": 0.0, "output": 0.0},
    ModelID.GPT4O_MINI: {"input": 0.00015, "output": 0.00060},
    ModelID.GPT4O: {"input": 0.00250, "output": 0.01000},
}

# Fallback chain: primary → fallback1 → fallback2
MODEL_FALLBACK_CHAIN: dict[str, list[str]] = {
    # Mozilla Otari fallbacks — degrade gracefully within the Otari fleet
    ModelID.GEMMA_3_27B: [ModelID.GROQ_MIXTRAL],
    ModelID.LLAMA_3_3_70B: [ModelID.QWEN3_32B, ModelID.GEMMA_3_27B],
    ModelID.QWEN3_32B: [ModelID.GEMMA_3_27B],
    ModelID.HERMES_4_70B: [ModelID.LLAMA_3_3_70B, ModelID.GEMMA_3_27B],
    ModelID.QWEN3_EMBEDDING_8B: [ModelID.GEMMA_3_27B],
    # Groq fallbacks
    ModelID.GROQ_LLAMA2_13B: [ModelID.GROQ_MIXTRAL],
    ModelID.GROQ_MIXTRAL: [ModelID.GROQ_LLAMA2_70B],
    ModelID.GROQ_LLAMA2_70B: [ModelID.GROQ_MIXTRAL],
    # Legacy
    ModelID.GPT4O: [ModelID.GPT4O_MINI, ModelID.LOCAL_2B],
    ModelID.GPT4O_MINI: [ModelID.LOCAL_2B],
    ModelID.LOCAL_2B: [],
}

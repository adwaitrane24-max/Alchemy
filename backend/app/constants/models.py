"""Model identifiers and cost constants — mapped to real Otari gateway model names."""

from __future__ import annotations

from enum import StrEnum


class ModelID(StrEnum):
    """Supported model identifiers for routing via Mozilla Otari."""

    # Mozilla Otari models (routed through Otari gateway to Groq backend)
    LLAMA_3_3_70B = "llama-3.3-70b-versatile"
    LLAMA_3_1_8B = "llama-3.1-8b-instant"
    QWEN3_32B = "qwen/qwen3-32b"
    LLAMA_4_SCOUT = "meta-llama/llama-4-scout-17b-16e-instruct"

    # Legacy (kept for backwards compatibility)
    GPT4O_MINI = "gpt-4o-mini"
    GPT4O = "gpt4o"
    LOCAL_2B = "local_2b"


# Cost per 1K tokens (USD) — Groq models are free through Otari
MODEL_COSTS: dict[str, dict[str, float]] = {
    ModelID.LLAMA_3_3_70B: {"input": 0.0, "output": 0.0},
    ModelID.LLAMA_3_1_8B: {"input": 0.0, "output": 0.0},
    ModelID.QWEN3_32B: {"input": 0.0, "output": 0.0},
    ModelID.LLAMA_4_SCOUT: {"input": 0.0, "output": 0.0},
    ModelID.GPT4O_MINI: {"input": 0.00015, "output": 0.00060},
    ModelID.GPT4O: {"input": 0.00250, "output": 0.01000},
    ModelID.LOCAL_2B: {"input": 0.0, "output": 0.0},
}

# Fallback chain: primary → fallback1 → fallback2
MODEL_FALLBACK_CHAIN: dict[str, list[str]] = {
    ModelID.LLAMA_3_3_70B: [ModelID.QWEN3_32B, ModelID.LLAMA_3_1_8B],
    ModelID.QWEN3_32B: [ModelID.LLAMA_3_3_70B, ModelID.LLAMA_3_1_8B],
    ModelID.LLAMA_4_SCOUT: [ModelID.LLAMA_3_3_70B, ModelID.LLAMA_3_1_8B],
    ModelID.LLAMA_3_1_8B: [ModelID.LLAMA_4_SCOUT],
    ModelID.GPT4O_MINI: [ModelID.LLAMA_3_1_8B],
    ModelID.GPT4O: [ModelID.GPT4O_MINI, ModelID.LLAMA_3_3_70B],
    ModelID.LOCAL_2B: [],
}

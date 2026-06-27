# Alchemy Backend

The core gateway engine for Alchemy — handles prompt analysis, routing, caching, security, and model dispatch.

## Architecture

```
app/
├── api/           → FastAPI route definitions
├── core/          → Configuration, logging, lifecycle
├── gateway/       → Mozilla Otari integration
├── services/      → Pipeline orchestration
├── modules/       → Pipeline modules
│   ├── fast_detector/   → Trivial prompt bypass
│   ├── task_analyzer/   → Prompt classification
│   ├── budget/          → Cost tracking & enforcement
│   ├── cache/           → Semantic cache (FAISS)
│   └── parallel/        → Concurrent analysis orchestration
├── models/        → Pydantic data models
├── storage/       → SQLite + FAISS persistence
├── security/      → Threat detection rules
├── context/       → Conversation history management
├── routing/       → Model selection engine
├── embeddings/    → Vector generation
├── prompts/       → Prompt optimization
├── analytics/     → Learning layer
├── schemas/       → API request/response schemas
├── constants/     → Thresholds, enums, error codes
├── exceptions/    → Custom exception hierarchy
├── config/        → Settings management
├── utils/         → Shared helpers
└── cli/           → Management commands
```

## Running

```bash
# Development server
make run-backend

# CLI
make run-cli
```

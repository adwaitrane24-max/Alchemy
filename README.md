# Alchemy

**Adaptive Cost-Aware AI Gateway powered by Mozilla Otari**

> *The right model, at the right cost, at the right time — every time.*

---

## What is Alchemy?

Alchemy is an intelligent routing and optimization layer that sits between users and multiple LLMs. Before any model receives a query, Alchemy analyzes, optimizes, caches, and routes it to the most cost-effective model — with full transparency.

### Key Capabilities

- **Fast Request Detection** — Bypass expensive pipelines for trivial queries
- **Security Screening** — Block prompt injection, jailbreaks, and leakage attempts
- **Adaptive Prompt Structuring** — Improve prompt clarity when beneficial
- **Task Analysis** — Classify complexity and capability requirements
- **Budget Management** — Real-time cost tracking and enforcement
- **Semantic Caching** — Avoid redundant API calls via embedding similarity
- **Explainable Routing** — Every decision is transparent and auditable
- **Context Management** — Budget-aware conversation history optimization
- **Learning Layer** — Analytics for continuous optimization

## Tech Stack

| Component | Technology |
|---|---|
| Runtime | Python 3.12 |
| API Framework | FastAPI |
| CLI | Typer + Rich |
| Local LLM | Gemma 2B via Ollama |
| AI Gateway | Mozilla Otari |
| Embeddings | sentence-transformers |
| Vector Search | FAISS |
| Database | SQLite |
| Voice STT | Smallest.ai |
| Validation | Pydantic v2 |
| Logging | Loguru |
| Package Manager | uv |

## Quick Start

```bash
# Clone the repository
git clone <repository-url>
cd Alchemy

# Create virtual environment
uv venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate      # Windows

# Install dependencies
make install-dev

# Copy environment config
cp .env.example .env
# Edit .env with your API keys

# Install pre-commit hooks
make hooks

# Run the CLI
make run-cli

# Start the backend server
make run-backend
```

## Project Structure

```
Alchemy/
├── backend/          # Core gateway engine
│   ├── app/          # Application source code
│   ├── tests/        # Test suites
│   ├── scripts/      # Utility scripts
│   └── docs/         # Backend-specific docs
├── frontend/         # CLI interface
│   ├── cli/          # Typer command definitions
│   ├── ui/           # Rich UI components
│   ├── animations/   # Routing animations
│   ├── voice/        # Smallest.ai STT integration
│   ├── dashboard/    # Budget & analytics dashboard
│   └── themes/       # CLI theme configurations
├── docs/             # Project documentation
├── pyproject.toml    # Project configuration
├── Makefile          # Development commands
└── docker-compose.yml
```

## Development

```bash
make format      # Format code (black + ruff)
make lint        # Lint code (ruff)
make typecheck   # Type check (mypy)
make test        # Run all tests
make check       # Run all quality checks
```

## License

MIT License — see [LICENSE](LICENSE) for details.

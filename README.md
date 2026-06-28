# Alchemy

**Adaptive Cost-Aware AI Gateway powered by Mozilla Otari**

> *The right model, at the right cost, at the right time — every time.*

---

## Table of Contents
- [What is Alchemy?](#what-is-alchemy)
- [The Problem We Solve](#the-problem-we-solve)
- [How Alchemy Works](#how-alchemy-works)
- [Key Capabilities](#key-capabilities)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Development](#development)
- [License](#license)

---

## What is Alchemy?

Alchemy is an **intelligent AI gateway** that acts as a smart intermediary between end users and multiple Large Language Models (LLMs). Think of it as a traffic controller and cost optimizer for AI requests.

Instead of directly sending queries to expensive AI models, Alchemy intercepts every request and performs intelligent preprocessing, analysis, routing, and optimization. It makes smart decisions about:
- **Which model** should handle this request (cheap or expensive?)
- **How to structure** the prompt for better results
- **Whether it's even necessary** to call an expensive model
- **Can this be answered from cache** to avoid redundant API calls?
- **Is this request safe** or does it contain injection attempts?

The result? **Significantly reduced costs** (sometimes 50-80% savings), **faster response times**, and **better observability** into your AI spending.

---

## The Problem We Solve

### Traditional AI Usage ❌

```
User Query → OpenAI GPT-4 → Response
Every query costs ~$0.03 - $0.10 (4K/8K tokens)
```

**Problems:**
- Every request goes to the same expensive model
- No caching of similar queries (duplicate API calls)
- No detection of simple queries that don't need advanced models
- Security vulnerabilities go undetected
- No budget visibility or cost control
- Wasted money on trivial requests

### With Alchemy ✅

```
User Query → Alchemy Gateway → Analysis & Decision Making
                                  ↓
                    Is it safe? Is it cached? Is it simple?
                                  ↓
Route to: Cached Answer / Local Model / Cheap API / Premium API
                                  ↓
                            Optimized Response
```

**Benefits:**
- **Cost Optimization**: Simple queries to cheap models, complex ones to premium models
- **Speed**: Cached answers are instant
- **Security**: Block malicious requests before they reach your APIs
- **Visibility**: Track every token spent, understand cost drivers
- **Intelligence**: Learn what works best for your use cases

---

## How Alchemy Works

### 1. **Request Interception & Analysis**
Every incoming query is analyzed for:
- Complexity level (simple FAQ vs. complex reasoning task)
- Required capabilities (does it need coding? reasoning? multimodal?)
- Security risk (prompt injection, jailbreak attempts, data leakage)
- Budget impact (how much will this cost?)

### 2. **Intelligent Routing Decision**
Based on the analysis, Alchemy decides:
```
Simple Query (FAQ, lookup) → Local Gemma 2B (Free, instant)
              ↓
Medium Query (analysis) → Cheap API (Claude 3 Haiku, ~$0.003)
              ↓
Complex Query (research, coding) → Premium API (GPT-4, ~$0.03)
              ↓
Repeated Query → Cached Result (Free, <1ms)
```

### 3. **Prompt Optimization**
- Rewrite prompts for clarity and conciseness when beneficial
- Add structured formatting for better outputs
- Optimize for target model's strengths
- Inject relevant context from cache when appropriate

### 4. **Caching Layer**
- Uses semantic embeddings (sentence-transformers) to find similar past queries
- FAISS vector search for fast similarity matching
- Confidence-based cache serving (high similarity = safe to return)
- Dramatically reduces redundant API calls

### 5. **Cost Tracking & Enforcement**
- Real-time token counting per model, per user, per team
- Budget alerts and enforcement
- Spending analytics and trends
- Cost breakdowns by model, feature, user

### 6. **Learning & Optimization**
- Tracks which routing decisions resulted in good outcomes
- Learns which model performs best for different query types
- Continuous improvement based on analytics
- Optional A/B testing capabilities

---

## Key Capabilities

### 🚀 Fast Request Detection
Identify trivial queries instantly without expensive LLM calls.
- **Example**: "What's the capital of France?" → Routed to local model or cache
- **Savings**: Avoid $0.03+ per query on simple facts

### 🔒 Security Screening
Multi-layer security before requests reach your APIs.
- **Detects**: Prompt injection attempts, jailbreaks, credential leakage patterns
- **Blocks**: Malicious requests before they consume tokens/budget
- **Logs**: All blocked attempts for audit and improvement

### 🧠 Adaptive Prompt Structuring
Improve prompt clarity and effectiveness when beneficial.
- **Adds structure**: Format prompts for JSON, code, or structured output
- **Context injection**: Adds relevant past context or guidelines
- **Model-specific optimization**: Tailors prompts for target model's strengths

### 📊 Task Analysis & Classification
Understand what each query really needs.
- **Complexity scoring**: 1-10 scale (simple fact lookup to novel reasoning)
- **Capability mapping**: Identifies if query needs coding, multimodal, RAG, etc.
- **Workload type**: FAQ vs. creative vs. analytical vs. coding

### 💰 Budget Management
Real-time cost tracking and enforcement.
- **Per-query estimates**: Know cost before sending to API
- **Budget limits**: Hard caps on spending per hour/day/month
- **Alerts**: Notify when approaching budget thresholds
- **Analytics**: See where every token/dollar is spent

### 📚 Semantic Caching
Avoid redundant API calls using intelligent similarity matching.
- **Embedding-based**: Finds semantically similar past queries
- **Configurable confidence**: Only serve cache above confidence threshold
- **Savings**: Often 20-40% of requests hit cache on typical usage

### 📋 Explainable Routing
Every decision is transparent and auditable.
- **Decision logs**: Why was this query routed to this model?
- **Scoring breakdown**: See the analysis that led to the decision
- **Audit trail**: Complete history for compliance and debugging

### 🧵 Context Management
Smart conversation history optimization.
- **Budget-aware summarization**: Compress old context when approaching limits
- **Selective history**: Only include relevant past messages
- **Token optimization**: Reduce context costs without losing information

### 📈 Learning Layer
Continuous optimization based on real usage.
- **Outcome tracking**: Which routing decisions led to good results?
- **Model performance**: Track which model works best for your use cases
- **Cost analysis**: Identify high-cost, low-value queries
- **Trend detection**: Spot emerging patterns in your usage

---

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| **Runtime** | Python 3.12 | Core implementation language |
| **API Framework** | FastAPI | High-performance REST API server |
| **CLI** | Typer + Rich | Beautiful command-line interface |
| **Local LLM** | Gemma 2B via Ollama | Free, instant responses for simple queries |
| **AI Gateway** | Mozilla Otari | Standardized API gateway interface |
| **Embeddings** | sentence-transformers | Convert queries to semantic vectors for caching |
| **Vector Search** | FAISS | Fast similarity search for cache hits |
| **Database** | SQLite | Persistent storage of routing decisions, analytics |
| **Voice STT** | Smallest.ai | Voice input support for CLI |
| **Validation** | Pydantic v2 | Type-safe request/response validation |
| **Logging** | Loguru | Structured, colorful logging |
| **Package Manager** | uv | Fast Python package management |

---

## Quick Start

### Prerequisites
- Python 3.12+
- Git
- `uv` package manager (or `pip`)

### Installation

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
# Edit .env with your API keys:
#   - OPENAI_API_KEY
#   - CLAUDE_API_KEY (optional)
#   - Other model API keys

# Install pre-commit hooks (for code quality)
make hooks

# Run the CLI
make run-cli

# Start the backend server
make run-backend
```

### Your First Query

**Via CLI:**
```bash
python -m frontend.cli "What's the capital of France?"
# Alchemy analyzes, routes to local model, returns instantly
```

**Via REST API:**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Explain quantum computing"}'
```

---

## Project Structure

```
Alchemy/
├── backend/          # Core gateway engine & API server
│   ├── app/          # Application source code
│   │   ├── models.py       # Data models & schemas
│   │   ├── router.py       # Routing logic (which model to use?)
│   │   ├── cache.py        # Semantic caching layer
│   │   ├── security.py     # Security screening
│   │   ├── analytics.py    # Cost tracking & analytics
│   │   └── api.py          # FastAPI route definitions
│   ├── tests/        # Unit & integration tests
│   ├── scripts/      # Utility scripts (setup, migration, etc.)
│   └── docs/         # Backend architecture documentation
│
├── frontend/         # CLI & user interfaces
│   ├── cli/          # Typer command definitions
│   ├── ui/           # Rich UI components (tables, panels, etc.)
│   ├── animations/   # Routing visualization animations
│   ├── voice/        # Smallest.ai STT integration
│   ├── dashboard/    # Budget & analytics dashboard
│   └── themes/       # CLI color themes & styling
│
├── docs/             # Full project documentation
│   ├── ARCHITECTURE.md      # System design & flow diagrams
│   ├── API.md               # REST API reference
│   ├── DEPLOYMENT.md        # Production setup guide
│   └── USAGE.md             # Detailed usage examples
│
├── pyproject.toml    # Python project configuration & dependencies
├── Makefile          # Development shortcuts
├── docker-compose.yml # Local dev environment with all services
├── .env.example      # Template for environment variables
└── README.md         # This file
```

---

## Development

### Code Quality

```bash
# Format code (black + ruff)
make format

# Lint code (ruff)
make lint

# Type check (mypy)
make typecheck

# Run all tests
make test

# Run all quality checks at once
make check
```

### Running Tests

```bash
# Run all tests with coverage
make test

# Run specific test file
pytest backend/tests/test_router.py -v

# Run tests matching a pattern
pytest -k "test_cache" -v
```

### Local Development with Docker

```bash
# Start all services (API, Ollama, vector DB)
docker-compose up

# Access API at http://localhost:8000
# View API docs at http://localhost:8000/docs
```

---

## How to Use Alchemy

### Example 1: Cost-Aware Chat
```python
from backend.app.router import Router

router = Router()

# Alchemy automatically decides which model to use
response = router.route_query(
    query="Explain machine learning to a 5-year-old",
    user_id="user123",
    budget_limit=0.50  # Max $0.50 for this query
)

print(response.model_used)  # "Claude 3 Haiku" ($0.001)
print(response.cost)        # 0.0015
print(response.cached)      # True/False
```

### Example 2: Monitoring Costs
```python
from backend.app.analytics import Analytics

analytics = Analytics()

# Get daily spending breakdown
daily_report = analytics.get_daily_report()
print(f"Today's spend: ${daily_report.total_cost}")
print(f"Queries: {daily_report.total_queries}")
print(f"Cache hit rate: {daily_report.cache_hit_rate}%")
```

### Example 3: CLI Usage
```bash
# Simple query (routed intelligently)
alchemy "What's 2+2?"

# With budget limit
alchemy --budget 0.10 "Write a 500-word essay on AI ethics"

# Interactive mode
alchemy --interactive

# View dashboard
alchemy dashboard
```

---

## Future Roadmap

- 🔄 Multi-model load balancing with latency optimization
- 🌍 Multi-language support with automatic translation
- 🎯 Fine-tuning integration for custom model adaptation
- 📱 Mobile app for on-the-go AI access
- 🔌 Webhooks and streaming responses
- 🤝 Team/organization features with usage sharing

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Support & Documentation

- 📖 **Full Documentation**: See `/docs` folder
- 🐛 **Issues**: Found a bug? [Open an issue](../../issues)
- 💬 **Discussions**: Have ideas? [Start a discussion](../../discussions)
- 📧 **Email**: [support information to be added]

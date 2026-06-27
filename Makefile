.PHONY: help install install-dev hooks format lint typecheck test test-unit test-integration test-load test-security test-cov check clean run-backend run-cli docker-up docker-down

PYTHON := python
UV := uv

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Installation ─────────────────────────────

install: ## Install production dependencies
	$(UV) pip install -e .

install-dev: ## Install all dependencies including dev tools
	$(UV) pip install -e ".[dev]"

hooks: ## Install pre-commit hooks
	pre-commit install

# ── Code Quality ─────────────────────────────

format: ## Format code with black and ruff
	$(UV) run black backend/ frontend/
	$(UV) run ruff check --fix backend/ frontend/

lint: ## Lint code with ruff
	$(UV) run ruff check backend/ frontend/

typecheck: ## Type check with mypy
	$(UV) run mypy backend/ frontend/

check: lint typecheck test ## Run all quality checks

# ── Testing ──────────────────────────────────

test: ## Run all tests
	$(UV) run pytest

test-unit: ## Run unit tests only
	$(UV) run pytest -m unit

test-integration: ## Run integration tests only
	$(UV) run pytest -m integration

test-load: ## Run load tests only
	$(UV) run pytest -m load

test-security: ## Run security tests only
	$(UV) run pytest -m security

test-cov: ## Run tests with coverage report
	$(UV) run pytest --cov=backend --cov-report=html --cov-report=term-missing

# ── Run ──────────────────────────────────────

run-backend: ## Start the backend FastAPI server
	$(UV) run uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

run-cli: ## Start the Alchemy CLI
	$(UV) run alchemy

# ── Docker ───────────────────────────────────

docker-up: ## Start all services via Docker Compose
	docker-compose up -d

docker-down: ## Stop all Docker services
	docker-compose down

# ── Maintenance ──────────────────────────────

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name .coverage -delete 2>/dev/null || true
	rm -rf dist/ build/ *.egg-info/

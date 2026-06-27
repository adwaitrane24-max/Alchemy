# Contributing to Alchemy

Thank you for your interest in contributing to Alchemy.

## Development Setup

```bash
# Clone the repository
git clone <repository-url>
cd Alchemy

# Create virtual environment
uv venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate      # Windows

# Install dependencies
make install

# Install pre-commit hooks
make hooks
```

## Development Workflow

1. Create a feature branch from `develop`
2. Make your changes
3. Run the full quality pipeline: `make check`
4. Commit with a descriptive message
5. Open a pull request against `develop`

## Code Standards

- Python 3.12+
- Type hints on all function signatures
- PEP 8 compliance (enforced by ruff + black)
- Absolute imports only
- No hardcoded values — use constants or configuration

## Commit Messages

Follow conventional commits:

```
feat: add semantic cache TTL configuration
fix: correct budget state transition from LOW to CRITICAL
refactor: extract embedding generation into shared utility
docs: update API contract documentation
test: add unit tests for fast request detector
```

## Testing

```bash
make test          # Run all tests
make test-unit     # Run unit tests only
make test-cov      # Run tests with coverage report
```

## Quality Checks

```bash
make lint          # Lint with ruff
make format        # Format with black
make typecheck     # Type check with mypy
make check         # Run all checks
```

## Branch Naming

- `feat/<feature-name>` — New features
- `fix/<bug-name>` — Bug fixes
- `refactor/<scope>` — Refactoring
- `docs/<topic>` — Documentation
- `test/<scope>` — Test additions

## Questions?

Open an issue for discussion before starting large changes.

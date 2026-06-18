# Contributing to Agentic-DataLab

## Development Setup

### Prerequisites
- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- Git

### Quick Start
```bash
# Clone repository
git clone <repository-url>
cd Agentic-DataLab

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python scripts/generate_secret.py  # Generate JWT secret
cp .env.example .env  # Edit .env with generated secret
pytest tests/  # Run tests

# Frontend setup
cd ../frontend
npm install
npm run dev  # Start dev server
npm test  # Run tests

# Docker (recommended)
docker-compose up -d
```

## Code Standards

### Backend (Python)
- **Style**: Follow PEP 8, use `ruff` for linting
- **Type Hints**: Use type hints for all functions
- **Docstrings**: Google-style docstrings for public APIs
- **Tests**: Minimum 60% coverage, use pytest

```python
def function_name(arg: str) -> int:
    """
    Brief description.

    Args:
        arg: Description

    Returns:
        Description

    Raises:
        ValueError: When condition
    """
    pass
```

### Frontend (Vue/TypeScript)
- **Style**: Use ESLint + Prettier
- **Types**: Explicit types for all props and returns
- **Components**: Single File Components (SFC)
- **Tests**: Vitest for unit tests

```typescript
<script setup lang="ts">
interface Props {
  title: string
  count?: number
}

const props = withDefaults(defineProps<Props>(), {
  count: 0
})
</script>
```

## Pull Request Process

1. **Create Branch**: `feature/description` or `fix/description`
2. **Write Tests**: Add tests for new features
3. **Run Checks**: Ensure all tests and linters pass
4. **Commit**: Use conventional commits
5. **Push & PR**: Create PR with clear description

### Commit Messages
```
feat: Add new feature
fix: Fix bug
docs: Update documentation
test: Add tests
refactor: Refactor code
chore: Update dependencies
```

## Running Tests

### Backend
```bash
cd backend
pytest tests/ -v --cov
ruff check .
mypy .
bandit -r . -ll
```

### Frontend
```bash
cd frontend
npm test
npm run type-check
npm run lint
```

### Integration
```bash
docker-compose up -d
curl http://localhost:8000/api/v1/health
```

## Project Structure

```
Agentic-DataLab/
├── backend/
│   ├── agents/          # Agent implementations
│   ├── api/             # API routes & middleware
│   ├── core/            # Core utilities
│   ├── models/          # Database models
│   ├── schemas/         # Pydantic schemas
│   ├── services/        # Business logic
│   └── tests/           # Tests
├── frontend/
│   ├── src/
│   │   ├── components/  # Vue components
│   │   ├── composables/ # Composable functions
│   │   ├── stores/      # Pinia stores
│   │   ├── types/       # TypeScript types
│   │   └── utils/       # Utilities
│   └── tests/           # Tests
└── docs/                # Documentation
```

## Questions?

- Open an issue for bugs
- Discussions for feature requests
- Email for security issues

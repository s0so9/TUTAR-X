# Football Intelligence Backend

FastAPI backend for the Football Intelligence platform.

## Architecture

```
backend/
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── config.py               # Configuration management
│   ├── api/                    # API endpoints
│   │   ├── v1/                 # API version 1
│   │   │   ├── endpoints/      # Route handlers
│   │   │   └── router.py       # API router
│   ├── domain/                 # Domain models
│   │   ├── models.py           # Pydantic models
│   │   └── schemas.py          # Request/Response schemas
│   ├── database/               # Database layer
│   │   ├── base.py             # Database base setup
│   │   ├── session.py          # Session management
│   │   └── models.py           # SQLAlchemy models
│   ├── providers/              # Data provider abstractions
│   │   ├── base.py             # Provider interface
│   │   └── development.py      # Development/mock provider
│   ├── features/               # Feature engineering
│   │   ├── base.py             # Feature interface
│   │   └── team_features.py    # Team feature calculators
│   ├── prediction/             # Prediction engine
│   │   ├── base.py             # Model interface
│   │   ├── poisson.py          # Poisson model
│   │   └── ensemble.py         # Model combination
│   ├── analysis/               # Analysis context
│   │   └── context.py          # AnalysisContext builder
│   ├── ai/                     # AI Analyst integration
│   │   ├── base.py             # AI provider interface
│   │   └── ollama.py           # Ollama implementation
│   └── utils/                  # Utilities
│       ├── probability.py      # Probability calculations
│       └── logging.py          # Logging configuration
└── tests/                      # Test suite
    ├── test_probability.py
    ├── test_poisson.py
    └── test_features.py
```

## Technology Stack

- **FastAPI**: Modern Python web framework
- **Pydantic**: Data validation and settings
- **SQLAlchemy**: Database ORM
- **PostgreSQL**: Primary database (SQLite for development)
- **NumPy/SciPy**: Scientific computing for prediction models

## Setup

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment configuration
copy .env.example .env

# Run development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Development Principles

1. **Modular Architecture**: Each component has a clear responsibility
2. **Provider Abstraction**: Data sources are abstracted behind interfaces
3. **PostgreSQL-Ready**: Database architecture designed for production PostgreSQL
4. **Type Safety**: Pydantic models for validation and type checking
5. **Testable**: Unit tests for mathematical and logical components
6. **Documented**: Clear documentation for all modules

## API Structure

The API follows REST principles and is versioned at `/api/v1/`.

Key endpoints:
- `GET /api/v1/health` - Health check
- `GET /api/v1/matches` - List matches (development data)
- `GET /api/v1/matches/{match_id}/prediction` - Get match prediction
- `GET /api/v1/teams/{team_id}` - Get team information

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_probability.py

# Run with coverage
pytest --cov=app tests/
```

## Notes

- Keep technical identifiers in English
- User-facing strings should be Turkish (handled by frontend)
- Development/mock data must be clearly labeled
- Never invent statistics or probabilities
- Numerical engine is authoritative

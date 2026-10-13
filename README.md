# TUTAR X - Football Intelligence Platform

TUTAR X — Maçın geleceğini veriden oku.

Professional football analytics, prediction, and live analysis platform.

## Overview

TUTAR X is a comprehensive football analytics system capable of:

- Collecting and storing football data
- Analyzing teams, players, and matches
- Calculating statistical features
- Generating predictions using multiple models
- Calibrating probabilities (not yet applied in production, see Status)
- Backtesting prediction models
- Comparing predictions with market information
- Updating predictions during live matches
- Explaining predictions using a local AI Analyst

## Architecture

The platform consists of three main components:

### Backend (Python + FastAPI)
- RESTful API server
- Prediction engine with multiple models
- Feature engineering layer
- Database abstraction (PostgreSQL-ready)
- Provider abstraction for data sources
- AI Analyst integration (Ollama)

### Frontend (React + TypeScript + Vite)
- Professional dark-themed web interface
- Turkish-first UI
- Real-time prediction display
- Analytics workspace
- Backtesting visualization

### Database (SQLite for development, PostgreSQL-ready)
- Match and team data
- Historical statistics
- Prediction results
- Model performance metrics

## Project Structure

```
FootballIntelligence/
├── backend/                 # Python FastAPI backend
│   ├── app/                 # Application code (API, providers, features, prediction engine)
│   ├── alembic/             # Database migrations
│   ├── scripts/             # Data import / maintenance scripts
│   └── tests/               # Backend test suite (pytest)
├── frontend/                # React TypeScript frontend (Vite)
├── docs/                    # Documentation and progress log
├── PROJECT_SPEC.md          # Master product specification
├── AGENTS.md                # Agent operational rules
└── README.md                # This file
```

## Technology Stack

### Backend
- Python 3.12+ (tested on 3.14)
- FastAPI
- Pydantic / pydantic-settings
- SQLAlchemy + Alembic
- NumPy / SciPy / scikit-learn
- SQLite for development, PostgreSQL-ready

### Frontend
- React 18
- TypeScript
- Vite
- React Router

### AI
- Ollama (qwen3-coder:30b)
- Local inference only

## Getting Started

Prerequisites: Python 3.12+ (tested on 3.14), Node.js 18+, and optionally
[Ollama](https://ollama.com) with `qwen3-coder:30b` for the AI Analyst.

### 1. Backend install

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# Runtime + test dependencies (requirements-dev.txt includes requirements.txt)
pip install -r requirements-dev.txt

# Configuration (then edit .env as needed)
copy .env.example .env        # Windows
cp .env.example .env          # macOS / Linux
```

Notes on `.env` (see comments in `backend/.env.example`):
- `CORS_ORIGINS` must be a JSON list, e.g. `["http://localhost:5173","http://127.0.0.1:5173"]`.
- `USE_REAL_PROVIDERS=true` serves real data from the local database (with external
  providers as fallback). `false` uses the DevelopmentProvider, i.e. mock data that is
  labeled as development data.
- `FI_ADMIN_TOKEN` protects `POST /api/v1/odds/manual-update`; when empty that
  endpoint is disabled (HTTP 503).
- `THE_ODDS_API_KEY` / `THE_ODDS_API_ENABLED` are optional (paid, quota-limited API).

### 2. Database setup

```bash
cd backend
alembic upgrade head
```

This creates the schema in the database named by `DATABASE_URL`
(default: `sqlite:///./football_intelligence.db` in `backend/`).
For PostgreSQL set `DATABASE_URL=postgresql://user:password@host:5432/dbname` first.

Existing database created before migrations were used (it has tables but no
`alembic_version` table)? Do **not** run `upgrade` on it (it would fail on existing
tables). Back it up, confirm its schema matches the models, then run
`alembic stamp head` once.

### 3. Data import

A fresh database is empty. Historical matches are imported with:

```bash
cd backend
python scripts/import_historical_data.py --start-date 2026-08-01 --end-date 2026-10-12 --provider fotmob
```

Upcoming fixtures: `python scripts/import_upcoming_matches.py --days 7`.

FotMob is an **unofficial, undocumented** data source: endpoints can change or
rate-limit without notice, and statistics coverage varies by competition.

### 4. Run the backend

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8003 --reload
```

- API: http://127.0.0.1:8003 (interactive docs at `/docs`)
- Health check: http://127.0.0.1:8003/health

### 5. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at http://localhost:5173. The Vite dev server proxies `/api` to
`http://127.0.0.1:8003`.

### Running tests

```bash
# Backend (pytest.ini limits collection to backend/tests)
cd backend
python -m pytest -q

# Point tests at a throwaway database so they never touch your real data:
#   Windows (PowerShell): $env:DATABASE_URL="sqlite:///./test_scratch.db"; python -m pytest -q
#   macOS / Linux:        DATABASE_URL=sqlite:///./test_scratch.db python -m pytest -q

# Frontend
cd frontend
npm test          # vitest
npm run build     # type-check + production build
```

## Development Principles

1. **Numerical Engine First**: All predictions derive from mathematical models
2. **AI as Explanation Layer**: AI Analyst explains, never invents statistics
3. **Data Integrity**: Mock data must be clearly labeled
4. **Modular Architecture**: Clean separation of concerns
5. **Type Safety**: Full type coverage in both backend and frontend
6. **Progressive Testing**: Test critical components as they're built
7. **Verification**: Always verify implementation works

## Core Principles

- The numerical/statistical engine is the source of truth
- The AI Analyst is an explanation layer only
- Never invent statistics, probabilities, or predictions
- Missing data must be explicitly represented as unavailable
- Development/mock data must be clearly labeled

## Documentation

- `PROJECT_SPEC.md` - Complete product specification
- `AGENTS.md` - Operational rules for autonomous agents
- `docs/PROGRESS.md` - Implementation progress log
- `backend/README.md` - Backend documentation
- `frontend/README.md` - Frontend documentation

## Status

Under active development. Implemented today: FastAPI backend with a database-first
hybrid data provider, statistical prediction models (Poisson family, ensemble,
Monte Carlo), market analysis, optional bookmaker odds via The Odds API, and the
React frontend.

Known limitations:
- Probability calibration is currently **not applied** (the prediction pipeline
  falls back to uncalibrated probabilities).
- Match data depends on FotMob, an unofficial source.
- The backend test suite still has known pre-existing failures that are being worked on.

See `docs/PROGRESS.md` for the detailed progress log.

## License

Proprietary - All Rights Reserved

## Notes

- Keep technical identifiers in English
- User-facing text primarily in Turkish
- PostgreSQL-ready architecture (SQLite for development)
- No external AI APIs (Ollama only)

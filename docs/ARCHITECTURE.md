# Football Intelligence - Architecture Documentation

## System Overview

Football Intelligence is designed as a professional football analytics platform with a strict separation between data, computation, and presentation layers.

## Architectural Layers

```
┌─────────────────────────────────────────────────────────────┐
│                     USER INTERFACE                           │
│              (React + TypeScript + Vite)                     │
└─────────────────────────────────────────────────────────────┘
                            │
                     HTTP REST API
                            │
┌─────────────────────────────────────────────────────────────┐
│                   API LAYER (FastAPI)                        │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌──────▼──────┐  ┌────────▼────────┐
│  DATA PROVIDERS │  │  PREDICTION │  │   AI ANALYST    │
│   (Abstract)    │  │    ENGINE   │  │   (Ollama)      │
└────────────────┘  └──────┬──────┘  └─────────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
            ┌───────▼──────┐  ┌──▼────────────┐
            │   FEATURES   │  │   ANALYSIS    │
            │  ENGINEERING │  │   CONTEXT     │
            └──────────────┘  └───────────────┘
                    │
            ┌───────▼──────┐
            │   DATABASE   │
            │ (PostgreSQL) │
            └──────────────┘
```

## Backend Architecture

### Module Structure

```
backend/app/
├── main.py                 # FastAPI application entry
├── config.py               # Configuration management
├── api/                    # API endpoints
│   └── v1/                 # Version 1 API
│       ├── router.py       # API router
│       └── endpoints/      # Endpoint handlers
├── domain/                 # Domain models
│   ├── models.py           # Business logic models
│   └── schemas.py          # API schemas (Pydantic)
├── database/               # Database layer
│   ├── base.py             # Database setup
│   ├── session.py          # Session management
│   └── models.py           # SQLAlchemy models
├── providers/              # Data provider abstraction
│   ├── base.py             # Provider interface
│   └── development.py      # Mock provider
├── features/               # Feature engineering
│   ├── base.py             # Feature interface
│   └── team_features.py    # Team statistics
├── prediction/             # Prediction engine
│   ├── base.py             # Model interface
│   ├── poisson.py          # Poisson model
│   └── ensemble.py         # Model combination
├── analysis/               # Analysis context
│   └── context.py          # Context builder
├── ai/                     # AI integration
│   ├── base.py             # Provider interface
│   └── ollama.py           # Ollama client
└── utils/                  # Utilities
    ├── probability.py      # Probability math
    └── logging.py          # Logging config
```

### Data Flow

1. **Request** → API endpoint receives request
2. **Provider** → Data fetched from provider (mock or real)
3. **Features** → Statistical features calculated
4. **Prediction** → Models generate predictions
5. **Context** → AnalysisContext assembled
6. **AI** → (Optional) AI Analyst generates explanation
7. **Response** → Structured response returned

## Frontend Architecture

### Module Structure

```
frontend/src/
├── main.tsx                # Application entry
├── App.tsx                 # Root component
├── api/                    # API client
│   ├── client.ts           # HTTP client
│   └── endpoints/          # API functions
├── components/             # Reusable components
│   ├── common/             # Common UI
│   ├── match/              # Match components
│   ├── team/               # Team components
│   └── prediction/         # Prediction display
├── pages/                  # Page components
│   ├── Dashboard.tsx       # Gösterge Paneli
│   ├── Matches.tsx         # Maçlar
│   ├── Teams.tsx           # Takımlar
│   └── ...                 # Other pages
├── hooks/                  # Custom hooks
│   ├── useMatch.ts
│   ├── usePrediction.ts
│   └── useTeam.ts
├── types/                  # TypeScript types
│   ├── match.ts
│   ├── prediction.ts
│   └── team.ts
├── utils/                  # Utilities
│   ├── format.ts
│   └── probability.ts
└── styles/                 # Styles
    └── global.css
```

## Database Architecture

### Entity Model (PostgreSQL-ready)

**Core Entities:**
- Competition
- Season
- Team
- Player
- Venue
- Match
- MatchEvent

**Statistics:**
- PlayerMatchStatistic
- TeamMatchStatistic
- Standing

**Predictions:**
- Prediction
- PredictionMarket
- Model
- ModelVersion
- ModelRun

**Backtesting:**
- Backtest
- BacktestResult

**Live:**
- LiveMatchState

**Features:**
- FeatureSnapshot

**Analysis:**
- AnalysisContext (stored for audit)

## Provider Abstraction

### Interface Design

```python
class DataProvider(ABC):
    @abstractmethod
    async def get_match(self, match_id: str) -> Match:
        pass
    
    @abstractmethod
    async def get_team_stats(self, team_id: str) -> TeamStats:
        pass
    
    # ... other methods
```

### Implementation Strategy

- **Development Phase**: DevelopmentProvider with clearly labeled mock data
- **Production Phase**: Real provider implementations (API-Football, etc.)
- **Testing Phase**: TestProvider with controlled data

## Prediction Engine Architecture

### Model Interface

```python
class PredictionModel(ABC):
    name: str
    version: str
    
    @abstractmethod
    def predict(self, context: ModelContext) -> PredictionOutput:
        pass
    
    @abstractmethod
    def get_metadata(self) -> ModelMetadata:
        pass
```

### Model Types

1. **Statistical Models**
   - Poisson
   - Dixon-Coles
   - Negative Binomial

2. **Machine Learning Models**
   - Random Forest
   - Gradient Boosting
   - Neural Networks

3. **Simulation Models**
   - Monte Carlo
   - Score Simulation

4. **Ensemble Models**
   - Weighted Average
   - Meta Model

## AI Analyst Architecture

### Provider Abstraction

```python
class AIProvider(ABC):
    @abstractmethod
    async def analyze(self, context: AnalysisContext) -> str:
        pass
```

### Ollama Implementation

- Local inference only
- Model: qwen3-coder:30b
- Endpoint: http://127.0.0.1:11434
- Strict context-based generation
- No hallucination of statistics

## Feature Engineering Architecture

### Feature Categories

1. **Team Strength Features**
   - Attack strength
   - Defense strength
   - Home/Away strength
   - Elo ratings

2. **Form Features**
   - Recent form (3/5/10 matches)
   - Home/Away form
   - Weighted form

3. **Goals Features**
   - Goals scored/conceded
   - xG/xGA
   - Shot efficiency

4. **Other Features**
   - Possession
   - Corners
   - Cards
   - Head-to-head (carefully weighted)

## API Design

### REST Principles

- Version prefix: `/api/v1/`
- Resource-based URLs
- HTTP methods: GET, POST, PUT, DELETE
- JSON request/response
- Consistent error format

### Key Endpoints

```
GET  /api/v1/health
GET  /api/v1/matches
GET  /api/v1/matches/{match_id}
GET  /api/v1/matches/{match_id}/prediction
GET  /api/v1/teams/{team_id}
GET  /api/v1/players/{player_id}
POST /api/v1/predictions/backtest
```

## Security Considerations

- No external AI APIs
- Local AI inference only
- Environment-based configuration
- Database credentials in .env
- CORS properly configured
- Input validation (Pydantic)

## Scalability Considerations

- Stateless API design
- Database connection pooling
- Async/await for I/O operations
- Caching strategies (future)
- Horizontal scaling capability

## Testing Strategy

### Backend Testing
- Unit tests for probability calculations
- Unit tests for prediction models
- Integration tests for API endpoints
- Feature calculation tests

### Frontend Testing
- Component tests (future)
- Type checking (TypeScript)
- Build verification

## Deployment Architecture (Future)

```
┌──────────┐
│  Client  │
└────┬─────┘
     │
┌────▼─────────────┐
│  Load Balancer   │
└────┬─────────────┘
     │
┌────▼────────┬────────────┐
│  Frontend   │  Frontend  │  (Static)
│  Instance   │  Instance  │
└─────────────┴────────────┘
     │
┌────▼────────┬────────────┐
│   Backend   │   Backend  │  (API)
│  Instance   │  Instance  │
└────┬────────┴─────┬──────┘
     │              │
┌────▼──────────────▼──────┐
│   PostgreSQL Database    │
└──────────────────────────┘
     │
┌────▼──────────────────────┐
│   Ollama (AI) Instance    │
└───────────────────────────┘
```

## Development Workflow

1. **Feature Development**
   - Read specification
   - Implement backend
   - Add tests
   - Implement frontend
   - Verify integration

2. **Verification**
   - Run tests
   - Build check
   - Manual testing
   - Update PROGRESS.md

3. **Phase Completion**
   - All tests pass
   - Build succeeds
   - Documentation updated
   - Ready for next phase

## Notes

- Architecture designed for progressive enhancement
- Modular design allows independent development
- Provider abstraction enables easy data source changes
- AI abstraction keeps inference local
- PostgreSQL-ready from day one

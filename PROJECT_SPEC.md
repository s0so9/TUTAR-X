MASTER PROJECT SPECIFICATION

## Football Intelligence, Analytics, Prediction & Live Analysis Platform

You are now working as the primary autonomous software engineering agent for this project.

The previous message established your role, the local development environment, and the general engineering rules.

This document is the MASTER PROJECT SPECIFICATION.

Everything below defines the actual product we are building.

---

# 1. PRODUCT VISION

We are building a professional football intelligence platform from scratch.

This is NOT intended to be a simple football scores website.

The goal is to build a complete football analytics system capable of:

- collecting football data

- storing historical data

- analyzing teams

- analyzing players

- analyzing matches

- calculating statistical features

- generating multiple independent predictions

- combining prediction models

- calibrating probabilities

- backtesting models

- comparing predictions with market information

- updating predictions during live matches

- explaining predictions using a local AI Analyst

- presenting everything through a professional web interface

The system should eventually function as a serious football analytics workstation.

The numerical/statistical engine is the source of truth.

The AI Analyst is an explanation layer.

---

# 2. CORE PRINCIPLE

The system must have a strict separation between

DATA

↓

FEATURE ENGINEERING

↓

ANALYTICS

↓

PREDICTION MODELS

↓

ENSEMBLE / META MODEL

↓

CALIBRATION

↓

PREDICTION OUTPUT

↓

ANALYSIS CONTEXT

↓

AI ANALYST

↓

USER INTERFACE

The AI must NEVER replace the numerical engine.

The AI Analyst must NEVER invent:

- statistics

- probabilities

- odds

- injuries

- lineups

- player information

- match events

- historical results

- model outputs

- confidence values

If the numerical system does not provide a value, the AI must say that the information is unavailable.

---

# 3. PROJECT STATUS

The project is being built from scratch.

Working directory:

C:\FootballIntelligence

Existing project directories:

C:\FootballIntelligence\frontend

C:\FootballIntelligence\backend

C:\FootballIntelligence\database

C:\FootballIntelligence\scripts

C:\FootballIntelligence\docs

The existing frontend should be inspected and reused where useful.

Do not destroy existing work without a reason.

---

# 4. TECHNOLOGY STACK

## Frontend

Use:

- React

- TypeScript

- Vite

- modern CSS / appropriate component architecture

- charts/visualizations where useful

The frontend should be:

- responsive

- fast

- professional

- dark-themed

- data-dense without being cluttered

- Turkish-first

- easy to navigate

---

## Backend

Use:

- Python

- FastAPI

- Pydantic

- SQLAlchemy

Architecture should be modular.

Avoid putting the entire backend into one file.

---

## Database

Design for:

PostgreSQL

The application must have a proper database abstraction so development can use local/mock data without destroying the production architecture.

---

## AI

Use ONLY:

Ollama

Model:

qwen3-coder:30b

Endpoint:

http://127.0.0.1:11434

The AI integration must be provider-abstracted even though Ollama is currently the only provider.

Do NOT add OpenAI.

Do NOT add Gemini.

Do NOT add Claude.

Do NOT add external AI APIs.

---

# 5. FOOTBALL DATA ARCHITECTURE

The application must not be hard-coded around one specific football data provider.

Create provider interfaces/abstractions.

The architecture should support:

- competitions

- leagues

- seasons

- teams

- players

- fixtures

- historical matches

- match events

- lineups

- substitutions

- player statistics

- team statistics

- standings

- injuries

- suspensions

- odds

- live scores

- live events

- xG

- possession

- shots

- shots on target

- corners

- cards

Where real providers are not yet connected, create clearly labeled development/mock providers.

Never represent mock data as live or real-world data.

---

# 6. DATABASE DOMAIN

The database architecture should eventually support entities including:

Competition

Season

Team

Player

Venue

Match

MatchEvent

Lineup

PlayerMatchStatistic

TeamMatchStatistic

Standing

Injury

Suspension

Odds

Prediction

PredictionMarket

Model

ModelVersion

ModelRun

Backtest

BacktestResult

LiveMatchState

FeatureSnapshot

AnalysisContext

Use proper relationships and indexes.

Avoid premature overengineering, but design the architecture so it can scale.

---

# 7. FEATURE ENGINEERING

Create a dedicated feature engineering layer.

Potential features include:

## Team strength

- attack strength

- defensive strength

- home strength

- away strength

- overall strength

- Elo

- rolling Elo

## Form

- last 3

- last 5

- last 10

- weighted recent form

- home form

- away form

## Goals

- goals scored

- goals conceded

- expected goals

- expected goals conceded

- shots

- shots on target

- conversion

- defensive efficiency

## Possession

- average possession

- possession differential

## Corners

- corners for

- corners against

- home/away corner averages

## Cards

- yellow cards

- red cards

- cards for

- cards against

## Head-to-head

Use carefully.

Do not allow historical head-to-head data to dominate more relevant current information.

## Player features

When data exists:

- minutes

- goals

- assists

- shots

- xG

- xA

- key passes

- cards

- form

- availability

---

# 8. PREDICTION ENGINE

The platform must support multiple independent prediction models.

The goal is not to artificially claim "40 models".

The goal is to have a large modular prediction engine where every model has a meaningful purpose.

Eventually support 40+ prediction/model components where justified.

Examples include:

### Statistical models

- Poisson

- Dixon-Coles

- Negative Binomial where appropriate

- Elo

- logistic regression

- Bayesian models

### Machine learning

- random forest

- gradient boosting

- XGBoost-style architecture where dependencies permit

- neural network models where sufficient data exists

### Simulation

- Monte Carlo

- scoreline simulation

- goal distribution simulation

- scenario simulation

### Feature-based models

- attack/defense model

- home advantage model

- recent form model

- xG model

- shots model

- possession model

- corners model

- cards model

- player availability model

### Market-related models

- implied probability

- bookmaker margin normalization

- market-vs-model comparison

### Ensemble

- weighted ensemble

- dynamically weighted ensemble

- meta model

Every model must expose:

- model name

- model version

- inputs

- output

- probability

- metadata

- evaluation metrics

---

# 9. PREDICTION MARKETS

Support architecture for:

## Match result

- Home

- Draw

- Away

## Goals

- Over/Under

- team goals

- total goals

## BTTS

- Yes

- No

## Correct score

Generate scoreline probability distribution.

## Expected goals

- home xG

- away xG

- total xG

## Corners

Where sufficient data exists:

- total corners

- home corners

- away corners

- over/under corners

## Cards

Where sufficient data exists:

- total cards

- home cards

- away cards

- over/under cards

## Player markets

Only when sufficient player data exists.

Never fabricate player-market predictions from missing data.

---

# 10. PROBABILITY ENGINE

Probabilities must be mathematically meaningful.

Do not simply generate arbitrary percentages.

For example:

1X2 probabilities should be derived from the underlying scoreline or model distributions.

Correct score probabilities should derive from the score distribution.

Goal markets should derive from the goal distribution.

BTTS should derive from the appropriate probability distribution.

Probability values must be validated.

They should not accidentally:

- exceed 100%

- become negative

- fail normalization where normalization is expected

---

# 11. FAIR ODDS

Where probabilities are available:

fair_odds = 1 / probability

Handle zero and invalid probabilities safely.

Clearly distinguish:

- model probability

- market implied probability

- fair odds

- bookmaker odds

- edge/value

Never call something guaranteed.

---

# 12. ENSEMBLE SYSTEM

The platform must eventually combine multiple models.

Possible architecture:

Individual Models

↓

Model Outputs

↓

Model Performance Weighting

↓

Ensemble

↓

Calibration

↓

Final Prediction

Weights should eventually be based on measurable historical performance rather than arbitrary hard-coded preference.

Track model performance over time.

---

# 13. CALIBRATION

Probability calibration is a core requirement.

Implement architecture for:

- Brier score

- log loss

- reliability diagrams

- calibration curves

- calibration error

- probability calibration

- isotonic calibration where appropriate

- Platt/scaled calibration where appropriate

A model producing 70% probabilities should be evaluated against historical outcomes.

Do not confuse:

confidence

with

probability.

---

# 14. BACKTESTING

Backtesting must be chronological.

Absolutely avoid future-data leakage.

Support:

- train/test split by time

- rolling windows

- walk-forward validation

- expanding-window validation

- model comparison

- calibration evaluation

- market comparison

- prediction performance history

Track:

- accuracy

- Brier score

- log loss

- calibration

- ROI where odds are available

- drawdown where appropriate

- sample size

Never claim profitability without sufficient historical evidence.

---

# 15. LIVE MATCH ENGINE

Create a live architecture capable of processing:

- current score

- match minute

- events

- goals

- cards

- substitutions

- shots

- shots on target

- possession

- corners

- xG

- player changes

- momentum indicators

The live prediction engine should be able to recalculate probabilities when new information arrives.

Example:

Pre-match prediction

↓

Kickoff

↓

15'

↓

Goal

↓

Red card

↓

Half-time

↓

Second half

↓

Full time

The system should be architected so the prediction state can update throughout the match.

---

# 16. AI ANALYST

Create a strict AnalysisContext object.

Conceptually:

AnalysisContext {

match

teams

competition

recentForm

teamStrength

playerAvailability

injuries

lineups

historicalData

xgData

statisticalFeatures

modelPredictions

ensemblePrediction

calibration

marketData

liveState

}

The AI Analyst receives this structured context.

It then produces an explanation.

The AI should answer questions such as:

- Why is the model assigning this probability?

- Which factors influence the prediction?

- What are the strongest statistical signals?

- What changed during the live match?

- Which model components agree/disagree?

- What information is missing?

- How reliable is the underlying sample?

The AI should explain uncertainty rather than hide it.

---

# 17. AI ANALYST SAFETY AGAINST HALLUCINATION

The AI Analyst must follow these rules:

1. Never invent a statistic.

2. Never invent a player injury.

3. Never invent a lineup.

4. Never invent an odds value.

5. Never change a supplied probability.

6. Never create an unsupported prediction.

7. Never claim access to unavailable live data.

8. Never pretend mock data is real.

9. Explicitly identify missing information.

10. Base numerical claims exclusively on AnalysisContext.

The numerical engine is authoritative.

---

# 18. FRONTEND INFORMATION ARCHITECTURE

Create pages/components for:

Dashboard

Matches

Match Detail

Teams

Team Detail

Players

Player Detail

Predictions

Analytics

Backtesting

Live

AI Analyst

Settings

---

# 19. DASHBOARD

Dashboard should eventually show:

- live matches

- upcoming matches

- recent matches

- prediction overview

- model health

- data freshness

- recent prediction performance

- interesting statistical signals

Avoid meaningless decorative metrics.

Every metric should have a purpose.

---

# 20. MATCH PAGE

A match page should eventually contain:

Teams

Competition

Kickoff

Venue

Recent form

Head-to-head

Team statistics

Expected goals

Attack/defense metrics

Prediction probabilities

Fair odds

Market comparison

Correct-score distribution

BTTS

Goals markets

Corners

Cards

Player information

Model breakdown

AI Analyst

Live state when applicable

---

# 21. TEAM PAGE

Show:

- team strength

- form

- home/away performance

- goals

- xG

- xGA

- shots

- possession

- corners

- cards

- squad

- player performance

- historical trends

---

# 22. PLAYER PAGE

Where data exists:

- appearances

- minutes

- goals

- assists

- xG

- xA

- shots

- key passes

- cards

- recent form

- availability

---

# 23. ANALYTICS PAGE

Create a professional analytics workspace.

Users should eventually be able to explore:

- team comparison

- player comparison

- league statistics

- trends

- model performance

- prediction distributions

- calibration

- historical results

---

# 24. BACKTEST PAGE

Allow the user to inspect:

- model

- period

- market

- sample size

- accuracy

- Brier

- log loss

- calibration

- ROI if applicable

Use charts where useful.

---

# 25. LIVE PAGE

Display:

- currently live matches

- score

- minute

- major events

- statistics

- live prediction

- prediction changes

- AI live analysis

---

# 26. DESIGN LANGUAGE

The application should feel like a serious football analytics product.

Visual direction:

- dark interface

- modern typography

- strong hierarchy

- subtle borders

- professional cards

- clean tables

- high information density

- readable charts

- responsive layouts

- smooth but restrained interactions

Avoid:

- generic admin-dashboard appearance

- excessive gradients

- excessive animations

- giant empty cards

- meaningless KPI counters

- fake "AI magic" UI

---

# 27. TURKISH UI

The user-facing interface should primarily be Turkish.

Examples:

Dashboard → Gösterge Paneli

Matches → Maçlar

Predictions → Tahminler

Analytics → Analiz

Backtesting → Geri Test

Live → Canlı

Teams → Takımlar

Players → Oyuncular

AI Analyst → AI Analisti

Settings → Ayarlar

Keep technical code identifiers in English.

---

# 28. DATA QUALITY

Every important data object should eventually contain metadata such as:

- source

- fetched_at

- updated_at

- freshness

- provider

- confidence/data quality indicators where appropriate

Do not silently mix data from incompatible sources.

---

# 29. OBSERVABILITY

Create useful logging.

The system should make it possible to diagnose:

- API errors

- provider failures

- stale data

- model failures

- invalid probabilities

- database failures

- AI failures

---

# 30. TESTING

Build tests progressively.

At minimum, test:

- probability normalization

- Poisson calculations

- scoreline distributions

- 1X2 calculations

- BTTS calculations

- totals calculations

- fair odds

- feature calculations

- calibration calculations

- backtesting time boundaries

- API validation

- AI AnalysisContext generation

Frontend should also be build-verified.

---

# 31. DEVELOPMENT STRATEGY

Do NOT attempt to implement every feature at once.

Build vertically.

PHASE 1:

Project inspection

↓

Frontend structure

↓

FastAPI backend

↓

API connection

↓

Football domain models

↓

Development data provider

↓

Basic feature engine

↓

Poisson model

↓

1X2 prediction

↓

Goals prediction

↓

BTTS

↓

Correct score

↓

AnalysisContext

↓

Ollama AI Analyst

↓

Frontend presentation

↓

Tests

↓

Build verification

This is the first functional milestone.

---

# 32. PHASE 2

After Phase 1 works:

- Elo

- Dixon-Coles

- form models

- xG models

- additional markets

- model registry

- model versioning

- ensemble

---

# 33. PHASE 3

Then:

- calibration

- backtesting

- historical performance

- model comparison

- reliability charts

---

# 34. PHASE 4

Then:

- real data providers

- historical data ingestion

- database expansion

- team/player analytics

---

# 35. PHASE 5

Then:

- live data

- live prediction engine

- live AI Analyst

- event-driven architecture

---

# 36. PHASE 6

Then:

- advanced models

- additional prediction motors

- meta models

- advanced player markets

- advanced analytics

---

# 37. IMPORTANT AGENT BEHAVIOR

You are an autonomous coding agent.

When you encounter a problem:

DO NOT simply tell the user how to fix it.

Inspect the problem.

Diagnose it.

Modify the appropriate files.

Run the relevant command/test.

Fix the issue.

Continue.

When you need information from the existing project:

READ THE FILES.

Do not guess.

When you need to make an architectural decision:

Choose the simplest production-quality solution that keeps the architecture extensible.

Do not ask unnecessary questions.

---

# 38. DO NOT FAKE COMPLETION

Never say:

"implemented"

unless the code actually exists.

Never say:

"tested"

unless you actually ran the test.

Never say:

"working"

unless you verified it.

Never create fake API responses that look like production data without labeling them as development/mock data.

---

# 39. FIRST ACTION NOW

You are currently connected to the project.

Start immediately.

First inspect:

C:\FootballIntelligence

Then inspect:

C:\FootballIntelligence\frontend

Then inspect the existing files and package configuration.

Determine exactly what already exists.

After inspection:

1. Establish the backend structure.

2. Establish frontend architecture.

3. Create the first real API endpoint.

4. Create the football domain model.

5. Create a clearly labeled development data provider.

6. Implement the first real prediction engine using Poisson mathematics.

7. Produce structured prediction output.

8. Produce AnalysisContext.

9. Connect AnalysisContext to local Ollama.

10. Display the result in the React frontend.

11. Add tests.

12. Run the frontend build.

13. Verify the backend.

14. Fix all errors found.

DO NOT STOP AT THE PLANNING STAGE.

The objective is to leave the repository in a more functional state than you found it.

Begin implementation now.

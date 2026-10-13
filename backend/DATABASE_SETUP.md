# Database Setup Guide

This document describes how to initialize and manage the MENSIONE backend database.

## Overview

The MENSIONE backend uses:
- **SQLAlchemy** as the ORM
- **Alembic** for schema migrations
- **PostgreSQL** for production (recommended)
- **SQLite** for development/testing (fallback)

## Database Configuration

Database connection is configured via the `DATABASE_URL` environment variable.

### Development (SQLite)

```bash
# .env
DATABASE_URL=sqlite:///./mensione.db
```

### Production (PostgreSQL)

```bash
# .env
DATABASE_URL=postgresql://user:password@localhost:5432/mensione
```

## Initial Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Apply Migrations

Run all pending migrations to create the database schema:

```bash
# From backend directory
alembic upgrade head
```

This will create all required tables:
- `provider_sources` — Data provider metadata
- `competitions` — Football competitions/leagues
- `teams` — Team information
- `players` — Player information
- `matches` — Match records with scores and metadata
- `match_events` — Goals, cards, substitutions
- `standings` — League table positions
- `match_statistics` — Match stats including xG
- `latency_logs` — Real-time data freshness tracking

### 3. Verify Setup

Check that tables were created:

```bash
# SQLite
sqlite3 mensione.db ".tables"

# PostgreSQL
psql -d mensione -c "\dt"
```

## Migration Management

### Check Current Version

```bash
alembic current
```

### View Migration History

```bash
alembic history
```

### Create New Migration

After modifying database models:

```bash
alembic revision --autogenerate -m "Description of changes"
```

**Always review the generated migration file before applying it.**

### Apply Migration

```bash
alembic upgrade head
```

### Rollback Migration

```bash
# Rollback one version
alembic downgrade -1

# Rollback to specific version
alembic downgrade <revision_id>
```

## Existing Migrations

### a0c16f627575_initial_schema.py

Initial database schema for the intelligence pipeline:
- Core entities: Provider sources, competitions, teams, players
- Match data: Matches, events, statistics
- Standing data: League tables
- Latency tracking: Real-time data freshness metrics

**Applied**: This migration must be applied before the application can use database persistence.

## Testing

Tests use an in-memory SQLite database that is created and destroyed for each test session:

```python
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
```

No migration application is needed for tests.

## Data Integrity

### Idempotent Ingestion

The repository layer ensures idempotent upserts via composite unique constraints on `(provider_source_id, provider_id)`.

### None-Overwrite Protection

**Critical**: The `upsert_by_provider_id` method NEVER overwrites non-None fields with None values. This ensures that missing optional fields in a later provider response don't erase valid data.

Example:
```python
# First ingest: venue_name = "Emirates Stadium"
match1 = ingest_match(provider_match_with_venue)

# Second ingest: venue_name = None (missing from provider)
match2 = ingest_match(provider_match_without_venue)

# Result: venue_name is still "Emirates Stadium" (preserved)
```

### Provider Separation

Different providers with the same external ID create separate database records. Each record is uniquely identified by `(provider_source_id, provider_id)`.

## Troubleshooting

### "No such table" Error

Run migrations:
```bash
alembic upgrade head
```

### Migration Conflicts

If you modified models without creating a migration:
```bash
alembic revision --autogenerate -m "Sync schema"
alembic upgrade head
```

### Database Locked (SQLite)

SQLite doesn't support high concurrency. For production, use PostgreSQL.

### Connection Refused (PostgreSQL)

Check:
1. PostgreSQL is running: `systemctl status postgresql`
2. Database exists: `psql -l`
3. User has permissions: `psql -d mensione -c "\du"`

## Production Checklist

Before deploying to production:

- [ ] Use PostgreSQL (not SQLite)
- [ ] Set `DATABASE_URL` with production credentials
- [ ] Run `alembic upgrade head` to apply all migrations
- [ ] Verify tables exist and have correct indexes
- [ ] Test idempotent ingestion with sample data
- [ ] Configure connection pooling in `app/database/session.py`
- [ ] Set up database backups
- [ ] Monitor query performance and add indexes as needed

## Support

For database-related issues, check:
- `alembic/versions/` for migration history
- `app/database/models.py` for schema definitions
- `app/database/repository.py` for data access patterns
- `tests/test_database.py` for expected behavior

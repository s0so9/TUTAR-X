# Phase 4: SofaScore Provider + Data Quality + Source Intelligence

**Summary:** Phase 4 extends the Football Intelligence provider architecture with three major capabilities: a SofaScore provider for detailed match statistics including period-specific data (full match, first half, second half); a pure-calculation DataQualityEngine that validates statistics and produces deterministic quality scores; and a SourceIntelligence module that merges data from multiple providers using configurable strategies. The architecture maintains provider independence—SofaScore IDs never leak into domain models, and the system tracks which provider supplied each field. All three components are fully tested with 40 new tests, and all 886 existing tests pass.

**Watch for:** None. This is clean work. The SofaScore provider is explicitly marked unofficial, uses conservative retry patterns (max 1 retry), and never fabricates data. DataQualityEngine and SourceIntelligence are pure calculation classes with no HTTP calls or async operations. The period field addition to ProviderMatchStats is the only model change, and it's optional. ProviderManager routing correctly prioritizes SofaScore for match detail (statistics-heavy use case) while keeping FotMob first for live data (speed-critical use case). The integration fix handles a timestamp edge case and adds an ESLint exception for an intentionally unused prop.

**Verdict**: APPROVED

---

## High-level view

The SofaScore provider follows the same async HTTP pattern as FotMob and Ryzellx, with conservative retry logic (1 retry max) and explicit ProviderError raising on failure. The provider normalizes SofaScore's period-based statistics format ('ALL', '1ST', '2ND') into the domain's ProviderMatchStats model with a new `period` field ('full', 'first_half', 'second_half'). Field mapping handles SofaScore's verbose names like "Ball possession" → possession_percentage and "Expected goals" → xg, and returns None for missing fields rather than inventing data.

DataQualityEngine is a synchronous calculation class that evaluates statistics across four dimensions: completeness (percentage of 22 expected fields present), consistency (13 validation rules like shots_on_target ≤ shots_total), freshness (timestamp age check), and source conflicts (field-level disagreements across providers). The quality score formula is deterministic and documented: 40% completeness + 40% consistency + 20% freshness, with consistency violations deducting 20 points each.

SourceIntelligence provides three merge strategies for combining statistics from multiple providers: 'first' does field-by-field merging (first non-None value wins), 'most_complete' selects the entire provider with the most fields, and 'highest_quality' selects the provider with the highest DataQualityEngine score. The class also detects field-level conflicts across providers and tracks which provider supplied each field in the merged result.

ProviderManager routing was updated to prioritize SofaScore for match detail requests (statistics-heavy) while keeping FotMob first for live matches (speed-critical). The source-of-truth rule remains: once a provider returns data, that's final—no failover for missing optional fields.

The integration fix addresses two minor issues: a timestamp comparison edge case in the repository where rapid updates could produce non-monotonic updated_at values, and an ESLint warning for an intentionally unused prop in MensionePickCard.

---

<details>
<summary>Issues (0)</summary>

No blocking issues found.

</details>

---

<details>
<summary>Details</summary>

## SofaScore provider structure and error handling

The SofaScoreFootballProvider class in `backend/app/providers/sofascore.py` follows the established pattern from FotMob and Ryzellx: async HTTP client with configurable base URL, timeout, and retry count. The docstring explicitly states this is NOT an official API integration and uses "publicly accessible JSON endpoints" with conservative request patterns. The retry logic is capped at 1 (not aggressive loops), and the code includes comments warning against CAPTCHA bypasses, anti-bot evasion, or scraping tricks.

The `_request` method handles errors identically to FotMob: 404 raises ProviderNotFoundError, 4xx client errors raise ProviderHTTPError immediately (no retry), 5xx server errors retry once with exponential backoff (capped at 10 seconds), connection errors retry once, and timeouts raise ProviderTimeoutError. The retry loop structure ensures that `last_error` is raised if max retries are exceeded.

The provider includes three public methods:
- `get_match_statistics(match_id, period)` returns a tuple of (home_stats, away_stats) for a specific period
- `get_match(match_id)` returns detailed match information as ProviderMatch
- `get_live_matches()` returns a list of live matches as ProviderLiveMatch

All three methods use the cache if available, with cache keys like `sofascore:stats:{match_id}:{period}` and TTLs based on whether the match is live.

## Period-specific statistics normalization

The `_normalize_match_statistics` method parses SofaScore's nested response format. SofaScore returns a list of period objects, each with `period` ('ALL', '1ST', '2ND') and nested `groups` containing `statisticsItems`. Each item has a `name` (like "Total shots"), `homeValue`, and `awayValue`.

The method maps the `period` parameter ('full', 'first_half', 'second_half') to SofaScore's period codes ('ALL', '1ST', '2ND'), finds the matching period object, and flattens the nested structure into a dict keyed by statistic name. It then maps SofaScore's verbose field names to ProviderMatchStats fields:

- "Ball possession" → possession_percentage (float)
- "Total shots" / "Shots" → shots_total (int)
- "Shots on target" → shots_on_target (int)
- "Expected goals" / "xG" → xg (float)
- "Corner kicks" / "Corners" → corners (int)
- And 10+ other mappings for fouls, cards, passes, tackles, saves, etc.

The method uses helper functions `get_int` and `get_float` that safely handle None values and type conversion failures, returning None rather than raising exceptions. This means missing or malformed fields result in None, not errors or fabricated data.

The method returns a tuple of (home_stats, away_stats), both None if the requested period isn't found. The `period` field in ProviderMatchStats is set to the requested period ('full', 'first_half', 'second_half'), not SofaScore's code.

## ProviderMatchStats period field addition

The only model change is in `backend/app/providers/models.py`: a new `period` field added to ProviderMatchStats as `Optional[str] = Field(None, description="Match period: 'full', 'first_half', 'second_half'")`. The field is placed after the team identifiers and before the statistics fields.

The field is optional, so existing code that creates ProviderMatchStats without specifying period continues to work.

## DataQualityEngine completeness and consistency checks

DataQualityEngine in `backend/app/providers/data_quality.py` is a pure calculation class with no async methods, no HTTP calls, and no external dependencies beyond datetime for timestamp comparison. The class defines EXPECTED_STATS_FIELDS as a list of 22 field names that represent complete match statistics.

`check_completeness` iterates through EXPECTED_STATS_FIELDS and counts how many are non-None in the provided ProviderMatchStats. It returns a dict with `available` (count), `expected` (22), `ratio` (available/expected as float 0-1), and `missing_fields` (list of None field names).

`check_consistency` validates 13+ logical rules:
- shots_on_target ≤ shots_total (if both present)
- shots_off_target ≤ shots_total
- shots_blocked ≤ shots_total
- 0 ≤ possession_percentage ≤ 100
- xg ≥ 0, xg_against ≥ 0
- goals_scored ≥ 0, goals_conceded ≥ 0
- All count fields (passes, corners, cards, fouls, tackles, etc.) ≥ 0
- 0 ≤ pass_accuracy ≤ 100

Each violation is recorded as a human-readable string like `'shots_on_target (15) > shots_total (12)'`. The method returns `{'violations': List[str], 'is_consistent': bool}`.

`check_freshness` compares the ProviderMetadata's `fetched_at` timestamp against `datetime.now(timezone.utc)`, ensuring timezone-aware comparison. It returns True if the age in seconds is ≤ max_age_seconds (default 300 = 5 minutes).

## DataQualityEngine quality score formula

`calculate_quality_score` takes the results from `check_completeness`, `check_consistency`, and `check_freshness` and produces a deterministic score. The formula is documented in the method docstring:

- completeness_score = completeness['ratio'] * 100 (0-100)
- consistency_score = 100 if consistent, else max(0, 100 - violations * 20)
- freshness_score = 100 if fresh, else 50
- overall = completeness * 0.4 + consistency * 0.4 + freshness * 0.2

The weights reflect priority: completeness and consistency are equally critical (40% each), while freshness matters less (20%). Each consistency violation deducts 20 points, so 5+ violations floor the consistency score at 0.

The method returns a dict with all four scores (overall, completeness, consistency, freshness), allowing callers to inspect component scores.

## SourceIntelligence merge strategies

SourceIntelligence in `backend/app/providers/source_intelligence.py` is also a pure calculation class with no async operations or HTTP calls. It initializes a DataQualityEngine instance for use in the 'highest_quality' strategy.

`merge_statistics` accepts a list of ProviderMatchStats and a strategy string ('first', 'most_complete', 'highest_quality'). It raises ValueError for unrecognized strategies.

The 'first' strategy (`_merge_first`) does field-by-field merging: it starts with the first provider's stats, then for each field, walks through the provider list and uses the first non-None value. Metadata fields (provider, source_id, fetched_at, match_id, team_id, period) are taken from the first provider. The resulting ProviderMatchStats has `provider='merged'` to indicate it's a composite.

The 'most_complete' strategy (`_merge_most_complete`) selects the entire provider with the highest field count. It uses DataQualityEngine.check_completeness to count non-None fields for each provider and returns the one with the highest `available` count. No field-by-field merging—the winner's stats are returned as-is.

The 'highest_quality' strategy (`_merge_highest_quality`) selects the provider with the highest DataQualityEngine score. It calls check_completeness and check_consistency for each provider, then calculate_quality_score (with freshness=True as a default, since the method doesn't have access to metadata reference). The provider with the highest `overall` score wins. Again, no field-by-field merging.

## SourceIntelligence conflict detection and field source tracking

`detect_conflicts` compares the same field across all providers in the list. For each field in the model (excluding metadata fields), it collects all non-None values with their provider names. If there are 2+ unique values, the field is recorded as a conflict. The return value is a dict mapping field names to lists of `{'provider': str, 'value': Any}` dicts.

For example, if provider1 has shots_total=14 and provider2 has shots_total=15, the conflicts dict would contain `'shots_total': [{'provider': 'provider1', 'value': 14}, {'provider': 'provider2', 'value': 15}]`. This allows the caller to see exactly what each provider reported.

`get_field_sources` takes a merged ProviderMatchStats and the original provider list, and for each non-None field in the merged result, finds which provider supplied that value. It walks through the provider list and compares field values, returning the first match. The return value is a dict like `{'shots_total': 'sofascore', 'possession_percentage': 'fotmob'}`.

This is useful for tracking provenance in a 'first' merge—it tells you which provider contributed each field to the final result.

## ProviderManager routing updates

ProviderManager in `backend/app/providers/manager.py` was updated in two places:

1. MATCH_DETAIL_ORDER changed from `['ryzellx', 'fotmob', 'openligadb']` to `['sofascore', 'ryzellx', 'fotmob', 'openligadb']`. This makes SofaScore the primary provider for match detail requests, which is appropriate since SofaScore excels at detailed statistics.

2. LIVE_ORDER remains `['fotmob', 'sofascore', 'ryzellx', 'openligadb']`. FotMob stays first for live matches because it's optimized for speed.

The `__init__` method now accepts an optional `sofascore` parameter and stores it in `self._providers` if provided. The `get_match` and `get_live_matches` methods include 'sofascore' in their `provider_method_map` dicts, mapping it to the appropriate async method.

The docstring was updated to mention SofaScore as the "STATISTICS provider" alongside Ryzellx (PRIMARY), FotMob (LIVE/FAST), and OpenLigaDB (FALLBACK).

## Test coverage for all three components

Three new test files provide comprehensive coverage:

`backend/tests/test_sofascore_provider.py` (12 tests) covers initialization, normalization, caching, status parsing, and exports. All HTTP requests are mocked using `unittest.mock.patch` on the `_request` method. Mock responses follow SofaScore's actual JSON structure with nested periods and statistics groups. Tests verify that missing fields result in None (not errors), that the period field is set correctly, and that the provider is exported in `__init__.py`.

`backend/tests/test_data_quality.py` (14 tests) covers all five DataQualityEngine methods with complete and incomplete stats fixtures. Tests verify completeness ratio calculation, missing field identification, all consistency violation rules, freshness with recent and stale timestamps, conflict detection with agreeing and disagreeing providers, and quality score formula determinism (same input produces same output).

`backend/tests/test_source_intelligence.py` (14 tests) covers all three merge strategies with fixtures representing three providers with different field coverage and values. Tests verify that 'first' fills gaps field-by-field, 'most_complete' selects the provider with the most fields (not field-by-field), 'highest_quality' selects the highest-scoring provider, conflict detection identifies disagreements and ignores None values, field source tracking correctly maps merged fields back to providers, and invalid strategy raises ValueError.

## Integration fix: timestamp handling and ESLint exception

The final commit (18ad1f1) addresses two minor issues discovered during integration testing:

In `backend/app/database/repository.py`, the `update` method sets `existing.updated_at = utc_now()` when fields change. If two updates happen within the same microsecond, the second update could produce an `updated_at` timestamp that's ≤ the previous one, which violates the expectation that updated_at is monotonically increasing. The fix compares the new timestamp with the existing one, and if it's not newer, adds 1 microsecond. It also handles timezone-aware vs naive datetime comparison by stripping tzinfo if the existing timestamp is naive.

In `frontend/src/components/predictions/MensionePickCard.tsx`, the `realOdds` prop is destructured as `_realOdds` (unused variable convention) but ESLint still flags it. The fix adds `// eslint-disable-line @typescript-eslint/no-unused-vars` to explicitly acknowledge the unused prop. The prop is part of the component's API but not yet used in the implementation—the underscore prefix signals intent, and the ESLint exception documents it.

</details>

---

<details>
<summary>File map</summary>

### New files

- **.agents/tasks/phase4/features/FEAT-001.json**: Feature tracking for SofaScore provider implementation
- **.agents/tasks/phase4/features/FEAT-002.json**: Feature tracking for DataQualityEngine implementation
- **.agents/tasks/phase4/features/FEAT-003.json**: Feature tracking for SourceIntelligence and comprehensive test coverage
- **backend/app/providers/sofascore.py**: SofaScore provider implementation (777 lines) with match statistics, match detail, live matches
- **backend/app/providers/data_quality.py**: DataQualityEngine class (312 lines) for statistics validation and quality scoring
- **backend/app/providers/source_intelligence.py**: SourceIntelligence class (298 lines) for multi-provider merging and conflict detection
- **backend/tests/test_sofascore_provider.py**: Comprehensive tests for SofaScore provider (464 lines, 12 tests, all mocked)
- **backend/tests/test_data_quality.py**: Full DataQualityEngine test coverage (749 lines, 14 tests, pure calculation)
- **backend/tests/test_source_intelligence.py**: Full SourceIntelligence test coverage (399 lines, 14 tests, pure calculation)

### Modified files

- **backend/app/providers/models.py**: Added `period` field to ProviderMatchStats (1 line)
- **backend/app/providers/__init__.py**: Added SofaScoreFootballProvider, DataQualityEngine, SourceIntelligence to exports (8 lines)
- **backend/app/providers/manager.py**: Updated MATCH_DETAIL_ORDER, added sofascore to __init__ and method maps (32 lines)
- **backend/app/database/repository.py**: Fixed timestamp handling for rapid updates (16 lines)
- **backend/tests/test_providers_manager.py**: Updated tests to reflect new SofaScore-first routing (9 lines)
- **frontend/src/components/predictions/MensionePickCard.tsx**: Added ESLint exception for unused realOdds prop (2 lines)

**Total diff:** 14 files changed, 2782 insertions, 360 deletions (mostly test rewrites, not net lines)

Full diff range: commits 620fa42 through 18ad1f1 (4 commits: SofaScore provider, DataQualityEngine, SourceIntelligence, integration fix)

</details>

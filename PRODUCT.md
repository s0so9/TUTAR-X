# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Now:** a closed team of two (the owner and a friend) who build and use TUTAR X themselves to analyse matches and evaluate betting markets before and during games.
- **Later (not decided when):** opening to İddaa/betting players and football enthusiasts. Until then, design for expert daily use by the builders, not for first-time visitors.

## Product Purpose

TUTAR X ("Maçın geleceğini veriden oku.") is a football intelligence workstation: it collects match data, computes team strength and match probabilities with a numerical engine, compares them with bookmaker odds, and shows live matches. Success means the team can, for any fixture, see at a glance how likely each outcome is, how that compares with the market, what is missing from the squads, and whether a pick is worth taking — and later verify how the predictions performed.

## Positioning

Numbers come from a tested statistical engine, not from opinion or an AI: global team ratings plus a starting-XI market-value adjustment, validated by walk-forward backtests (see `docs/live-tests/2026-10-13-ucl.md`). The product says "veri yok" instead of guessing, labels unverified odds, and refuses to call a model–market gap "value" when it is implausible. Honesty about uncertainty is the differentiator against tipster sites.

## Operating Context

- Primary use is on a desktop browser during focused analysis sessions; matchday use includes following live matches.
- An Android wrapper (Capacitor) exists in the codebase but is secondary.
- Typical session: open today's fixtures → pick a match → read probabilities, market comparison, squad/injury status → decide on picks / build a combination (kombine) → follow live → check results afterwards.
- Data sources: FotMob (unofficial API) for fixtures, scores and line-ups; odds currently entered manually by the team (`sampiyonlar-ligi/`), optionally The Odds API.

## Capabilities and Constraints

- Stack (existing): React + TypeScript + Vite frontend (`frontend/`), FastAPI backend (`backend/`, port 8003). Mandated by `AGENTS.md`.
- Existing surfaces: dashboard (today's picks + match centre), match centre (league-grouped list by date), match detail (probabilities, xG, pick card, form/H2H, squad status), live list/detail, predictions, easy matches, favourites, combination builder, settings/analytics stubs.
- Planned by spec but not built: teams, players, backtesting, AI Analyst pages.
- Honesty rules (binding, `AGENTS.md`): never invent statistics; missing data shown explicitly ("veri yok"), never as 0; mock/dev data labelled; unverified odds labelled "Kullanıcı girişli oran (doğrulanmadı)"; model–market conflicts shown as warnings, never as value.
- Terminology: Turkish UI (Maçlar, Canlı, Tahminler, Kombine, KG Var, Alt/Üst, Ev/Beraberlik/Deplasman, Seçim); English code identifiers.
- Undecided: whether/when to open publicly; monetisation.

## Brand Commitments

- Name **TUTAR X**, tagline **"Maçın geleceğini veriden oku."**; logo files in `frontend/public/` (`logo*`).
- `PROJECT_SPEC.md` §26 asks for a serious analytics product and explicitly avoids generic admin-dashboard looks, excessive gradients and animations, giant empty cards, meaningless KPI counters and fake "AI magic" UI.
- Owner's request (2026-10-13): drop the "AI slop" look; useful, clickable, animated interactions that do not overwhelm.

## Evidence on Hand

- Real data in the local DB: ~86k finished matches (2025-07 → 2026-10), FotMob line-up values and injury lists for upcoming matches.
- Validation results and frozen predictions: `docs/live-tests/2026-10-13-ucl.md`, `docs/live-tests/2026-10-13/`.
- No users, testimonials, track record, or public performance claims exist yet; none may be invented. Settlement / track record is not yet automated.

## Product Principles

1. The numerical engine is the source of truth; the UI explains it, never embellishes it.
2. Uncertainty is shown, not hidden: probabilities over verdicts, "veri yok" over guesses, warnings over false confidence.
3. The market is the benchmark: every probability should be easy to compare with the bookmakers' view.
4. Built for repeated expert use: fast scanning, dense but calm, every metric has a purpose.
5. Provenance is visible: where a number came from (model, FotMob, user-entered odds) is always discoverable.

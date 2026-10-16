"""Research figures behind rule headline_v2 (docs/research/2026-10-15-accuracy-roadmap.md, Paket 1).

Reads the research outputs in backend/data/research (no football data is created here) and checks the
links the app relies on:
  * the 13 competitions the tracker follows (settings.featured_competition_ids) are the "featured_ids" of
    review_roadmap_feasibility.json and a subset of the 20 tested competitions (sel_test.json ->
    C_rules.per_comp_R1); the frontend checks its own copy of the 20 ids against the same file
    (frontend/src/utils/__tests__/headlineEvidence.test.ts);
  * the ~300 recorded Bankos of the Sonuclar page is the sample-size row of roadmap_live_sample_size.json;
  * the tier floors are band edges of sel_test.json -> C_rules.banko_bands.
"""

import json
from pathlib import Path

from app.config import Settings
from app.prediction.headline_picks import BANKO_MAX_P, BANKO_MIN_P, TIER_BANKO_MIN_P, TIER_COK_GUCLU_MIN_P
from app.services.headline_tracking.report import BANKO_PROOF_TARGET

RESEARCH = Path(__file__).resolve().parents[1] / "data" / "research"


def _load(name: str) -> dict:
    return json.loads((RESEARCH / name).read_text(encoding="utf-8"))


def _featured_default() -> set:
    default = Settings.model_fields["featured_competition_ids"].default
    return {x.strip() for x in default.split(",") if x.strip()}


def test_tracked_competitions_are_tested_competitions():
    tested = set(_load("sel_test.json")["C_rules"]["per_comp_R1"])
    featured = _featured_default()
    assert len(tested) == 20 and len(featured) == 13
    assert featured <= tested
    assert set(_load("review_roadmap_feasibility.json")["featured_ids"]) == featured
    assert {"42", "73", "10216"} <= featured  # the three UEFA club competitions


def test_proof_target_is_the_sample_size_row_of_the_research():
    rows = _load("roadmap_live_sample_size.json")["by_sample_size"]
    row = next(r for r in rows if r["n_picks"] == BANKO_PROOF_TARGET)
    assert BANKO_PROOF_TARGET == 300
    assert row["wilson90_if_observed_0.90"] == [0.8678, 0.925]


def test_tier_floors_are_band_edges_of_the_research():
    bands = _load("sel_test.json")["C_rules"]["banko_bands"]
    edges = sorted({float(edge) for key in bands for edge in key.split("-")})
    assert edges[0] == BANKO_MIN_P and edges[-1] == BANKO_MAX_P
    assert TIER_BANKO_MIN_P in edges and TIER_COK_GUCLU_MIN_P in edges
    # the research rules for the two strongest tiers
    all_test = _load("sel_test.json")["C_rules"]["all_test"]
    assert all_test["R1_banko85"]["n"] == bands["0.85-0.90"]["n"] + bands["0.90-0.95"]["n"]
    assert all_test["R3_banko90"]["hit"] == bands["0.90-0.95"]["hit"]

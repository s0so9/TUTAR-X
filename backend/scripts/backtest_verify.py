"""Representative backtest verification script.

Run from backend directory:
    python scripts/backtest_verify.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.providers.development import DevelopmentProvider
from app.domain.enums import MatchStatus
from app.prediction.backtest import (
    run_backtest, poisson_predict_fn, elo_predict_fn,
    negative_binomial_predict_fn, logistic_regression_predict_fn
)
from app.prediction.comparison import (
    ModelComparator, RankingMetric, snapshot_from_backtest_metrics
)

provider = DevelopmentProvider()
all_matches = provider.get_matches()
finished = [m for m in all_matches if m.status == MatchStatus.FINISHED]
print(f"Finished matches: {len(finished)}")

# --- Synthetic data test (enough matches to exercise all windows) ---
from datetime import datetime, timedelta
from app.domain.match import Match

def _synth(n=50):
    teams = ["A", "B", "C", "D"]
    result = []
    for i in range(n):
        h, a = teams[i % 4], teams[(i + 1) % 4]
        hs, as_ = (2, 0) if i % 3 == 0 else (1, 1) if i % 3 == 1 else (0, 1)
        result.append(Match(
            id=f"m{i}",
            competition_id="c1", season_id="s1",
            home_team_id=h, away_team_id=a,
            scheduled_at=datetime(2024, 1, 1) + timedelta(days=i),
            status=MatchStatus.FINISHED,
            home_score=hs, away_score=as_,
        ))
    return result

synth_matches = _synth(50)
print(f"Synthetic matches: {len(synth_matches)}")

adapters = [
    ("poisson",  poisson_predict_fn()),
    ("neg_binom", negative_binomial_predict_fn()),
    ("elo",      elo_predict_fn()),
    ("lr",       logistic_regression_predict_fn()),
]

results = {}
for name, fn in adapters:
    r = run_backtest(
        synth_matches, fn,
        model_id=name, mode="expanding",
        min_train=5, test_size=3, step_size=3,
    )
    results[name] = r
    m = r.metrics
    acc = f"{m.accuracy:.3f}" if m.accuracy is not None else "N/A"
    brier = f"{m.brier_score:.4f}" if m.brier_score is not None else "N/A"
    print(f"  {name:12s}: n={m.n_predictions:3d}  acc={acc}  brier={brier}  reliable={m.is_reliable}")

snapshots = [
    snapshot_from_backtest_metrics(results[k].metrics, model_type=k)
    for k in results
]
comp = ModelComparator(primary_metric=RankingMetric.BRIER_SCORE)
comparison = comp.compare(snapshots)

print("\nRankings (Brier score, lower=better):")
for r in comparison.rankings:
    val = f"{r.primary_metric_value:.4f}" if r.primary_metric_value is not None else "N/A"
    print(f"  Rank {r.rank}: {r.model_id:12s}  brier={val}  reliable={r.is_reliable}")

print(f"\nBest model: {comparison.best_model_id}  has_reliable_winner={comparison.has_reliable_winner}")
if comparison.warnings:
    for w in comparison.warnings:
        print(f"  WARN: {w}")

print("\nBacktest + comparison verification: OK")

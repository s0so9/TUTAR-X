from app.providers.development import DevelopmentProvider
from app.features import MatchFeatureExtractor
from app.prediction.feature_snapshot import extract_feature_snapshot, TeamStrengthMetrics, FormMetrics
from app.prediction.data_quality import DataQualityGate

provider = DevelopmentProvider()
match = provider.get_match('dev_match_002')
print(f'Match: {match.home_team_id} vs {match.away_team_id}')

extractor = MatchFeatureExtractor(provider=provider, min_matches=3, recent_matches=5)
features = extractor.extract_features(match)
print(f'\nFeatures from extractor ({len(features)} total):')
for key in sorted(features.keys()):
    if features[key] is not None:
        print(f'  {key}: {features[key]}')

print(f'\nKey fields for Poisson:')
print(f'  home_goals_scored_avg: {features.get("home_goals_scored_avg")}')
print(f'  away_goals_scored_avg: {features.get("away_goals_scored_avg")}')
print(f'  home_attack_strength: {features.get("home_attack_strength")}')

# Now build snapshot
gate = DataQualityGate()
dq_report = gate.assess(features)
snapshot = extract_feature_snapshot(
    match_id=match.id,
    home_team_id=match.home_team_id,
    away_team_id=match.away_team_id,
    feature_set=None,
    data_quality_report=dq_report
)
print(f'\nSnapshot home_strength: {snapshot.home_strength}')
print(f'Snapshot away_strength: {snapshot.away_strength}')

# Get feature dict
feature_dict = snapshot.get_feature_dict()
print(f'\nFeature dict from snapshot ({len(feature_dict)} total):')
for key in sorted(feature_dict.keys()):
    if feature_dict[key] is not None:
        print(f'  {key}: {feature_dict[key]}')

print(f'\nKey fields in feature_dict:')
print(f'  home_goals_scored_avg: {feature_dict.get("home_goals_scored_avg")}')
print(f'  away_goals_scored_avg: {feature_dict.get("away_goals_scored_avg")}')

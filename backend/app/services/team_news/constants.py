"""Constants of the team-news live layer (sources, statuses, competitions).

Technical identifiers are English; ``SOURCE_LABELS_TR`` holds the Turkish
labels the UI shows next to each piece of data.
"""

from __future__ import annotations

# Europe's 10 strongest leagues by UEFA association coefficient + the three UEFA
# club competitions (FotMob league ids).
TARGET13_COMPETITIONS: tuple[int, ...] = (47, 87, 55, 54, 53, 57, 61, 40, 71, 122, 42, 73, 10216)

# Data sources (stored in the `source` columns).
SOURCE_TEAM_SQUAD = "fotmob_team_squad"  # /api/data/teams?id=<team> -> squad.squad
SOURCE_MATCH_LINEUP = "fotmob_match_lineup"  # /api/data/matchDetails -> content.lineup
SOURCE_PLAYER_PROFILE = "fotmob_player_profile"  # /api/data/playerData?id=<player>
SOURCE_MATCH_DETAILS = "fotmob_match_details"  # player_match_stats (content.playerStats + lineup)

AVAILABILITY_SOURCES = (SOURCE_TEAM_SQUAD, SOURCE_MATCH_LINEUP, SOURCE_PLAYER_PROFILE)

# Availability statuses.
STATUS_INJURED = "injured"
STATUS_SUSPENDED = "suspended"
STATUS_DOUBTFUL = "doubtful"
STATUS_INTERNATIONAL_DUTY = "international_duty"
STATUS_OTHER = "other"
AVAILABILITY_STATUSES = (
    STATUS_INJURED,
    STATUS_SUSPENDED,
    STATUS_DOUBTFUL,
    STATUS_INTERNATIONAL_DUTY,
    STATUS_OTHER,
)

# FotMob unavailability "type" values observed in matchDetails
# (content.lineup.<side>Team.unavailable[*].unavailability.type).
RAW_TYPE_TO_STATUS = {
    "injury": STATUS_INJURED,
    "suspension": STATUS_SUSPENDED,
    "internationalDuty": STATUS_INTERNATIONAL_DUTY,
    "doubtful": STATUS_DOUBTFUL,
}

# How a timestamp of an observation was obtained.
BASIS_OBSERVED = "observed"  # wall-clock time of the fetch that returned the data
BASIS_MATCH_KICKOFF = "match_kickoff"  # backfilled from a post-match response: the list applies at kickoff

CLEARED_NOT_LISTED = "not_listed"
CLEARED_SUPERSEDED = "superseded"

# Turkish UI labels (user-facing text is Turkish, AGENTS.md rule 20).
SOURCE_LABELS_TR = {
    SOURCE_TEAM_SQUAD: "FotMob takım kadrosu (sakatlık listesi)",
    SOURCE_MATCH_LINEUP: "FotMob maç kadrosu (ilk 11 ve eksikler)",
    SOURCE_PLAYER_PROFILE: "FotMob oyuncu profili",
    SOURCE_MATCH_DETAILS: "FotMob maç detayları (oyuncu istatistikleri)",
    "local_matches": "Yerel maç veritabanı (sonuçlar ve xG)",
}

STATUS_LABELS_TR = {
    STATUS_INJURED: "Sakat",
    STATUS_SUSPENDED: "Cezalı",
    STATUS_DOUBTFUL: "Şüpheli",
    STATUS_INTERNATIONAL_DUTY: "Milli takım görevi",
    STATUS_OTHER: "Diğer",
}

# FotMob content.lineup.lineupType (as sent) -> lineup_status (derived, documented):
#   standard        -> confirmed      official XI published (also the final XI of finished matches)
#   predicted       -> predicted      FotMob's predicted XI for this match
#   lastStarting11  -> last_match_xi  the team's XI of its previous match (lineup.source
#                                     "lastStartingLineups"); a placeholder, NOT a prediction
#   anything else   -> other          e.g. "unavailable"
LINEUP_STATUS_BY_TYPE = {
    "standard": "confirmed",
    "predicted": "predicted",
    "lastStarting11": "last_match_xi",
}
LINEUP_TYPE_LABELS_TR = {
    "predicted": "Tahmini ilk 11 (FotMob)",
    "standard": "Açıklanan ilk 11 (FotMob)",
    "lastStarting11": "Önceki maçın ilk 11'i (FotMob; bu maç için tahmin değil)",
}

# Form window (team matches before kickoff).
FORM_WINDOW_MATCHES = 5

# missing_reason codes used in API responses -> Turkish UI text.
MISSING_REASON_LABELS_TR = {
    "match_not_tracked": "Bu maç yerel veritabanında yok ve kadro haberi servisi tarafından henüz izlenmedi.",
    "lineup_not_observed": "Bu takım için henüz ilk 11 bilgisi (tahmini veya açıklanan) gözlemlenmedi.",
    "team_not_in_local_db": "Takım yerel veritabanında yok; son maçlar hesaplanamıyor.",
    "no_finished_matches_before_kickoff": "Yerel veritabanında bu takımın maç öncesine ait bitmiş maçı yok.",
    "no_player_match_data": "Takımın son maçları için oyuncu bazlı maç verisi (FotMob maç detayları) yok.",
    "partial_player_match_data": "Takımın son maçlarının bir kısmı için oyuncu verisi yok; değerler yalnızca verisi olan maçlardan hesaplandı.",
    "did_not_appear": "Oyuncu, verisi olan son maçlarda forma giymedi.",
    "availability_not_observed": "Bu takım için sakatlık/ceza bilgisi henüz hiçbir kaynaktan gözlemlenmedi; boş liste 'herkes hazır' anlamına gelmez.",
    "team_scored_no_goals": "Takım bu maçlarda gol atmadı; gol payı tanımsız.",
    "team_xg_unavailable": "Bu maçlar için takım xG verisi yok.",
    "player_goals_unavailable": "Oyuncunun gol verisi gönderilmedi.",
    "player_xg_unavailable": "Oyuncunun xG verisi gönderilmedi.",
    "team_minutes_unavailable": "Takımın oynadığı süre hesaplanamadı.",
    "squad_not_observed": "Bu takımın kadrosu henüz çekilmedi.",
    "team_not_found": "Takım bulunamadı.",
}

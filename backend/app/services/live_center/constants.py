"""Constants of the live-center layer (FotMob matchDetails -> live-center contract).

Field paths are documented in docs/live-center-data-sources.md. Everything here
is a label or a mapping; no value is ever invented from these tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

PROVIDER_FOTMOB = "fotmob"

# --------------------------------------------------------------------------- status

STATUS_SCHEDULED = "SCHEDULED"
STATUS_LIVE = "LIVE"
STATUS_HALF_TIME = "HALF_TIME"
STATUS_FINISHED = "FINISHED"
STATUS_POSTPONED = "POSTPONED"
STATUS_CANCELLED = "CANCELLED"
STATUS_ABANDONED = "ABANDONED"
STATUS_EXTRA_TIME = "EXTRA_TIME"
STATUS_PENALTIES = "PENALTIES"

LIVE_STATUSES = frozenset({STATUS_LIVE, STATUS_HALF_TIME, STATUS_EXTRA_TIME, STATUS_PENALTIES})
CLOSED_STATUSES = frozenset({STATUS_FINISHED, STATUS_POSTPONED, STATUS_CANCELLED, STATUS_ABANDONED})

# Cache TTLs of the contract (seconds).
TTL_LIVE_SECONDS = 15
TTL_SCHEDULED_SECONDS = 300
TTL_SCHEDULED_MIN_SECONDS = 15  # close to kick-off the entry expires at kick-off (never below 15 s)
TTL_FINISHED_SECONDS = 3600

# --------------------------------------------------------------------------- events

EVENT_GOAL = "goal"
EVENT_OWN_GOAL = "own_goal"
EVENT_PENALTY_GOAL = "penalty_goal"
EVENT_PENALTY_MISSED = "penalty_missed"
EVENT_YELLOW = "yellow_card"
EVENT_SECOND_YELLOW = "second_yellow"
EVENT_RED = "red_card"
EVENT_SUBSTITUTION = "substitution"
EVENT_VAR = "var"
EVENT_PERIOD_END = "period_end"

# FotMob "Card".card -> contract type
CARD_TYPES = {"Yellow": EVENT_YELLOW, "YellowRed": EVENT_SECOND_YELLOW, "Red": EVENT_RED}

PERIOD_ORDER = {"1H": 0, "HT": 1, "2H": 2, "ET": 3, "PEN": 4, "FT": 5}

# --------------------------------------------------------------------------- lineups

LINEUP_TYPE_MAP = {
    "standard": "confirmed",
    "confirmed": "confirmed",
    "predicted": "predicted",
}

UNAVAILABILITY_REASON_TR = {
    "injury": "Sakatlık",
    "suspension": "Cezalı",
    "international_duty": "Milli takım görevi",
    "internationalduty": "Milli takım görevi",
    "doubtful": "Şüpheli",
    "other": "Diğer",
}

# --------------------------------------------------------------------------- stats

GROUP_GENERAL = "Genel"
GROUP_SHOTS = "Şutlar"
GROUP_PASSES = "Pas"
GROUP_DEFENCE = "Savunma"
GROUP_DISCIPLINE = "Disiplin"

UNIT_COUNT = "count"
UNIT_PERCENT = "percent"
UNIT_DECIMAL = "decimal"


@dataclass(frozen=True)
class StatSpec:
    key: str  # our key (English technical identifier)
    source_keys: tuple[str, ...]  # FotMob stat keys
    label_tr: str
    group: str
    unit: str
    derived: Optional[str] = None  # "percent_of_total": percentage from rawStats value/total


# Stable output order (contract): possession, xG, total shots, shots on target,
# big chances, corners, fouls, offsides, yellow cards, red cards, passes, pass
# accuracy, saves, tackles, then the rest.
STAT_SPECS: tuple[StatSpec, ...] = (
    StatSpec("possession", ("BallPossesion", "BallPossession"), "Topla oynama", GROUP_GENERAL, UNIT_PERCENT),
    StatSpec("xg", ("expected_goals",), "Gol beklentisi (xG)", GROUP_GENERAL, UNIT_DECIMAL),
    StatSpec("total_shots", ("total_shots",), "Toplam şut", GROUP_SHOTS, UNIT_COUNT),
    StatSpec("shots_on_target", ("ShotsOnTarget",), "İsabetli şut", GROUP_SHOTS, UNIT_COUNT),
    StatSpec("big_chances", ("big_chance",), "Net gol fırsatı", GROUP_SHOTS, UNIT_COUNT),
    StatSpec("corners", ("corners",), "Korner", GROUP_GENERAL, UNIT_COUNT),
    StatSpec("fouls", ("fouls",), "Faul", GROUP_DISCIPLINE, UNIT_COUNT),
    StatSpec("offsides", ("Offsides",), "Ofsayt", GROUP_GENERAL, UNIT_COUNT),
    StatSpec("yellow_cards", ("yellow_cards",), "Sarı kart", GROUP_DISCIPLINE, UNIT_COUNT),
    StatSpec("red_cards", ("red_cards",), "Kırmızı kart", GROUP_DISCIPLINE, UNIT_COUNT),
    StatSpec("passes", ("passes",), "Toplam pas", GROUP_PASSES, UNIT_COUNT),
    StatSpec("pass_accuracy", ("accurate_passes",), "Pas isabeti", GROUP_PASSES, UNIT_PERCENT, derived="percent_of_total"),
    StatSpec("saves", ("keeper_saves",), "Kaleci kurtarışı", GROUP_DEFENCE, UNIT_COUNT),
    StatSpec("tackles", ("matchstats.headers.tackles",), "Top çalma (müdahale)", GROUP_DEFENCE, UNIT_COUNT),
    StatSpec("accurate_passes", ("accurate_passes",), "İsabetli pas", GROUP_PASSES, UNIT_COUNT),
    StatSpec("shots_off_target", ("ShotsOffTarget",), "İsabetsiz şut", GROUP_SHOTS, UNIT_COUNT),
    StatSpec("blocked_shots", ("blocked_shots",), "Engellenen şut", GROUP_SHOTS, UNIT_COUNT),
    StatSpec("shots_woodwork", ("shots_woodwork",), "Direkten dönen", GROUP_SHOTS, UNIT_COUNT),
    StatSpec("shots_inside_box", ("shots_inside_box",), "Ceza sahası içinden şut", GROUP_SHOTS, UNIT_COUNT),
    StatSpec("shots_outside_box", ("shots_outside_box",), "Ceza sahası dışından şut", GROUP_SHOTS, UNIT_COUNT),
    StatSpec("big_chances_missed", ("big_chance_missed_title",), "Kaçan net fırsat", GROUP_SHOTS, UNIT_COUNT),
    StatSpec("touches_opp_box", ("touches_opp_box",), "Rakip ceza sahasında topla buluşma", GROUP_GENERAL, UNIT_COUNT),
    StatSpec("xg_open_play", ("expected_goals_open_play",), "Akan oyunda xG", GROUP_SHOTS, UNIT_DECIMAL),
    StatSpec("xg_set_play", ("expected_goals_set_play",), "Duran topta xG", GROUP_SHOTS, UNIT_DECIMAL),
    StatSpec("xg_non_penalty", ("expected_goals_non_penalty",), "Penaltısız xG", GROUP_SHOTS, UNIT_DECIMAL),
    StatSpec("xgot", ("expected_goals_on_target",), "İsabetli şut xG'si (xGOT)", GROUP_SHOTS, UNIT_DECIMAL),
    StatSpec("own_half_passes", ("own_half_passes",), "Kendi yarı sahasında pas", GROUP_PASSES, UNIT_COUNT),
    StatSpec("opposition_half_passes", ("opposition_half_passes",), "Rakip yarı sahada pas", GROUP_PASSES, UNIT_COUNT),
    StatSpec("long_balls_accurate", ("long_balls_accurate",), "İsabetli uzun top", GROUP_PASSES, UNIT_COUNT),
    StatSpec("accurate_crosses", ("accurate_crosses",), "İsabetli orta", GROUP_PASSES, UNIT_COUNT),
    StatSpec("throws", ("player_throws",), "Taç atışı", GROUP_PASSES, UNIT_COUNT),
    StatSpec("interceptions", ("interceptions",), "Pas arası", GROUP_DEFENCE, UNIT_COUNT),
    StatSpec("shot_blocks", ("shot_blocks",), "Şut bloklama", GROUP_DEFENCE, UNIT_COUNT),
    StatSpec("clearances", ("clearances",), "Uzaklaştırma", GROUP_DEFENCE, UNIT_COUNT),
    StatSpec("duels_won", ("duel_won",), "Kazanılan ikili mücadele", GROUP_DEFENCE, UNIT_COUNT),
    StatSpec("ground_duels_won", ("ground_duels_won",), "Kazanılan yer mücadelesi", GROUP_DEFENCE, UNIT_COUNT),
    StatSpec("aerials_won", ("aerials_won",), "Kazanılan hava topu", GROUP_DEFENCE, UNIT_COUNT),
    StatSpec("dribbles_succeeded", ("dribbles_succeeded",), "Başarılı çalım", GROUP_GENERAL, UNIT_COUNT),
    StatSpec("distance_covered_m", ("physical_metrics_distance_covered",), "Kat edilen mesafe (m)", GROUP_GENERAL, UNIT_COUNT),
    StatSpec("running_distance_m", ("physical_metrics_running",), "Koşu mesafesi (m)", GROUP_GENERAL, UNIT_COUNT),
    StatSpec("walking_distance_m", ("physical_metrics_walking",), "Yürüme mesafesi (m)", GROUP_GENERAL, UNIT_COUNT),
    StatSpec("sprinting_distance_m", ("physical_metrics_sprinting",), "Sprint mesafesi (m)", GROUP_GENERAL, UNIT_COUNT),
    StatSpec("sprints", ("physical_metrics_number_of_sprints",), "Sprint sayısı", GROUP_GENERAL, UNIT_COUNT),
)

# FotMob group keys -> our group, for stats the table above does not know yet
# (they are passed through with the source title as label, see parsers).
SOURCE_GROUP_MAP = {
    "top_stats": GROUP_GENERAL,
    "shots": GROUP_SHOTS,
    "expected_goals": GROUP_SHOTS,
    "passes": GROUP_PASSES,
    "defence": GROUP_DEFENCE,
    "duels": GROUP_DEFENCE,
    "discipline": GROUP_DISCIPLINE,
    "physical_metrics": GROUP_GENERAL,
}

# --------------------------------------------------------------------------- shotmap

SHOT_SITUATION_TR = {
    "RegularPlay": "Akan oyun",
    "FromCorner": "Korner",
    "FastBreak": "Hızlı hücum",
    "SetPiece": "Duran top",
    "FreeKick": "Serbest vuruş",
    "ThrowInSetPiece": "Taç atışı",
    "Penalty": "Penaltı",
    "IndividualPlay": "Bireysel",
}
SHOT_BODY_PART_TR = {
    "RightFoot": "Sağ ayak",
    "LeftFoot": "Sol ayak",
    "Header": "Kafa",
    "OtherBodyParts": "Diğer",
}

# --------------------------------------------------------------------------- missing / errors

MISSING_REASONS_TR = {
    "not_started": "Maç henüz başlamadı.",
    "not_provided": "Kaynak (FotMob) bu bölümü göndermedi.",
    "lineup_not_announced": "Kadro henüz açıklanmadı.",
    "no_layout": "Kaynak saha dizilimi koordinatı göndermedi; diziliş ızgarası çıkarılamadı.",
    "shotmap_not_covered": "Kaynak şut haritası göndermedi (maç bu ayrıntı düzeyinde izlenmiyor olabilir).",
    "momentum_not_provided": "Kaynak baskı/momentum grafiği göndermedi.",
    "half_stats_not_provided": "Kaynak devre bazlı istatistik göndermedi.",
    "events_not_provided": "Kaynak olay akışı göndermedi.",
}

ERROR_MESSAGES_TR = {
    "unknown_match_id": "Maç kimliği tanınmadı (beklenen biçim: fotmob_<sayı>).",
    "match_not_found_at_source": "Maç FotMob'da bulunamadı.",
    "source_blocked": "FotMob isteği reddetti (403/doğrulama sayfası); istekler durduruldu.",
    "source_rate_limited": "FotMob istek sınırına ulaşıldı (429); kısa süre sonra tekrar deneyin.",
    "source_unavailable": "FotMob şu anda yanıt vermiyor.",
    "source_payload_invalid": "FotMob yanıtı beklenen biçimde değil.",
    "source_disabled": "Canlı maç merkezi veri kaynağı yapılandırmada kapalı.",
}


# FotMob event descriptions (English defaultText) -> Turkish; unknown texts are shown as sent.
EVENT_DETAIL_TR = {
    "header": "Kafa vuruşu",
    "penalty": "Penaltı",
    "left foot": "Sol ayak",
    "right foot": "Sağ ayak",
    "leftfoot": "Sol ayak",
    "rightfoot": "Sağ ayak",
    "free kick": "Serbest vuruş",
    "freekick": "Serbest vuruş",
    "volley": "Vole",
    "own goal": "Kendi kalesine",
    "foul": "Faul",
    "dissent": "İtiraz",
    "time wasting": "Zaman geçirme",
    "handball": "Elle oynama",
    "unsporting behaviour": "Sportmenliğe aykırı hareket",
    "unsporting behavior": "Sportmenliğe aykırı hareket",
    "simulation": "Simülasyon",
    "professional foul": "Kasıtlı faul",
    "violent conduct": "Şiddet içeren hareket",
    "serious foul play": "Ciddi faul",
    "delay of game": "Oyunu geciktirme",
    "delaying restart": "Oyunu geciktirme",
    "entering field": "İzinsiz sahaya girme",
    "leaving field": "İzinsiz sahayı terk",
    "off the ball": "Topsuz alanda faul",
    "excessive celebration": "Aşırı sevinç",
    "argument": "Tartışma",
    "pushing": "İtme",
    "tripping": "Çelme",
    "holding": "Tutma",
    "elbowing": "Dirsek",
    "spitting": "Tükürme",
    "abusive language": "Hakaret",
    "second yellow card": "İkinci sarı kart",
    # VAR decisions
    "goal": "Gol",
    "no goal": "Gol yok",
    "goal cancelled": "Gol iptal",
    "goal disallowed": "Gol iptal",
    "goal confirmed": "Gol geçerli",
    "goal awarded": "Gol verildi",
    "no penalty": "Penaltı yok",
    "penalty cancelled": "Penaltı iptal",
    "penalty awarded": "Penaltı verildi",
    "penalty confirmed": "Penaltı onaylandı",
    "red card": "Kırmızı kart",
    "no red card": "Kırmızı kart yok",
    "red card cancelled": "Kırmızı kart iptal",
    "card upgrade": "Kart yükseltildi",
    "offside": "Ofsayt",
    "mistaken identity": "Yanlış oyuncu",
}

# Canlı maç merkezi — veri kaynakları (14 Ekim 2026)

## Özet (Türkçe)

Sofascore ve Maçkolik tarzı bir canlı maç ekranı için skor, dakika, olay akışı, kadrolar ve yedekler,
reytingler, bütün takım istatistikleri (1. ve 2. yarı ayrı), şut haritası ve baskı grafiği gerekiyor.
Bunların hepsini **FotMob** tek istekte veriyor ve zaten kullandığımız kaynak. Diğer seçenekler:

| Kaynak | Durum | Karar |
|---|---|---|
| **FotMob** `/api/data/matchDetails` | Çalışıyor; canlı maçlarda olaylar, kadro, 38 istatistik × 3 dönem, şut haritası, baskı grafiği | **Ana kaynak** |
| Sofascore `api.sofascore.com` | Düz istek **403 Forbidden** (bot koruması); robots.txt de 403 | Kullanılmıyor — koruma aşılmaz |
| Maçkolik | robots.txt: `/api/` yasak, `anthropic-ai` ve diğer yapay zekâ ajanları tamamen yasak | Kullanılmıyor |
| API-Football, Sportmonks, Opta vb. | Lisanslı, API anahtarı ve ücret gerekir | İleride yedek kaynak olabilir |

Sofascore ve Maçkolik verilerini lisanslı sağlayıcılardan alıyor (Opta/Stats Perform, Sportradar vb.);
biz aynı içeriği FotMob üzerinden gösteriyoruz. Değerler kaynağın gönderdiği gibidir; göndermediği bölüm
"veri yok" ve nedeniyle gösterilir, asla 0 yazılmaz.

## Uç nokta

`GET /api/v1/matches/{match_id}/live-center` — `backend/app/api/v1/endpoints/live_center.py`,
servis `backend/app/services/live_center/` (parsers, schemas, constants, service).

- Önbellek: canlıyken 15 sn, maç öncesi 5 dk (başlama saatinde sona erer), maç bitince 1 saat.
- Aynı maça eş zamanlı gelen istekler tek FotMob isteğini paylaşır.
- FotMob istekleri `TeamNewsFotMobClient` üzerinden: süreç içi ≤ 1 istek/sn, ortak limiter
  (`scripts/data_collection/fotmob_rate.py`), 403/doğrulama sayfasında durma, 429'da bekleme.
- Hatalar 404/503 + neden kodu + Türkçe mesaj; asla uydurma veri yok.

## FotMob alan yolları (matchDetails)

| Bölüm | Yol |
|---|---|
| Durum, dakika | `header.status` (`started`, `finished`, `liveTime.short`, `halfs`, `reason.penalties`) |
| Skor | `header.teams[0/1].score` |
| Olaylar | `content.matchFacts.events.events[*]` (`type`: Goal, Card, Substitution, VAR, Half, MissedPenalty; `time`, `overloadTime`, `isHome`, `newScore`, `swap`, `cardReason`) |
| Kadrolar | `content.lineup.{homeTeam,awayTeam}` (`formation`, `starters`, `subs`, `coach`, `unavailable`), `content.lineup.lineupType` |
| İstatistikler | `content.stats.Periods.{All,FirstHalf,SecondHalf}.stats[*].stats[*]` (`key`, `stats`) |
| Şut haritası | `content.shotmap.shots[*]` (`min`, `minAdded`, `period`, `teamId`, `playerId`, `x`, `y`, `expectedGoals`, `expectedGoalsOnTarget`, `isOwnGoal`, `situation`, `shotType`) |
| Baskı grafiği | `content.matchFacts.momentum.main.data[*]` (yedek: `content.momentum.main.data`; `minute`, `value`) |
| Stat, hakem, seyirci | `content.matchFacts.infoBox` (`Stadium`, `Referee`, `Attendance`) |

Doğrulama: 13 Ekim Viking 3–3 Bayern (bitmiş) — 24 olay sırasıyla, 38 istatistik × 3 dönem, 33 şut,
92 baskı noktası, reytingli kadrolar ve dakikalı değişiklikler; 14 Ekim maçları canlı izlendi.
FotMob'un İngilizce açıklamaları ("Header", "Foul", "Dissent", VAR kararları) Türkçeye çevrilir
(`constants.EVENT_DETAIL_TR`); bilinmeyen metin olduğu gibi gösterilir.

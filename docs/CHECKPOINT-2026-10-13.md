# Kayıt noktası — 13 Ekim 2026, 23:15 TSİ

Eğitim, sahibin isteğiyle bilinçli olarak durduruldu (bilgisayar 00:00'da kapanacaktı; yarıda
kesilmesin diye). Yarın buradan devam edilir.

## Durum özeti

| Parça | Durum | Nerede |
|---|---|---|
| Geçmiş sonuçlar 2021-07 → 2025-06 (115 turnuva) + üretim DB birleşimi | ✅ bitti, denetlendi | `backend/data/history/all_results.db` (168.579 sonuç), README_history.md |
| Maç detayları 2022/23–2024/25 (TARGET13 + 2024/25 ek ligler) | ✅ bitti, denetlendi | `backend/data/training/fotmob_match_details_history.jsonl` (13.250 maç) |
| 2026/27 kadrolar + oyuncu profilleri (231 kulüp, 6.818 oyuncu) | ✅ bitti, denetlendi | `backend/data/players/` (README_players.md) |
| Kapanış oranları 2021/22–2025/26 (14 lig) | ✅ bitti, denetlendi | `backend/data/external/football_data_history.csv` (25.201 satır) |
| Canlı katman (şema, servisler, yenileme, API) | ✅ kod hazır, **üretime uygulanmadı** | `docs/live-layer.md` §7 |
| Eğitim hattı (stints, oyuncu etkisi, özellikler, model) | ✅ mevcut veriyle geliştirildi | `docs/training/player-impact-pipeline.md` |
| **Tam veri eğitimi** | ⏸ **durduruldu** — adım 1 ve 3a bitti | aşağıda |
| Bağımsız denetim | ⏸ başlamadı | |
| Canlı tahmine bağlama (flag arkasında) | ⏸ başlamadı (uygulama dosyalarına dokunulmadı) | |

Kontrol (23:15): `import app.main` çalışıyor, `backend/config/` değişmedi, eğitim scriptleri derleniyor,
106 hattı testi geçiyor. Durdurulan eğitim süreci (player_impact.py) sonlandırıldı; yarım dosya yok.

## Tam veri eğitimi — nerede kaldı

Bitti (yeniden kullanılabilir):
1. **Reyting λ, 4 sezon, xG'li:** `backend/data/training/walkforward_lambdas_full_2022_2026.csv`
   (+ `.meta.json`, karşılaştırma `walkforward_lambdas_full_check.json`; haftalık kesimler 2022-08-01 → 2026-10-12).
2. **Stints, iki detay dosyası birlikte:** `backend/data/training/stints_all.jsonl.gz`
   (+ `stints_all_report.json`, `stints_all_validation.csv`).

Kalan (sırayla):
3. `player_impact.py` iki dosyayla, haftalık/2 haftalık kesimler 2022-09 → 2026-10, ridge/prior yeniden ayarı
   (eğitim dönemi içinde zaman-ileri doğrulama). Eğitim ajanı script'i bu çalışma için düzenlemişti
   (`scripts/training/player_impact.py`, derleniyor, testler geçiyor) — çalıştırmadan önce diff'ine bakın.
4. Gol katmanını yalnızca eğitim döneminde yeniden fit et (değerlendirme için).
5. `build_match_features.py` tüm maçlar (expected_return ASLA kullanılmaz; awarded hariç).
6. `train_match_model.py`: eğitim 2022-08-01..2025-06-30, doğrulama 2025-07-01..2026-01-31, test 2026-02-01..2026-10-12;
   adaylar: üretim, ceza'lı Poisson + Avrupa'ya özel terimler, HGB; genişleyen pencere (2023/24, 2024/25, 2025/26).
7. Segmentler: lig/Avrupa, büyük maçlar (favori ≥ %70), olasılık bandına göre isabet, banko (≥ %85/%90) isabetleri.
8. Piyasa karşılaştırması (kapanış oranları), değer bahsi backtest'i.
9. Çıktılar: `match_model_candidate_full.json`, `player_impact_latest.json`, `full_training_report.json`,
   `docs/training/2026-10-13-full-training.md`.

Sonra: bağımsız sızıntı denetimi → karar → canlıya bağlama (flag, parite testi) → API yeniden başlatma.

İş akışı betiği (aynen yeniden kullanılabilir; yeni oturumda resume çalışmaz, ama istemler buradadır):
`C:\Users\Mito\.claude\projects\C--Users-Mito-Downloads-FootballIntelligence-main-FootballIntelligence-main-backend\70fce4b3-f78d-4101-9f4e-477912a2db21\workflows\scripts\tutarx-full-training-wf_932e0cb0-eee.js`
Yeniden başlatırken eğitim ajanına adım 1–2 çıktılarının hazır olduğunu ve yeniden kullanmasını söyleyin.

## Yarın sırası (~2–3 saat)

1. Tam veri eğitimini adım 3'ten bitir + bağımsız denetim.
2. Karar: yeni model üretimden ve Avrupa maçlarında daha iyiyse → `config/match_model.json` + oyuncu etkisi dosyası,
   canlı tahmine bağla (flag), API'yi yeniden başlat, tahminleri kontrol et.
3. Canlı katmanı aç (`docs/live-layer.md` §7): DB yedeği → `alembic stamp 20261013_pv_index_align` →
   `alembic upgrade head` → `scripts/live/load_player_data.py --allow-production-db` (DB ~87 → ~375 MB) →
   yenileme (in-API döngü YA DA 15 dk'lık zamanlanmış görev, ikisi birden değil) → API yeniden başlat.
4. Arayüz: maç sayfasına "Kadro & eksikler" (eksiklerin son 5 maç katkısı, ilk 11 gücü, form).
5. "Banko" bölümü (bkz. kullanıcıyla anlaşılan plan: model + piyasa ≥ %88–90, tipin geçmiş isabeti, kombine ihtimali).
6. Günlük bakım işleri: yeni maç detayları, oyuncu profilleri; üretim DB'deki 19 iptal maçın temizliği;
   `parse_match` lineup dışı oyuncuları atlıyor (README gap 11) — `--from-raw` ile düzeltilebilir.

## Bu akşamın testi

`docs/live-tests/2026-10-13/` — v5 (resmi kadrolar) dondu; maç sonu karşılaştırması
`results.md` dosyasına otomatik yazılır (`compare_results.py`). Toplayıcı hız sınırı maçlar bitince 6 istek/sn'ye
çıkarılır (`backend/data/raw_cache/.fotmob_rate/rate.txt`).

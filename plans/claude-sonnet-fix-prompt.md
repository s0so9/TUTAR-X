# FootballIntelligence Hata Düzeltme — Uygulama Promptu (Claude Sonnet 4.5'e verilecek)

## Bağlam

Bu proje bir futbol istihbarat ve tahmin platformudur. Temel ilke: **sayısal modeller tek gerçek kaynağıdır; hiçbir katman sayıyı icat etmez; eksik veri eksik olarak raporlanır.** Aşağıdaki düzeltmeler bu ilkeye aykırı davranışları gidermek içindir.

Kurallar:
- Kod kimliği İngilizce, arayüz dili Türkçe.
- Backend = Python + FastAPI + Pydantic + SQLAlchemy.
- Değişiklikleri küçük, doğrulanabilir adımlar halinde yap; her adımdan sonra ilgili testi çalıştır.
- Mock/development verisini asla gerçek veri gibi sunma.

---

## Düzeltme 1 — Poisson'daki çift lambda formülü (CRITICAL)

**Dosya:** `backend/app/prediction/poisson.py`

Mevcut durumda aynı eşleşme için iki farklı lambda formülü var:
- `estimate_lambda_from_features` (satır ~302): `λ = attack × venue × opponent_defense_strength`
- `predict()` (satır ~343): `λ = goals_scored_avg × (opponent_goals_conceded_avg / 1.0)`

Bu, aynı veri için farklı sonuç üretir ve "tek gerçek kaynak" ilkesini bozar.

**Yapılması gereken:**
- Tek, kanonik bir `estimate_lambda(...)` metodu tanımla; iki farklı formül kalmasın.
- `predict()` metodu lambda hesaplaması için bu kanonik yöntemi çağırsın; inline `× (x / 1.0)` gibi formüller kaldırılsın.
- Tüm çağrı yolları (`service.py` `generate_prediction`, orchestrator, market derivation) aynı kanonik formülü kullansın.
- Formülde "savunma güçlü = gol yeme oranı düşük = rakibe beklenebilir gol artar" mantığının doğru yönde uygulandığı domain'e göre doğrulanmalı. Şu anki `× opponent_defense_strength` çarpanının yönü yanlış olabilir (savunma ne kadar güçlü/high ise lambda o kadar büyüyor); gerekirse çarpanı ters çevir veya oran tabanlı yap.
- Doğrulama: `backend/tests` altında Poisson lambda tutarlılığı testi; aynı girdi için her yolun aynı lambda verdiği test edilmeli.

---

## Düzeltme 2 — Score distribution yeniden ölçeklendirme matematiği (HIGH)

**Dosya:** `backend/app/prediction/model_orchestrator.py` (satır ~534-656, `calibrate_prediction` ve `_rescale_score_distribution`)

Sorunlar:
1. Kategori ölçek faktörü `calibrated/original` olarak tanımlanıyor; `original < 1e-6` durumunda faktör 1.0'a sabitleniyor (satır ~643-645). Bu, düşük olasılıklı kategorilerdeki skorların hiç ölçeklenmemesine ve kategori toplamlarının hedefe ulaşmamasına yol açar.
2. Kalibrasyon sonrası `home_score_mean`/`away_score_mean` değiştirilmiyor; P(home) değişirken lambda sabit kalıyor → xG ile 1X2 tutarsız.
3. Yöntem yalnızca orijinal 1X2 prob'larının kategori toplamlarına eşit olması durumunda geçerli; bu varsayım kontrol edilmiyor.

**Yapılması gereken:**
- `_rescale_score_distribution` yerine **yeniden normalizasyon + kategori hedefi** yaklaşımı: her kategori için skorları, kategorinin toplamının hedefe (calibrated prob'a) oranla ölçekle. Kategori toplamı 0'a yakınsa o kategorinin skorları için güvenli bir dağılım (örn. en olası skorlara eşit ağırlık) belirle; 1.0'a sabitleme yapma.
- Ölçekleme sonrası dağılımın toplamı 1.0'a normalize edilsin.
- Kategori hedeflerine ulaşılması doğrulanmalı: örn. "toplam home skoru ≈ calibrated_home_prob" invariant testi yaz.
- Değişikliği `backend/tests` altında ilgili calibrasyon/ensemble testinde doğrula; yoksa yeni test ekle.

---

## Düzeltme 3 — Dev-baseline fallback'ini production'a kapat (HIGH)

**Dosya:** `backend/app/prediction/service.py`
- `generate_prediction` (satır ~267-281)
- `generate_prediction_markets` (satır ~358-368)

Mevcut davranış: eksik özellikler 1.0'a düşürülüyor; tetikleyici `hasattr(provider, 'is_development_data')` + `provider.is_development_data()`. Bu, yanlış konfigure edilmiş bir provider'ın production'da eksik veriyi 1.0'la doldurmasına izin verebilir → "insufficient_data" durumu gizlenir.

**Yapılması gereken:**
- Baseline fallback'ini yalnızca **açık ve explicit dev-flag**'i üzerinden etkinleştir (örn. `settings.is_development` env-tabanlı). `hasattr(provider, ...)` soyut kontrolünü kaldır veya yalnızca ikincil guard olarak tut.
- Production modunda eksik özellik varsa `generate_prediction` → `None`, `generate_prediction_markets` → boş liste dönmeli; dev-bypass production'a sızamaz şekilde güvencele.
- 1.0 = "nötr/lig ortalaması" varsayımını yalnızca gerçekten dev modunda koru; gerekçeyi inline yorumda belirt.
- Test: provider'ın `is_development_data` False döndürdüğü production senaryosunda eksik özellik + `generate_prediction` → `None` testini ekle.

---

## Düzeltme 4 — Confidence fallback'ini "unknown" olarak raporla (MEDIUM)

**Dosya:** `backend/app/prediction/model_orchestrator.py` (satır ~707-711, `assess_confidence`)

Mevcut: `data_quality_score = 0.5` sabit fallback. Bu, veri kalitesi raporunun yokluğunu "orta kalite" olarak gizler; PROJECT_SPEC'e (eksik veri eksik olarak raporlanmalı) aykırı.

**Yapılması gereken:**
- Rapor yoksa `data_quality_score`'u `None` olarak `ConfidenceEngine`'e geçir; engine'de bu durumun "unknown/insufficient" etiketine düşmesini sağla; 0.5'a sabitleme yapma.
- Üretilen `ConfidenceAssessment` içinde bu bileşenin "unknown" olduğu açıkça belirtilsin.
- Test: `data_quality_report` yokken üretilen confidence'ın "insufficient_data" benzeri bir etiket aldığı doğrulanmalı.

---

## Düzeltme 5 — Optimizasyon ensemble yükleme hata sessizliğine kapat (MEDIUM)

**Dosya:** `backend/app/prediction/service.py` (satır ~176-183)

Mevcut: `create_optimized_ensemble()` başarısız olursa yalnızca `logging.warning` atılıyor ve default ensemble'a düşülüyor; production'da model seçimi hatası görünür kalmıyor.

**Yapılması gereken:**
- Bu durumda `pipeline_metadata`/`calibration_metadata` içine uyarı alanı ekle (örn. `"ensemble_fallback": "default"`, `"ensemble_fallback_reason": str(e)`).
- Log seviyesini context ile artır; AI-Analyst'e giden `AnalysisContext`'te bu fallback'in yaşandığı temsil edilebilmeli.
- Default ensemble'a düşüldüğünde prediction'daki confidence düşürülmeli veya `model_agreement` işaretlenmeli.

---

## Düzeltme 6 — Market selector aday diagnostic boşluğu (MEDIUM)

**Dosya:** `backend/app/prediction/market_selector.py` (satır ~304)

Mevcut: `all_candidates=None  # TODO`. Aday marketlerin debug edilememesi "neden bu market seçildi?" sorusunu yanıtsız bırakıyor.

**Yapılması gereken:**
- `all_candidates` listesini (filtrelenmemiş adaylar + elenen adaylar + elenme nedenleri) doldur ve sonucuyla birlikte dönecek yapıya ekle.
- Her aday için en az: `market_type, line, probability, edge, risk_level, selected, rejection_reason`.
- Bu yapı AI-Analyst/yorum katmanında "market seçimi neden oldu" açıklamasında kullanılabilmeli.

---

## Düzeltme 7 — Ad-hoc `Config` class'ını tiplendir (LOW)

**Dosya:** `backend/app/prediction/service.py` (satır ~127-129)

Mevcut: `type('Config', (), {'min_sample_size': min_sample_size})()` dynamic class.

**Yapılması gereken:**
- `dataclass` veya Pydantic model (`PredictionServiceConfig`) kullan; alanlar: `min_matches`, `min_sample_size`, `is_development` (Düzeltme 3 ile bağlantılı).
- `self.config` bu tip'in instance'ı olsun; ilgili tüm kullanım noktaları senkron.

---

## Düzeltme 8 — BTTS olasılığı üretimi eksik (MEDIUM)

**Dosya:** `backend/app/prediction/service.py` (satır ~1492)

Mevcut: `"btts_probability": None  # TODO: derive from score distribution`.

**Yapılması gereken:**
- `calibrated_prediction.score_distribution` üzerinden BTTS hesapla: `sum(p for (h,a),p in dist.items() if h>=1 and a>=1)`.
- Bu değer versioned prediction'a yazılsın; yalnızca dağılım yoksa `None` bırakılsın.
- Test: bilinen Poisson λ'leri için BTTS olasılığı ile bağımsız hesap eşleşmeli.

---

## Düzeltme 9 — Kök dizindeki dağınık script/test karışıklığı (PROJELİK)

**Durum:** Kök dizinde onlarca `*.py` (debug, analyze, find, check, test, diagnose) ve `.md` rapor; backend'te hem kök hem `tests/` altında test. Pytest keşfini karmaşıklaştırıyor, "hangi test yetkili?" belirsiz.

**Yapılması gereken:**
- Kök dizindeki geçici script'leri `scripts/` altına taşı; gerçekten çalışan testleri `backend/tests/` altına taşı.
- `requirements.txt`/pytest config'te test keşfi yolunu netleştir; kök dizinden rastgele test çalıştırılmasını engelle.
- Her taşınan test için son çalıştırma sonucunu `docs/PROGRESS.md`'ye ekle.

---

## Doğrulama kontrol listesi

Her düzeltme sonrası:
- İlgili `backend/tests` altındaki testleri çalıştır (poisson, ensemble, calibration, market_selector, service).
- Yeni invariant testlerini ekle:
  - aynı girdi → aynı lambda (Poisson kanonik yol)
  - kategori toplam ≈ calibrated 1X2 prob (score distribution rescale)
  - production + eksik veri → `None` (dev-baseline sızması yok)
  - eksik veri kalitesi → "unknown/insufficient" confidence etiketi
- Type-check / import doğrulaması (`pyright` veya `py_compile`).
- Mock/development çıktılarının `is_development` olarak etiketlendiği doğrulansın.
- Her adım sonunda `docs/PROGRESS.md`'ye kayıt yap.

---

## Sıralama (öncelik)

1. Düzeltme 1 (Poisson lambda birleştirme) — diğerlerinin kök nedeni.
2. Düzeltme 2 (score distribution rescale invariant).
3. Düzeltme 3 (dev-baseline production sızması).
4. Düzeltme 4 (confidence unknown raporu).
5. Düzeltme 5 → 8 (metadata/observability).
6. Düzeltme 9 (proje hijyeni, bağımsız olarak yapılabilir).

**Genel ilke:** Her adımda "sayısal çıktının her yoldan aynı ve açıkça türetilmiş" olduğu testlerle kanıtlanmalı; hiçbir değişiklik üretimde veri eksikliği maskelemesin.

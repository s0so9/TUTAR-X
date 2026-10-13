# FootballIntelligence — Sonnet 4.5 Master Düzeltme Promptu (v2)

## Talimat

Sen bir kıdemli Python + TypeScript yazılım mühendisisin. Aşağıdaki düzeltmeleri `c:/FootballIntelligence` deposunda **doğrudan uygula**. Her düzeltme için: mevcut kodu oku → değiştir → ilgili testi çalıştır → `docs/PROGRESS.md` sonuna bir madde ekle.

**Kurallar:**
- Kod kimliği İngilizce, UI dili Türkçe.
- Backend: Python + FastAPI + Pydantic + SQLAlchemy. Frontend: React + TypeScript + Vite.
- Eksik veriyi asla rastgele/sabit bir sayıyla gizleme; eksik olarak raporla.
- Sayısal motor tek gerçek kaynağıdır; hiçbir katman sayıyı icat etmez.
- Mock/development veriyi asla gerçek veri gibi sunma.
- Her adımdan sonra ilgili testi çalıştır; "test edildi" demek için test çıktısını görmüş olmalısın.
- Her adımdan sonra `docs/PROGRESS.md` sonuna madde ekle.
- Aşağıda DÜZELTİLMİŞ olarak işaretli kalemleri **yapma**.
- Satır numaraları yaklaşık olabilir; fonksiyon adı ve kod örüntüsüne göre eşleştir.

---

## BÖLÜM A — ZATEN DÜZELTİLMİŞ (TEKRAR YAPMA)

Bu kalemler mevcut GitHub durumuna göre doğrulanmıştır. Dokunma:

1. **Poisson çift lambda** — `poisson.py` içinde tek kanonik `estimate_lambda` artık var.
2. **Score distribution rescale invariant** — `CalibrationIntegration._rescale_score_distribution` artık kategori hedeflerine göre ölçekliyor, normalize ediyor.
3. **Ensemble `StaticWeights` default 1.0 → 0.0** — `ensemble_engine.py`'de tanımsız model artık 0.0 ağırlık alıyor.
4. **Prediction version DB persistence + unique constraint** — `prediction_version.py`, `prediction_persistence.py`, `prediction_repository.py` DB-backed; IntegrityError handled.
5. **Settlement kanonik market ID'leri** — `settlement.py` BTTS'yi metin üzerinden değil market kimliği üzerinden sonuçlandırıyor.
6. **Odds endpoint alan uyumu** — `odds.py` `AverageMarketOdds`'dan okuduğu alanlar düzeltilmiş (join üzerinden takım adı/ziyaret).
7. **Statistics double-count / xGA denominator** — `attack_defence.py`'deki xGA/hit-shot hesapları artık doğru örnek sayısına bölünüyor.
8. **Frontend odds hook'ları merkezi client + refetch** — `useOdds.ts` artık `client.ts`'deki `request`'i kullanıyor, refetch gerçek fetch başlatıyor.
9. **shots mapping fix** — `client.ts` `shots_off_target` → `shotsOutsideBox` yanlış eşlemesi düzeltilmiş.
10. **Calibration random-data block** — `train_calibration.py`'deki `random.gauss` üretim yolundan çıkarılmış, demo olarak etiketlenmiş.
11. **Odds updater flush before averages** — `odds_updater_service.py` artık `_calculate_and_store_averages` öncesi `db.flush()` çağırıyor.
12. **useLazyPrediction StrictMode** — hook artık abort'ta loading state'i temizliyor, remount'ta yeniden fetch başlatıyor.

---

## BÖLÜM B — DÜZELTİLECEK KALEMLER (AŞAĞIDAKİ SIRA İLE)

### B-1. P1 — `walk_forward.py` API uyuşmazlıkları (CRITICAL)

**Dosya:** `backend/app/prediction/walk_forward.py`

**Sorun 1a — Yanlış import (satır 424-425):**
```python
from app.prediction.ensemble_engine import StaticWeighting
ensemble_engine = EnsembleEngine(strategy=StaticWeighting())
```
→ `StaticWeighting` diye bir sınıf yok. Doğrusu `StaticWeights` ve bir `weights` dict istiyor.

**Değişiklik:**
```python
from app.prediction.ensemble_engine import StaticWeights, ReliabilityWeights
from app.prediction.ensemble_engine import EnsembleEngine
# Reliability-based, no need for per-model weight config
ensemble_engine = EnsembleEngine(strategy=ReliabilityWeights())
```
(Eğer sabit ağırlık istenirse: `StaticWeights(weights={"poisson_v1": 0.25, "dixon_coles_v1": 0.30, "neg_binomial_v1": 0.25, "form_adjusted_v1": 0.20})`)

**Sorun 1b — `combine()` yanlış veri tipi alıyor (satır 427):**
`orchestration_result.successful_predictions` → `List[ModelOutput]`.
`EnsembleEngine.combine()` → `List[ModelPrediction]` bekliyor.
`ModelOutput` içinde `prediction: Optional[ModelPrediction]` alanı var.

**Değişiklik:**
```python
predictions = [
    out.prediction
    for out in orchestration_result.successful_predictions
    if out.prediction is not None
]
if len(predictions) < 2:
    return None
ensemble_pred = ensemble_engine.combine(predictions=predictions, context={})
```

**Sorun 1c — `market_engine.derive()` fazla argüman (satır 468-472):**
Mevcut:
```python
market_probs = market_engine.derive(
    score_distribution=ensemble_pred.score_distribution,
    home_score_mean=ensemble_pred.home_score_mean,
    away_score_mean=ensemble_pred.away_score_mean
)
```
Gerçek imza `MarketDerivationEngine.derive(score_distribution: Dict[Tuple[int,int], float])` → **sadece tek argüman**.

**Değişiklik:**
```python
market_probs = market_engine.derive(
    score_distribution=ensemble_pred.score_distribution
)
```

**Sorun 1d — `data_quality_score` 0.5 fabrications (satır 441):**
```python
data_quality_score = snapshot.data_quality_report.overall_score if snapshot.data_quality_report else 0.5
```
→ `0.5` uydurma. `None` olarak bırakılmalı; ConfidenceEngine zaten `None` → insufficient olarak işliyor.

**Değişiklik:**
```python
data_quality_score = snapshot.data_quality_report.overall_score if snapshot.data_quality_report else None
```

**Sorun 1e — `_build_snapshot` `DataQualityReport` yanlış alanlarla (satır 569-574):**
Mevcut:
```python
data_quality_report=DataQualityReport(
    overall_score=0.5,
    missing_features=[],
    low_confidence_features=[],
    data_freshness_score=0.5
)
```
Gerçek `DataQualityReport` modeli (Pydantic): `overall_score: float`, `checks: List[DataQualityCheck]`, `passed: int`, `failed: int`, `warnings: List[str]`. `missing_features`, `low_confidence_features`, `data_freshness_score` diye alanlar **yok**.

**Değişiklik:**
```python
data_quality_report=DataQualityReport(
    overall_score=0.5,  # walk-forward simülasyon: orta kalite
    checks=[],
    passed=0,
    failed=0,
    warnings=["walk_forward_simulation: kalite raporu simüle edilmiş"]
)
```

**Sorun 1f — Sessiz `return None` (satır 539-541):**
```python
except Exception as e:
    # Log error but continue evaluation
    return None
```
→ Hatalı maç, veri yetersizliği, yazılım hatası **ayrı sayılmalı**. Sessiz `None` her şeyi yutuyor.

**Değişiklik:**
```python
except Exception as e:
    import logging
    logging.getLogger(__name__).error(
        f"Walk-forward evaluation failed for match {test_match.id}: {e}",
        exc_info=True,
    )
    # Yazılım hatası: kaydı None döndürme; hata sayacını artıran özel bir durum üret
    return PipelinePredictionRecord(
        match_id=test_match.id,
        predicted_at=datetime.utcnow(),
        actual_outcome=None,
        actual_home_score=None,
        actual_away_score=None,
        feature_config=config.name,
        models_available=0,
        models_successful=0,
        model_outputs={},
        ensemble_home_win=None,
        ensemble_draw=None,
        ensemble_away_win=None,
        model_agreement=0.0,
        calibrated_home_win=None,
        calibrated_draw=None,
        calibrated_away_win=None,
        calibration_status="error",
        confidence_score=0.0,
        confidence_label="ERROR",
        uncertainty_score=0.0,
        uncertainty_label="unknown",
        model_disagreement=0.0,
        selected_market=None,
        selection_probability=None,
        selection_confidence=None,
        is_pass=True,
        pass_reason=f"evaluation_error: {str(e)[:200]}",
        features_available={},
        data_quality_score=None,
        shot_markets_evaluated=False,
        shot_market_predictions={},
    )
```
Not: `PipelinePredictionRecord` dataclass'ında `None` kabul etmeyen alanlar varsa, bu kayıt senaryosunu desteklemek için ilgili alanlara `Optional` tipini ekle. `_aggregate_metrics` içinde `is_pass=True` ve `pass_reason` başlangıcı `"evaluation_error"` olan kayıtları `eval_records` dışına al ama `n_predictions` sayımına dahil et.

---

### B-2. P1 — `walk_forward.py` `_fit_calibration` fit edilmiyor (HIGH)

**Dosya:** `backend/app/prediction/walk_forward.py`
**Satır 577-603**

Mevcut:
```python
def _fit_calibration(self, train_matches, config) -> CalibrationEngine:
    calibration_engine = CalibrationEngine()
    # For now, return unfitted engine
    return calibration_engine
```

**Değişiklik:** Gerçek `CalibrationData` (predicted_probs, actual_outcomes, timestamps) toplu fit et:
```python
def _fit_calibration(self, train_matches, config) -> CalibrationEngine:
    """Fit calibration using only training data (temporal cutoff)."""
    calibration_engine = CalibrationEngine(method="isotonic")

    # Walk-forward: historical predictions needed.
    # If no stored predictions exist, build a minimal out-of-sample approximation
    # using the same pipeline on a holdout subset, recording actuals.
    # For this implementation, use the ensemble home_win probability from each
    # train match as the predicted probability and the actual home_win outcome
    # as the binary outcome (0.0/1.0). This is a documented simplification:
    # real production calibration should use stored prediction versions.

    predicted_probs = []
    actual_outcomes = []
    timestamps = []

    for m in train_matches:
        if m.home_score is None or m.away_score is None:
            continue
        outcome = 1.0 if m.home_score > m.away_score else 0.0
        # Use a neutral 0.5 as placeholder for predicted home_win probability
        # when no stored prediction exists; this is documented as a limitation.
        predicted_probs.append(0.5)
        actual_outcomes.append(outcome)
        timestamps.append(m.scheduled_at)

    if len(predicted_probs) >= CalibrationEngine.MIN_SAMPLES:
        from app.prediction.calibration_engine import CalibrationData
        cutoff = max(timestamps) if timestamps else None
        try:
            calibration_engine.fit(
                CalibrationData(
                    predicted_probs=predicted_probs,
                    actual_outcomes=actual_outcomes,
                    timestamps=timestamps,
                ),
                cutoff_date=cutoff,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Walk-forward calibration fit failed, using unfitted engine: {e}"
            )

    return calibration_engine
```
Not: `CalibrationEngine.MIN_SAMPLES` sabitini kullan; `calibration_engine.py`'de tanımlı (30). Eğer tanımlı değilse 30 kullan.

**Gerçek iyileştirme (sonraki adım):** `PredictionVersionRepository`'den `get_settled_picks_by_market` ile tarih kesimli gerçek tahmin–sonuç çiftlerini getir, bu listeden `predicted_probs`/`actual_outcomes` oluştur. Yalnızca bu yol çalışmıyorsa 0.5 placeholder'a düş. Bu placeholder'ı metadata'da açıkça "walk_forward_calibration_source=placeholder" olarak işaretle.

---

### B-3. P1 — `service.py` confidence fallback 0.5 uydurma (HIGH)

**Dosya:** `backend/app/prediction/service.py`
**Satır 1298-1318**

Mevcut:
```python
except Exception as e:
    ...
    confidence_assessment = ConfidenceAssessment(
        overall_confidence=0.5,
        confidence_label="MEDIUM",
        components=ConfidenceComponents(
            model_agreement=0.5,
            data_quality=0.5,
            sample_size=0.5,
            calibration_reliability=0.5,
            lineup_certainty=0.5,
            prediction_stability=0.5
        ),
        ...
    )
```

**Değişiklik:** Hesaplanamayan güven "orta" değil **insufficient_data** olarak raporlanmalı. `ConfidenceComponents` alanları `float` zorunlu; `ConfidenceAssessment` içinde alan genişletme gerekmez, etiketi değiştirmek yeterli.
```python
except Exception as e:
    import logging
    logging.error(f"Confidence assessment failed: {e}", exc_info=True)
    stage_timings["5_confidence_FAILED"] = (time.time() - step_start) * 1000
    profiler.end_stage(success=False, error=str(e), duration_ms=stage_timings["5_confidence_FAILED"])
    confidence_assessment = ConfidenceAssessment(
        overall_confidence=0.0,
        confidence_label="INSUFFICIENT_DATA",
        components=ConfidenceComponents(
            model_agreement=0.0,
            data_quality=0.0,
            sample_size=0.0,
            calibration_reliability=0.0,
            lineup_certainty=0.0,
            prediction_stability=0.0,
        ),
        weights=ConfidenceWeights(),
        component_breakdown={},
    )
```
Not: `INSUFFICIENT_DATA` etiketi `confidence_label` serbest metin alanına yazılabilir. UI tarafında bu etiketi "Yetersiz veri" olarak göster.

---

### B-4. P2 — `service.py` `data_quality_score` 0.5 fallback (satır 1576)

Mevcut:
```python
data_quality_score=snapshot.data_quality_report.overall_score if snapshot.data_quality_report else 0.5
```

**Değişiklik:**
```python
data_quality_score=snapshot.data_quality_report.overall_score if snapshot.data_quality_report else None
```
`PredictionVersion` modelinde `data_quality_score` alanı `Optional[float]` ise sorunsuz; değilse `Optional` yap.

---

### B-5. P2 — `service.py` dev-provider `hasattr` otomatik algılama (satır 174-177)

Mevcut:
```python
is_dev_provider = (
    hasattr(provider, 'is_development_data')
    and provider.is_development_data()
)
```

**Değişiklik:** Ad-hoc `hasattr` soyut kontrolünü kaldır; config üzerinden explicit dev flag kullan:
```python
# Development/production modu artık config'ten gelir.
# hasattr otomatik algılama kaldırıldı.
if config is None:
    from app.config import settings
    is_dev = settings.is_development  # bool, env: FI_IS_DEVELOPMENT=1
    if is_dev:
        self.config = PredictionServiceConfig.for_development(
            min_matches=min_matches,
            min_sample_size=min_sample_size
        )
    else:
        self.config = PredictionServiceConfig.for_production(
            min_matches=min_matches,
            min_sample_size=min_sample_size
        )
```
`backend/app/config.py` içinde `Settings` modeline şunu ekle:
```python
is_development: bool = False  # env: FI_IS_DEVELOPMENT
```
Not: Mevcut `DevelopmentProvider` sınıfı `is_development_data()` method'u döndürüyorsa, o sınıfın `__init__`'inde bir flag'i de config'e bağla; `service.py`'de `hasattr` kullanımını tamamen kaldır.

---

### B-6. P2 — `service.py` `MarketAnalyser(is_development_data=True)` sabit True (satır 203)

Mevcut:
```python
self.market_analyser = market_analyser or MarketAnalyser(
    value_threshold=0.03,
    is_development_data=True,
)
```

**Değişiklik:**
```python
self.market_analyser = market_analyser or MarketAnalyser(
    value_threshold=0.03,
    is_development_data=self.config.is_development,
)
```
`PredictionServiceConfig` dataclass'ında `is_development: bool` alanı yoksa ekle.

---

### B-7. P2 — `monte_carlo.py` global `random.seed` (satır 214-215)

Mevcut:
```python
if self.seed is not None:
    random.seed(self.seed)
```

**Değişiklik:** Yerel RNG instance kullan (`logistic_regression.py`'deki `random.Random(self.seed)` örüntüsü):
```python
if self.seed is not None:
    rng = random.Random(self.seed)
else:
    rng = random.Random()
# _run_simulation ve _poisson_sample çağrıları bu rng'yi kullansın
```
`_run_simulation` ve `_poisson_sample`'daki `random.poisson` / `random.random` çağrılarını `rng.poisson` / `rng.random` yap.

---

### B-8. P1 — `odds.py` `manual_odds_update` yetkilendirme yok (satır 269-315)

**Dosya:** `backend/app/routers/odds.py`

**Değişiklik:** Admin yetkisi + hız sınırı + eşzamanlı koruma + ham exception'ı gizle.
FastAPI dependency olarak `require_admin` ekleyip bu endpoint'e uygula:
```python
# backend/app/api/dependencies.py (yeni)
async def require_admin(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = auth[7:]
    if not verify_admin_token(token):  # JWT/secret kontrolü
        raise HTTPException(status_code=403, detail="Insufficient permissions")

# backend/app/routers/odds.py
@router.post("/manual-update")
async def manual_odds_update(
    request: Request,
    db: Session = Depends(get_db),
    _admin: None = Depends(require_admin),
):
    # Eşzamanlı koruma: basit lock (app-wide global veya Redis; burada basit global)
    ...
    try:
        ...
    except Exception:
        logger.exception("manual_odds_update failed")
        raise HTTPException(status_code=500, detail="Odds update failed; see server logs")
```
`verify_admin_token` fonksiyonu `app/auth/` altına eklenmeli; admin kimliği ortam değişkeni `FI_ADMIN_TOKEN`'dan gelir. İstemciye asla ham traceback dönülmez.

**Küçük not:** Kodda satır 283'teki `# TODO` yorumunu da kaldır; çözüm tamamlandığında TODO'yu sil.

---

### B-9. P2 — `dependencies.py` `ProviderCache` per-request (satır 52)

**Dosya:** `backend/app/api/dependencies.py`

Mevcut:
```python
def get_data_provider():
    cache = ProviderCache()
    ...
```

**Değişiklik:** Uygulama yaşam döngüsüne bağlı paylaşılan cache. `main.py`'de `lifespan` içinde tek global `ProviderCache` örneği oluştur, `Depends` ile sun:
```python
# backend/app/api/dependencies.py
_provider_cache: ProviderCache = None  # module-level

def init_provider_cache() -> ProviderCache:
    global _provider_cache
    if _provider_cache is None:
        _provider_cache = ProviderCache()
    return _provider_cache

def get_data_provider() -> Generator[FootballDataProvider, None, None]:
    cache = init_provider_cache()
    ...
```
`backend/app/main.py` `lifespan`'de `init_provider_cache()` çağrısını yap.

Sayfalama (limit/offset) veritabanına inmek için: `matches.py` list endpoint'inde provider'a `limit`/`offset` gönder; Python içi dilimleme kaldırılsın. Bu değişiklik list endpoint'inin provider sorgusunu desteklemesi gerektirir; desteklemeyen provider'lar için mevcut davranış korunsun ama log'a warning atılsın.

---

### B-10. P2 — `matches.py` async endpoint senkron bloklamada (satır ~649-693)

**Dosya:** `backend/app/api/v1/endpoints/matches.py`

**Değişiklik:** `generate_full_prediction` senkron; async endpoint içinde doğrudan çağırmak event loop'ı blokluyor. `run_in_executor` ile dışala:
```python
import asyncio
loop = asyncio.get_running_loop()
result = await loop.run_in_executor(
    None,
    lambda: prediction_service.generate_full_prediction(match, stage, odds_data, correlation_id),
)
```
Benzer şekilde `service.py`'de `ThreadPoolExecutor + future.result(timeout)` örüntüsünü (satır 654-663, 784-824, 895-917) gerçek deadline/iptal davranışına sahip bir örüntüye çevir; `shutdown(wait=False)` ile sınırsız arka plan işi bırakma.

---

### B-11. P2 — `train_calibration.py` `NotImplementedError` (HIGH)

**Dosya:** `backend/scripts/train_calibration.py`

İnceleme bulgusu 5: gerçek pipeline'ın kronolojik out-of-sample tahmin–sonuç çiftleriyle eğitilmeli. `NotImplementedError`'ı kaldırıp gerçek eğitim yolunu aç:
```python
def train_calibration_models(real_pairs, cutoff):
    """Fit production calibrator on real out-of-sample pairs."""
    if len(real_pairs) < MIN_TRAIN_SAMPLES:
        raise InsufficientDataError(
            f"Need >= {MIN_TRAIN_SAMPLES} settled pairs, got {len(real_pairs)}"
        )
    probs = [p.predicted_home_win for p in real_pairs]
    outcomes = [float(p.actual_outcome == 'home_win') for p in real_pairs]
    timestamps = [p.predicted_at for p in real_pairs]
    engine = CalibrationEngine(method="isotonic")
    engine.fit(
        CalibrationData(predicted_probs=probs, actual_outcomes=outcomes, timestamps=timestamps),
        cutoff_date=cutoff,
    )
    return engine
```
`real_pairs`, `PredictionVersionRepository`'den `get_settled_picks_by_market` ile çekilmeli; tarih kesimi `cutoff`'tan önceki kayıtlar alınmalı. Eğitim metadata'sı (örnek sayısı, kesim tarihi, model sürümü, Brier/log-loss) artifact'a yazılmalı.

**Küçük not:** Kök dizindeki 40+ geçici script/test dosyasını `scripts/` veya `backend/tests/` altına taşı; kök dizini temizle.

---

### B-12. P2 — `service.py` `odds_data` gerçekten pipeline'a bağlanmalı (HIGH)

**Dosya:** `backend/app/api/v1/endpoints/matches.py` (~satır 661)

Mevcut:
```python
odds_data=None
```

**Değişiklik:** Maç ve piyasa kimlikleriyle zaman damgalı gerçek `AverageMarketOdds` kayıtlarını oku, `generate_full_prediction`'a `odds_data=` olarak aktar:
```python
odds_data = odds_service.load_odds_for_match(
    match_id=match.id,
    as_of=prediction_time,  # tahmin anından önceki en taze oran
)
result = prediction_service.generate_full_prediction(
    match, stage, odds_data=odds_data, correlation_id=correlation_id,
)
```
Yoksa `odds_data=None` ve pipeline'ın `NO_ODDS` davranışı çalışmalı.

---

## BÖLÜM C — ÖNCELİK SIRASI

1. **B-1** — `walk_forward.py` API uyuşmazlıkları (pipeline bozuk, diğer metrikler sahte)
2. **B-2** — `walk_forward.py` `_fit_calibration`
3. **B-11** — `train_calibration.py` gerçek eğitim yolu (kalibrasyon zinciri)
4. **B-3** — `service.py` confidence fallback
5. **B-4** — `service.py` data_quality fallback
6. **B-12** — `matches.py` odds_data gerçekten pipeline'a bağlanmalı
7. **B-5, B-6** — dev provider config'ten (güvenlik/teşhis karışması için)
8. **B-7** — Monte Carlo yerel RNG
9. **B-8** — `odds.py` admin yetkilendirme
10. **B-9** — `dependencies.py` uygulama yaşam döngüsüne cache
11. **B-10** — `matches.py` async bloklamayı kaldır

## BÖLÜM D — DOĞRULAMA PROTOKOLÜ

Her B kalemi sonrası:
1. `cd backend && python -m pytest tests/test_*.py -x -q` → en azından ilgili modül testleri geçiyor.
2. `cd frontend && npm run typecheck && npm run build` → TypeScript hatası yok.
3. Yeni invariant testleri:
   - `walk_forward.py`: küçük deterministik fixture'da ≥1 `PipelinePredictionRecord` üret; `evaluation_error` geçen kayıtlar `pass_reason`'de açıkça işaretli; `_aggregate_metrics` bu kayıtları `n_predictions`'a ekler ama `eval_records` dışına alır.
   - `train_calibration.py`: ≥ `MIN_TRAIN_SAMPLES` gerçek pair → `CalibrationEngine.status == FITTED`; < MIN → `InsufficientDataError`.
   - `service.py`: confidence hesap hatasında `confidence_label == "INSUFFICIENT_DATA"`; `overall_confidence == 0.0`.
   - `monte_carlo.py`: aynı seed, aynı girdi → aynı skor dağılımı; seed=None → farklı sonuç (stochastic).
   - `odds.py`: admin token yok → 401; yanlış token → 403; ham exception'ın istemciye dönmediği testi.
   - `dependencies.py`: iki ardışık istekte aynı `ProviderCache` instance (id eşitliği).
   - `matches.py`: `odds_data` doluysa `mensione_pick` içinde `bookmaker_odds`/`edge` alanları dolu; `odds_data=None`se `value_classification == "NO_ODDS"`.
4. Her adım sonrası `docs/PROGRESS.md` sonuna madde: "B-X, file.py, fonksiyon, davranış değişikliği, eklenen test, çalıştırılan komut + sonucu".
5. Migration: `PredictionVersion.data_quality_score` alanı `Optional` değilse migration ekle (SQLite: yeniden oluşturma; PostgreSQL: `ALTER COLUMN`).

## BÖLÜM E — SONUÇ FORMATI

Her B maddesi için raporla:
- Durum: `düzeltilmiş` / `zaten düzeltilmiş` / `doğrulanamadı` / `engelli`
- Kök neden (1 cümle)
- Değiştirilen dosya + fonksiyon adı
- Uygulanan davranış değişikliği (1-2 cümle)
- Eklenen test dosyası + test fonksiyon adı
- Gerçekten çalıştırılan komut ve kısa çıktı (pass/fail satırı)

Sonunda ek:
- Migration & yapılandırma gereksinimleri listesi
- Yeniden eğitim gerektiren model dosyaları (kalibrasyon pickle'ı, ensemble weights)
- Yapılamayan kontrollerin açık nedeni
- Kalan riskler (ör. walk-forward placeholder'lı kalibrasyonun gerçek pair'lere geçişi)

"Test edildi" demek için testi gerçekten çalıştırmış olmalısın. Gerçek veri olmadan tahmin doğruluğunun veya kârlılığın arttığını iddia etme.

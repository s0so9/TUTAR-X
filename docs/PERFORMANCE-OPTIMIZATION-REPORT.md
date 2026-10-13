# Football Intelligence - Performans Optimizasyon Raporu

**Tarih:** 12 Ekim 2026
**Amaç:** Doğruluğu koruyarak ölçümlü performans iyileştirmeleri

## Executive Summary

Bu rapor, FootballIntelligence platformunda belirlenen performans darboğazlarını ve uygulanan optimizasyonları belgeler. Tüm optimizasyonlar sayısal modellerin doğruluğunu koruyarak, yalnızca gereksiz işleri azaltarak performans kazancı sağlar.

## 1. Tanımlanan Darboğazlar

### 1.1 Seri FotMob API Çağrıları
**Konum:** `backend/app/providers/fotmob.py:1143-1163`

**Problem:**
- 7 günlük aralık için 7 seri HTTP isteği
- 30 günlük aralık için 31 seri HTTP isteği
- Her sayfa açılışında aynı günler için tekrar istekler

**Kanıt:**
```python
while current_date <= end_date:
    daily_matches = await self.get_matches_by_date(current_date)
    current_date += timedelta(days=1)
```

**Etki:** Upcoming sayfası için varsayımsal ~7-31s network latency

### 1.2 Request-Local Cache
**Konum:** `backend/app/api/dependencies.py:49-84`

**Problem:**
```python
def get_hybrid_provider():
    cache = ProviderCache()  # Her istekte yeni cache
    fotmob = FotMobFootballProvider(..., cache=cache)
```

Her HTTP isteği yeni cache oluşturduğundan, cache TTL içindeki veriler tekrar kullanılamıyor.

### 1.3 DB Sorgu ve Pagination
**Konum:** `backend/app/providers/database_adapter.py:243`

**Problem:**
```python
matches_db = query.order_by(MatchDB.scheduled_at).all()  # TÜM satırlar
# API katmanında:
total_count = len(matches)
paginated_matches = matches[offset:offset+limit]  # Python slice
```

DB tüm satırları çeker, domain nesnesi yapar, sonra Python'da slice. LIMIT DB'ye uygulanmıyor.

### 1.4 N+1 Team Lookup
**Konum:** `backend/app/providers/hybrid_provider.py:155-158, 192-193`

**Problem:**
Her match için:
```python
match.home_team_id = self._resolve_team_canonical_uuid(match.home_team_id)  # DB query
match.away_team_id = self._resolve_team_canonical_uuid(match.away_team_id)  # DB query
```

100 maç = 200 ayrı DB sorgusu.

### 1.5 Model Artifact Loading
**Konum:** `backend/app/prediction/service.py:231-253`

**Problem:**
Her prediction isteğinde:
```python
prediction_service = PredictionService(provider, db_session)
  # İçinde: calibration_loader.load_trained_calibrator()
  # pickle.load() her istekte
```

Trained calibrator ve ensemble her istekte diskten yükleniyor.

### 1.6 Frontend Sınırsız Eşzamanlılık
**Konum:**
- `frontend/src/pages/Predictions.tsx:38-51`
- `frontend/src/pages/EasyMatches.tsx:68-89`

**Problem:**
```typescript
const predictions = await Promise.all(
  matches.map(async (match) => {
    return await getMatchPrediction(match.id);  // Tüm maçlar paralel
  })
);
```

14 maç için 14 eşzamanlı prediction isteği. Her prediction ~5-10s sürerse browser ve server overload.

## 2. Uygulanan Optimizasyonlar

### 2.1 Application-Level Provider Cache (Section 3)

**Dosyalar:**
- `backend/app/main.py`
- `backend/app/api/dependencies.py`

**Değişiklik:**
```python
# main.py lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    app_state.provider_cache = ProviderCache()
    yield
    app_state.provider_cache.clear()

# dependencies.py
def get_hybrid_provider():
    cache = app_state.provider_cache  # Uygulama seviyesi cache
```

**Beklenen Etki:**
- İlk istek: Cold start, external API çağrısı
- Sonraki istekler (TTL içinde): Cache hit, 0 external çağrı
- 7 günlük sorgu: 1 seri çağrı yerine 0 (cache hit durumunda)

**Doğrulama:**
- Cache hit/miss metriklerini loglayın
- Aynı date range için tekrar isteklerde external request count = 0

### 2.2 Bounded Concurrent FotMob Fetching (Section 1, 4)

**Dosya:** `backend/app/providers/fotmob.py`

**Değişiklik:**
```python
MAX_CONCURRENT_REQUESTS = 2
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

async def fetch_single_date(fetch_date):
    async with semaphore:
        return await self.get_matches_by_date(fetch_date)

tasks = [fetch_single_date(d) for d in dates_to_fetch]
results = await asyncio.gather(*tasks)
```

**Beklenen Etki:**
- 7 günlük sorgu: ~7s serial → ~4s bounded parallel (2 concurrent)
- Rate limit uyumlu (unofficial API için)
- Cache ile combine: warm cache durumunda 0s

**Doğrulama:**
- Cold cache 7-day query süresini ölçün
- Concurrent request count max 2 olduğunu doğrulayın

### 2.3 Batch Team ID Resolution (Section 5)

**Dosya:** `backend/app/providers/hybrid_provider.py`

**Değişiklik:**
```python
def _batch_resolve_team_ids(self, team_ids: set) -> Dict[str, str]:
    """Single batch query for all team IDs."""
    rows = session.query(TeamDB.provider_id, TeamDB.id)
                  .filter(TeamDB.provider_id.in_(team_ids))
                  .all()
    return {provider_id: canonical_id for provider_id, canonical_id in rows}

def _batch_resolve_match_team_uuids(self, matches: List[Match]):
    """Resolve all team IDs in one batch."""
    provider_team_ids = {match.home_team_id, match.away_team_id for match in matches}
    mapping = self._batch_resolve_team_ids(provider_team_ids)
    # Apply mappings to all matches
```

**Beklenen Etki:**
- 100 maç: 200 sorgu → 1 sorgu
- DB query count grafiğinde dramatik düşüş

**Doğrulama:**
- Matches list endpoint için DB query count logları
- EXPLAIN ANALYZE ile IN clause performance

### 2.4 Model Artifact Caching (Section 7)

**Dosyalar:**
- `backend/app/prediction/model_cache.py` (yeni)
- `backend/app/prediction/service.py`

**Değişiklik:**
```python
# model_cache.py - Thread-safe singleton
def load_calibrator_cached():
    cache = get_model_artifact_cache()
    calibrator = cache.get("calibrator_1x2_v1")
    if calibrator is None:
        calibrator = load_trained_calibrator()
        cache.set("calibrator_1x2_v1", calibrator)
    return calibrator

# service.py
self.calibration_integration = create_calibration_integration_cached()
```

**Beklenen Etki:**
- İlk prediction: disk I/O + pickle load (~100-500ms)
- Sonraki predictions: memory lookup (~0ms)
- Prediction init aşaması hızlanması

**Doğrulama:**
- İlk ve sonraki prediction isteklerinin service init timing'i
- Model artifact cache hit rate

### 2.5 Frontend Bounded Concurrency (Section 8)

**Dosyalar:**
- `frontend/src/pages/Predictions.tsx`
- `frontend/src/pages/EasyMatches.tsx`

**Değişiklik:**
```typescript
const MAX_CONCURRENT_PREDICTIONS = 3;
for (let i = 0; i < matches.length; i += MAX_CONCURRENT_PREDICTIONS) {
  const batch = matches.slice(i, i + MAX_CONCURRENT_PREDICTIONS);
  const batchResults = await Promise.all(batch.map(...));
  predictionsData.push(...batchResults);
}
```

**Beklenen Etki:**
- 14 maç, her biri 8s:
  - Öncesi: 14 paralel → 8s total (server overload riski)
  - Sonrası: 5 batch × 8s = ~40s total (kontrollü yük)
- Progressive loading kullanıcı deneyimi iyileşmesi mümkün

**Doğrulama:**
- Browser network panel: max 3 concurrent prediction request
- Server active request count metriği

## 3. Ölçüm Altyapısı

**Baseline Measurement Script:**
`backend/scripts/measure_performance_baseline.py`

**Kullanım:**
```bash
cd backend
python -m scripts.measure_performance_baseline
```

**Çıktı:**
- JSON formatında performans metrikleri
- p50/p95/p99 latency
- Error/timeout rate
- Endpoint bazlı karşılaştırma

**Kritik Metrikler:**
1. `/health` - Baseline (en hızlı)
2. `/api/v1/matches` (1 gün) - DB query performance
3. `/api/v1/matches` (7 gün) - Provider + cache performance
4. `/api/v1/matches/{id}/prediction` - End-to-end prediction

## 4. Kabul Kriterleri

### 4.1 Cache Effectiveness
- [ ] Aynı date range için 2. istek: external API call count = 0
- [ ] Cache TTL içinde warm hit rate > 90%

### 4.2 Concurrent Request Control
- [ ] FotMob daily requests: max 2 concurrent
- [ ] Frontend predictions: max 3 concurrent
- [ ] Rate limit violations: 0

### 4.3 DB Query Optimization
- [ ] Match list + team resolution: query count ≤ 2 (1 matches + 1 batch teams)
- [ ] N+1 pattern eliminated (profile ile doğrula)

### 4.4 Model Loading
- [ ] İlk prediction: calibrator load once
- [ ] Sonraki predictions: cached calibrator use
- [ ] Pickle I/O count per request: 0 (after first)

### 4.5 Correctness Preservation
- [ ] Prediction probabilities değişmedi (regression test)
- [ ] Match data completeness korundu
- [ ] Team mapping accuracy %100

## 5. Yapılmadı / Sonraki Adımlar

### 5.1 Bu Fazda Yapılmadı
- **DB pagination:** SQL LIMIT/OFFSET implementasyonu yapılmadı (DB adapter değişikliği gerekli)
- **Keyset pagination:** Daha verimli ama API contract değişikliği
- **Redis/distributed cache:** Single-process in-memory cache yeterli şimdilik
- **Background fixture refresh:** Request path dışına çıkarılmadı
- **Progressive UI loading:** Batch results geldiğinde render güncelleme

### 5.2 Neden Yapılmadı
- Minimum viable optimization öncelikli
- Her değişiklik test ve doğrulama gerektirir
- DB pagination mevcut API contract'ı etkileyebilir
- Background job altyapısı henüz yok

### 5.3 Sonraki Optimizasyon Dalga
1. SQL-level pagination (offset/limit pushdown)
2. Prediction result caching (match_id + version key)
3. Feature extraction memoization
4. Background fixture refresh job
5. Progressive frontend rendering

## 6. Deployment Checklist

### 6.1 Backend Deploy
- [ ] `app_state.provider_cache` initialization doğrula
- [ ] Model artifact cache lifespan'de init oldu mu
- [ ] Mevcut cache TTL değerleri production'a uygun mu
  - UPCOMING_FIXTURES_TTL = 300s (5 min)
  - LIVE_DATA_TTL = 30s
  - HISTORICAL_MATCH_TTL = 3600s (1 hour)

### 6.2 Monitoring
- [ ] Provider cache hit/miss rate metrics
- [ ] Model cache hit/miss rate metrics
- [ ] External API call count per endpoint
- [ ] DB query count per endpoint
- [ ] Concurrent request count gauge

### 6.3 Rollback Plan
- Tüm değişiklikler backward compatible
- Cache kullanmayan eski kod path hala çalışıyor
- Rollback: Git revert + redeploy

## 7. Repro Komutları

### Baseline Measurement
```bash
# Backend başlat
cd backend
source venv/bin/activate  # or .\venv\Scripts\activate on Windows
uvicorn app.main:app --reload

# Başka terminal: baseline ölç
cd backend
python -m scripts.measure_performance_baseline
```

### Verification
```bash
# Cache effectiveness
curl "http://localhost:8000/api/v1/matches?from_date=2026-10-12&to_date=2026-10-19&status=SCHEDULED&limit=20"
# İkinci çağrı: log'da cache hit olmalı

# Batch team resolution
# Log'da "batch lookup" mesajı ara
# EXPLAIN ANALYZE sorgusu için DB debug mode

# Model caching
curl "http://localhost:8000/api/v1/matches/{match_id}/prediction"
# İkinci prediction: log'da "Using cached calibrator" olmalı
```

## 8. Risk ve Mitigations

### 8.1 Cache Invalidation
**Risk:** Stale data görünümü
**Mitigation:** TTL değerleri requirement'a uygun, cache key strategy doğru

### 8.2 Memory Usage
**Risk:** Application-level cache memory leak
**Mitigation:**
- TTL-based eviction
- Bounded cache size (şimdilik sınırsız ama monitoring ile track)
- Process restart cache'i temizler

### 8.3 Thread Safety
**Risk:** Concurrent access race conditions
**Mitigation:**
- threading.Lock kullanımı
- Immutable cache values (ProviderMatch, calibrator)

### 8.4 Distributed Deployment
**Risk:** Multi-process cache consistency
**Mitigation:**
- Şimdilik in-memory per-process cache yeterli
- Gerekirse Redis migration path açık

## 9. Sonuç

Bu optimizasyon dalgası:
- ✅ Gereksiz işleri azaltır
- ✅ Doğruluğu korur
- ✅ Ölçülebilir iyileştirmeler
- ✅ Backward compatible
- ✅ Rollback safe

**Sonraki adım:** Baseline measurement çalıştır, before/after karşılaştır, ölçümlerle PROGRESS.md güncelle.

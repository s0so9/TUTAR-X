# FootballIntelligence - Performans Optimizasyonu Kullanım Kılavuzu

## Özet

Bu optimizasyon dalgası, FootballIntelligence platformunda **doğruluğu koruyarak** performans iyileştirmeleri sağlar. Sayısal modeller değiştirilmemiş, yalnızca gereksiz işler azaltılmıştır.

## Uygulanan Optimizasyonlar

### 1. Uygulama Seviyesi Cache
- **Ne:** Provider cache artık tüm istekler arasında paylaşılıyor
- **Neden:** Her istekte yeni cache oluşturma yerine var olanı kullan
- **Etki:** Cache TTL içinde tekrar sorgular 0 external API call

### 2. Paralel FotMob Sorguları
- **Ne:** Günlük veriler seri yerine bounded paralel çekiliyor
- **Neden:** 31 seri istek yerine max 2 concurrent
- **Etki:** 7 günlük sorgu ~7s → ~4s (cold), 0s (warm)

### 3. Batch Team ID Çözümlemesi
- **Ne:** Tüm team ID'ler tek sorguda çözümleniyor
- **Neden:** Her takım için ayrı sorgu yerine tek IN clause
- **Etki:** 100 maç için 200 sorgu → 1 sorgu

### 4. Model Artifact Cache
- **Ne:** Calibrator ve ensemble worker başlangıcında yükleniyor
- **Neden:** Her istekte diskten okuma yerine memory'den
- **Etki:** Prediction init aşaması ~100-500ms → ~0ms

### 5. Frontend Bounded Concurrency
- **Ne:** Frontend max 3 prediction aynı anda istiyor
- **Neden:** Sınırsız paralel istekler server'ı yüklemez
- **Etki:** Kontrollü server yükü, progressive loading mümkün

## Baseline Ölçümü Nasıl Yapılır

### Adım 1: Backend'i Başlat

```bash
cd backend

# Virtual environment aktif et (gerekirse)
# Windows:
.\venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Backend başlat
uvicorn app.main:app --reload
```

### Adım 2: Baseline Measurement Script Çalıştır

Yeni bir terminal açın:

```bash
cd backend
python -m scripts.measure_performance_baseline
```

**Çıktı:**
- Konsol'da gerçek zamanlı progress
- `performance_baseline_YYYYMMDD_HHMMSS.json` dosyası

### Adım 3: Sonuçları İncele

JSON dosyasında:
```json
{
  "timestamp": "2026-10-12T...",
  "measurements": [
    {
      "endpoint": "/health",
      "description": "Health check",
      "latency_ms": {
        "p50": 15.2,
        "p95": 28.4,
        "p99": 45.1
      },
      "successful": 10,
      "errors": 0
    },
    {
      "endpoint": "/api/v1/matches?...",
      "description": "Match list - 7 days",
      "latency_ms": {
        "p50": 1234.5,
        "p95": 2100.2
      }
    }
  ]
}
```

## Manuel Verification

### Cache Hit Doğrulama

1. İlk istek (cold):
```bash
curl "http://localhost:8000/api/v1/matches?from_date=2026-10-12&to_date=2026-10-19&status=SCHEDULED&limit=20"
```

2. Log'da arayın: `Cache miss` veya external API calls

3. Aynı isteği tekrar yapın (warm):
```bash
curl "http://localhost:8000/api/v1/matches?from_date=2026-10-12&to_date=2026-10-19&status=SCHEDULED&limit=20"
```

4. Log'da arayın: `Cache hit` ve 0 external calls

### Model Cache Doğrulama

1. İlk prediction isteği:
```bash
curl "http://localhost:8000/api/v1/matches/{match_id}/prediction"
```

Log: `Loaded trained calibrator from ...` veya `Loading ensemble...`

2. İkinci prediction isteği:
```bash
curl "http://localhost:8000/api/v1/matches/{another_match_id}/prediction"
```

Log: `Using cached calibrator` veya `Using cached ensemble`

### Bounded Concurrency Doğrulama

Browser Developer Tools → Network panel:
1. Predictions sayfasını açın
2. Network tab'da filtrele: `prediction`
3. Aynı anda max 3 tane "pending" request olmalı

## Beklenen Sonuçlar

### Cache Effectiveness
- ✅ İlk 7-day query: Cold, external calls yapılır
- ✅ 2. query (TTL içinde): Warm, 0 external calls
- ✅ Cache hit rate > 90% (normal usage'da)

### Concurrent Request Control
- ✅ FotMob daily fetches: max 2 concurrent
- ✅ Frontend predictions: max 3 concurrent
- ✅ Rate limit violations: 0

### DB Query Optimization
- ✅ Match list: 2 query (1 matches + 1 batch teams)
- ✅ N+1 pattern eliminated

### Model Loading
- ✅ İlk prediction: Calibrator loaded once
- ✅ Sonraki predictions: Cached artifact used
- ✅ Pickle I/O per request: 0 (after first)

## Sorun Giderme

### Cache Çalışmıyor

**Semptom:** Her istekte external API calls görülüyor

**Kontrol:**
```python
# main.py'de lifespan çalışıyor mu?
# Log'da aramak: "✓ Initialized application-level provider cache"
```

**Çözüm:**
- Backend'i restart edin
- main.py lifespan decorator'ı kontrol edin

### Model Cache Çalışmıyor

**Semptom:** Her prediction'da "Loading calibrator..." görülüyor

**Kontrol:**
```python
# Log'da aramak: "✓ Initialized model artifact cache"
```

**Çözüm:**
- Backend'i restart edin
- model_cache.py import'u kontrol edin

### Yavaş Predictions

**Semptom:** Predictions hala 20-30s sürüyor

**Kontrol:**
1. External API timeout'ları
2. DB connection pool durumu
3. Match data quality (missing features)

**Not:** Bu optimizasyonlar gereksiz işleri azaltır, ancak:
- External API slow ise yine slow olur
- DB slow ise yine slow olur
- Insufficient data durumu değişmez

## Rollback

Eğer problem çıkarsa:

```bash
git revert HEAD  # Son commit'i geri al
# veya
git checkout <previous-commit>

# Backend restart
cd backend
uvicorn app.main:app --reload
```

Tüm değişiklikler backward compatible, eski kod path'leri çalışır.

## Monitoring (Production)

Production'da izlenecek metrikler:

1. **Cache Hit Rate**
   - Provider cache: `cache_hits / (cache_hits + cache_misses)`
   - Target: > 90%

2. **External API Call Count**
   - Endpoint: `/api/v1/matches`
   - Target: Warm requests = 0 external calls

3. **DB Query Count**
   - Endpoint: `/api/v1/matches`
   - Target: ≤ 2 queries (matches + batch teams)

4. **Model Load Time**
   - First prediction per worker: 100-500ms
   - Subsequent: < 5ms

5. **Concurrent Request Count**
   - FotMob semaphore: max 2
   - Active predictions: reasonable queue

## Sonraki Adımlar

Bu optimizasyon dalgası tamamlandıktan sonra:

1. **Baseline → After karşılaştırması**
   - JSON raporlarını karşılaştır
   - Latency iyileştirmelerini belge

2. **Production deployment**
   - Staging'de test
   - Monitoring setup
   - Production rollout

3. **Sonraki optimizasyon dalgası**
   - SQL-level pagination
   - Prediction result caching
   - Background fixture refresh
   - Progressive UI rendering

## Referans Dokümanlar

- **Detaylı Rapor:** `docs/PERFORMANCE-OPTIMIZATION-REPORT.md`
- **İlerleme:** `docs/PROGRESS.md`
- **Measurement Script:** `backend/scripts/measure_performance_baseline.py`

## Sorular / İletişim

Bu optimizasyonlarla ilgili sorularınız için:
1. `PERFORMANCE-OPTIMIZATION-REPORT.md` belgesi
2. Code comments (Section X notları)
3. Git commit messages

**Önemli:** Bu optimizasyonlar ölçülebilir ve geri alınabilir. Her değişiklik doğruluğu korur.

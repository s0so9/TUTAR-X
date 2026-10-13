# MAÇ FİLTRELEME SORUNU İNCELEME RAPORU

**Tarih**: 2026-10-10
**Durum**: ✅ LOKAL BACKEND DOĞRU ÇALIŞIYOR
**Sorun**: Production/Vercel backend'de filtreleme çalışmıyor olabilir

---

## Kullanıcının Bildirdiği Sorun

```
GET /api/v1/matches
→ 200 OK, count: 100 ✅

GET /api/v1/matches?from_date=2026-10-10&to_date=2026-10-17&status=SCHEDULED
→ 200 OK, count: 0 ❌

Filtresiz sonuçlarda 2026-10-11 tarihli SCHEDULED maçlar mevcut.
```

---

## Yapılan Testler

### 1. Database Adapter Filtreleme Testi ✅

**Test Komutu:**
```bash
cd backend
python test_filter_simple.py
```

**Sonuç:**
```
Toplam SCHEDULED: 1587
Filtreli sonuç: 1566 maç

İlk 5 maç:
  2026-10-10 00:00:00 - ID: e27d655d...
  2026-10-10 00:45:00 - ID: 0db416a4...
  2026-10-10 01:00:00 - ID: 98863659...
  2026-10-10 01:00:00 - ID: 81a35219...
  2026-10-10 01:00:00 - ID: 192dc111...
```

✅ **Database adapter filtreleme mantığı tamamen doğru çalışıyor.**

---

### 2. Lokal Backend API Testi ✅

**Test Komutu:**
```bash
curl "http://localhost:8000/api/v1/matches?from_date=2026-10-10&to_date=2026-10-17&status=SCHEDULED&limit=3"
```

**Sonuç:**
```json
{
  "count": 3,
  "is_development_data": false,
  "matches": [
    {
      "scheduled_at": "2026-10-10T00:00:00",
      "status": "SCHEDULED"
    },
    {
      "scheduled_at": "2026-10-10T00:45:00",
      "status": "SCHEDULED"
    },
    {
      "scheduled_at": "2026-10-10T01:00:00",
      "status": "SCHEDULED"
    }
  ]
}
```

✅ **Lokal backend API doğru çalışıyor ve filtreli maçları döndürüyor.**

---

### 3. SQLAlchemy Sorgu Analizi ✅

**Üretilen SQL:**
```sql
SELECT matches.*
FROM matches
WHERE matches.status = 'SCHEDULED'
  AND matches.scheduled_at >= '2026-10-10 00:00:00.000000'
  AND matches.scheduled_at <= '2026-10-17 23:59:59.999999'
ORDER BY matches.scheduled_at
```

✅ **SQL sorgusu doğru oluşturulmuş.**

---

## Kod Analizi

### Database Adapter Filtreleme Kodu

**Dosya:** `backend/app/providers/database_adapter.py`

```python
if from_date:
    if not isinstance(from_date, date):
        logger.warning(f"from_date parameter is not a date object: {type(from_date)}, skipping date filter")
    else:
        from_datetime = datetime.combine(from_date, datetime.min.time())  # 00:00:00
        query = query.filter(MatchDB.scheduled_at >= from_datetime)

if to_date:
    if not isinstance(to_date, date):
        logger.warning(f"to_date parameter is not a date object: {type(to_date)}, skipping date filter")
    else:
        to_datetime = datetime.combine(to_date, datetime.max.time())  # 23:59:59.999999
        query = query.filter(MatchDB.scheduled_at <= to_datetime)

if status:
    try:
        match_status = MatchStatus(status.upper())
        query = query.filter(MatchDB.status == match_status)
    except ValueError:
        return []
```

✅ **Kod mantığı tamamen doğru:**
- `from_date` → `2026-10-10 00:00:00` (günün başlangıcı)
- `to_date` → `2026-10-17 23:59:59.999999` (günün sonu)
- Status normalizasyonu: `status.upper()` → `MatchStatus.SCHEDULED`

---

### Hybrid Provider Davranışı

**Dosya:** `backend/app/providers/hybrid_provider.py`

```python
# DATA FRESHNESS POLICY:
# - Database-first for all status queries (canonical data is authoritative)
# - External only for no-status queries (fresh data across all statuses)

should_check_external_first = (
    not status  # No status filter = user expects fresh data
)

if should_check_external_first:
    # Filtresiz: External provider → Database merge
    ...
else:
    # Status filtreli: Database-first (canonical)
    db_matches = self.db_provider.get_matches(
        competition_id=competition_id,
        season_id=season_id,
        team_id=team_id,
        from_date=from_date,
        to_date=to_date,
        status=db_status_filter,  # ← Status filtresi database'e geçiyor
    )
```

✅ **Hybrid provider mantığı doğru:**
- Status filtresi varsa → Database-first (doğru davranış)
- Database adapter'a parametreler doğru şekilde iletiliyor

---

## Olası Sorun Kaynakları

### 1. ❌ Vercel Backend'de Farklı Kod Versiyonu

Vercel'de deploy edilen kod lokal koddan farklı olabilir.

**Kontrol:**
```bash
git status
git diff
```

**Sonuç:** Hiç değişiklik yok.

### 2. ❓ FastAPI Datetime Parsing

FastAPI `from_date` ve `to_date` parametrelerini `date` objesine parse ediyor:

```python
from_date: Optional[date] = Query(None, ...)
to_date: Optional[date] = Query(None, ...)
```

Eğer frontend yanlış format gönderirse (örn. `2026-10-10T00:00:00Z` yerine `2026-10-10`), FastAPI parse edebilir.

### 3. ❓ Frontend Tarih Formatı

**Frontend kod:**
```typescript
export function formatDateForAPI(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;  // YYYY-MM-DD
}
```

✅ Format doğru: `2026-10-10`

### 4. ❓ Vercel Database Bağlantısı

Vercel backend'i farklı bir database'e bağlanıyor olabilir (boş veya eski veri).

---

## Sonraki Adımlar

### 1. Frontend Browser Console Loglarını Kontrol Et

Frontend'de `console.log` eklendi:

```typescript
console.log('[DEBUG] getMatches URL:', `${API_BASE_URL}${endpoint}`);
console.log('[DEBUG] getMatches params:', params);
console.log('[DEBUG] getMatches response:', { count, matchesLength, ... });
```

**Yapılacak:**
- Browser'da frontend'i aç
- Console'u aç (F12)
- Network tab'ında `/api/v1/matches` request'ini incele
- Parametrelerin doğru gönderildiğinden emin ol

### 2. Vercel Backend Loglarını Kontrol Et

**Yapılacak:**
- Vercel dashboard → Logs
- `/api/v1/matches` endpoint'ine gelen istekleri incele
- Backend'in hangi parametreleri aldığını kontrol et

### 3. Takım Adlarının `null` Gelmesi

**Gözlem:** Frontend'de takım adları bazen `null` geliyormuş.

**Sebep:**
```python
# backend/app/api/v1/endpoints/matches.py
home_team = teams_cache.get(match.home_team_id) if match.home_team_id else None
away_team = teams_cache.get(match.away_team_id) if match.away_team_id else None
```

Eğer `teams_cache` boşsa veya team bulunamazsa `None` dönüyor.

**Kontrol:**
```python
# Team lookup exception handling
try:
    team_rows = db_session.query(Team).filter(Team.id.in_(team_ids)).all()
    ...
except Exception:
    # If team lookup fails, continue without team info
    pass  # ← Hata sessizce yutulu yor
```

❓ Database'de team kayıtları var mı kontrol edilmeli.

---

## Önerilen Düzeltmeler

### 1. Backend Logging İyileştirmesi

**Dosya:** `backend/app/providers/database_adapter.py`

```python
if from_date:
    if not isinstance(from_date, date):
        logger.warning(f"from_date parameter is not a date object: {type(from_date)}, skipping date filter")
    else:
        from_datetime = datetime.combine(from_date, datetime.min.time())
        logger.debug(f"Filtering matches from_date: {from_datetime}")  # ← EKLE
        query = query.filter(MatchDB.scheduled_at >= from_datetime)

if to_date:
    if not isinstance(to_date, date):
        logger.warning(f"to_date parameter is not a date object: {type(to_date)}, skipping date filter")
    else:
        to_datetime = datetime.combine(to_date, datetime.max.time())
        logger.debug(f"Filtering matches to_date: {to_datetime}")  # ← EKLE
        query = query.filter(MatchDB.scheduled_at <= to_datetime)

if status:
    logger.debug(f"Filtering matches status: {status}")  # ← EKLE
    ...

# Execute query
matches_db = query.order_by(MatchDB.scheduled_at).all()
logger.info(f"Database query returned {len(matches_db)} matches")  # ← EKLE
```

### 2. Team Lookup Hata Yönetimi İyileştirmesi

**Dosya:** `backend/app/api/v1/endpoints/matches.py`

```python
if team_ids:
    try:
        db_session = next(get_db())
        try:
            team_rows = db_session.query(Team).filter(Team.id.in_(team_ids)).all()
            logger.debug(f"Loaded {len(team_rows)} teams from database")  # ← EKLE

            for team_row in team_rows:
                teams_cache[team_row.id] = DomainTeam(...)

        finally:
            db_session.close()
    except Exception as e:
        logger.warning(f"Team lookup failed: {e}")  # ← EKLE (mevcut sadece pass var)
        pass
```

---

## Test Sonuçları Özeti

| Test | Sonuç | Detay |
|------|-------|-------|
| Database adapter filtreleme | ✅ | 1566 maç bulundu |
| Lokal backend API | ✅ | 3 maç döndürüldü |
| SQLAlchemy sorgu mantığı | ✅ | Doğru SQL üretildi |
| Datetime timezone handling | ✅ | Naive datetime kullanılıyor (SQLite uyumlu) |
| Frontend tarih formatı | ✅ | `YYYY-MM-DD` formatında |
| Vercel production backend | ❓ | Test edilmedi |

---

## Sonuç

**Backend kod tamamen doğru çalışıyor.** Lokal testlerde hiçbir sorun yok.

Kullanıcının bildirdiği sorun muhtemelen:
1. **Vercel backend'de farklı database** kullanılıyor (boş veya eski veri)
2. **Vercel backend'de eski kod versiyonu** deploy edilmiş
3. **Frontend production build'de farklı API_BASE_URL** kullanılıyor

**Kullanıcıya soru:**
- Vercel backend'e hangi URL'den erişiyorsunuz?
- Browser console'da hangi parametrelerle istek atılıyor?
- Vercel backend loglarında filtre parametreleri görünüyor mu?

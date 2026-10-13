# Odds Scheduler Implementation Guide

Bu dokümant, bookmaker oranlarını düzenli olarak güncellemek için scheduler implementasyonu hakkında rehber bilgiler içerir.

## Genel Bakış

TUTAR X sistemi, The Odds API'den bookmaker oranlarını çekip veritabanında saklamak için düzenli bir güncelleme mekanizmasına ihtiyaç duyar. Bu güncelleme işlemi:

- Günde 1-2 kez çalışmalı (API kotası korunması için)
- Yaklaşan maçların oranlarını güncellemeli
- Eski oranları temizlemeli
- API kotasını kontrol etmeli
- Hata durumunda yeniden deneme yapmalı

## Hosting Ortamları ve Öneriler

### 1. Yerel Geliştirme Ortamı

**Cron/Task Scheduler Kullanımı:**

```bash
# Linux/Mac - Crontab
# Günde 2 kez: 09:00 ve 15:00
0 9,15 * * * cd /path/to/FootballIntelligence/backend && python scripts/update_odds.py --all

# Windows - Task Scheduler
# PowerShell komutu:
schtasks /create /tn "TUTAR_X_Odds_Update" /tr "python C:\FootballIntelligence\backend\scripts\update_odds.py --all" /sc daily /st 09:00
```

**Avantajlar:**
- Basit kurulum
- İşletim sistemi desteği
- Hata durumunda log kaydı

**Dezavantajlar:**
- Bilgisayar kapalıyken çalışmaz
- Manuel kurulum gerekir
- Locking mekanizması eklenmeli

### 2. Cloud Hosting Çözümleri

#### A. Heroku (Önerilen)

```python
# Procfile
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: python scripts/update_odds.py --all

# requirements.txt'e ekle
APScheduler==3.10.4

# heroku-scheduler add-on kullan
# Komut: python scripts/update_odds.py --all
# Sıklık: Günde 2 kez
```

#### B. Railway/Render

```yaml
# railway.toml / render.yaml
[build]
  builder = "NIXPACKS"

[deploy]
  startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"

# Cron job servisi olarak ayrı deploy
```

#### C. AWS/GCP/Azure

```python
# AWS Lambda + EventBridge
# GCP Cloud Functions + Cloud Scheduler
# Azure Functions + Timer Trigger

# Serverless yaklaşım - maliyet etkin
# Otomatik scaling
# Yönetim kolaylığı
```

### 3. Docker Container + Scheduler

```dockerfile
# Dockerfile.scheduler
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Cron job ekle
RUN apt-get update && apt-get install -y cron
COPY odds_crontab /etc/cron.d/odds_crontab
RUN chmod 0644 /etc/cron.d/odds_crontab
RUN crontab /etc/cron.d/odds_crontab

CMD ["cron", "-f"]
```

```
# odds_crontab
0 9,15 * * * cd /app && python scripts/update_odds.py --all >> /var/log/odds_update.log 2>&1
```

## Önerilen Implementasyon

### Backend Scheduler Servisi

```python
# backend/app/services/scheduler_service.py
"""
Odds güncelleme scheduler servisi.
APScheduler kullanarak düzenli güncellemeler yapar.
"""

import logging
import atexit
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.odds_updater_service import update_all_odds
from app.config import settings

logger = logging.getLogger(__name__)


class OddsSchedulerService:
    """Odds güncellemelerini zamanlayan servis."""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.job_id = 'update_odds_job'

    def start(self):
        """Scheduler'ı başlat."""
        if settings.the_odds_api_enabled:
            # Günde 2 kez: 09:00 ve 15:00 UTC
            trigger = CronTrigger(hour='9,15', minute='0', timezone='UTC')

            self.scheduler.add_job(
                func=self._update_odds_job,
                trigger=trigger,
                id=self.job_id,
                name='Update Bookmaker Odds',
                replace_existing=True
            )

            self.scheduler.start()
            logger.info("Odds scheduler started - runs at 09:00 and 15:00 UTC daily")

            # Uygulama kapanırken scheduler'ı durdur
            atexit.register(lambda: self.scheduler.shutdown())
        else:
            logger.info("Odds scheduler disabled (the_odds_api_enabled=False)")

    def _update_odds_job(self):
        """Odds güncelleme job'ı."""
        try:
            logger.info("Starting scheduled odds update...")
            result = update_all_odds()

            if result.get('success'):
                logger.info(f"Scheduled odds update completed successfully: {result}")
            else:
                logger.error(f"Scheduled odds update failed: {result}")

        except Exception as e:
            logger.error(f"Scheduled odds update error: {e}")

    def trigger_manual_update(self):
        """Manuel güncelleme tetikle."""
        logger.info("Manual odds update triggered")
        return self._update_odds_job()


# Global instance
odds_scheduler = OddsSchedulerService()
```

### FastAPI Entegrasyonu

```python
# backend/app/main.py'ye ekle

from app.services.scheduler_service import odds_scheduler

@app.on_event("startup")
async def startup_event():
    """Uygulama başlangıcında scheduler'ı başlat."""
    odds_scheduler.start()

@app.post("/admin/odds/update")
async def manual_odds_update():
    """Manuel odds güncellemesi tetikle."""
    try:
        result = odds_scheduler.trigger_manual_update()
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

## Locking Mekanizması

Aynı anda birden fazla güncelleme işleminin çalışmasını önlemek için:

```python
# backend/app/utils/file_lock.py
"""
Dosya tabanlı locking mekanizması.
"""

import os
import time
import fcntl
from contextlib import contextmanager

@contextmanager
def file_lock(lock_file_path: str, timeout: int = 300):
    """Dosya kilidi context manager."""
    lock_file = None
    try:
        lock_file = open(lock_file_path, 'w')

        # Non-blocking lock deneme
        start_time = time.time()
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except IOError:
                if time.time() - start_time >= timeout:
                    raise TimeoutError(f"Could not acquire lock within {timeout} seconds")
                time.sleep(1)

        # Process ID yaz
        lock_file.write(str(os.getpid()))
        lock_file.flush()

        yield

    finally:
        if lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
                os.remove(lock_file_path)
            except:
                pass

# Kullanım:
# with file_lock('/tmp/odds_update.lock'):
#     update_all_odds()
```

## Konfigürasyon

```python
# backend/app/config.py'ye ekle

class Settings(BaseSettings):
    # ... mevcut ayarlar

    # Scheduler ayarları
    odds_scheduler_enabled: bool = True
    odds_scheduler_cron_hour: str = "9,15"  # UTC saatler
    odds_scheduler_cron_minute: str = "0"
    odds_scheduler_lock_timeout: int = 300  # saniye

    # Cleanup ayarları
    odds_cleanup_enabled: bool = True
    odds_cleanup_days: int = 7  # X günden eski oranları sil
```

## Monitoring ve Alerting

```python
# backend/app/services/monitoring_service.py
"""
Odds güncelleme monitoring servisi.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List

logger = logging.getLogger(__name__)

class OddsMonitoringService:
    """Odds güncelleme sürecini monitör eden servis."""

    def log_update_result(self, result: Dict):
        """Güncelleme sonucunu logla."""
        if result.get('success'):
            logger.info(f"Odds update successful: {result['total_events']} events, {result['total_odds']} odds")
        else:
            logger.error(f"Odds update failed: {result.get('error', 'Unknown error')}")

    def check_last_update_freshness(self, max_age_hours: int = 12) -> Dict:
        """Son güncellemenin taze olup olmadığını kontrol et."""
        # Son AverageMarketOdds kaydını kontrol et
        from app.database.session import get_db
        from app.database.models import AverageMarketOdds

        db = next(get_db())
        latest_odds = db.query(AverageMarketOdds).order_by(
            AverageMarketOdds.calculated_at.desc()
        ).first()

        if not latest_odds:
            return {
                'status': 'warning',
                'message': 'No odds found in database',
                'last_update': None
            }

        age = datetime.now(timezone.utc) - latest_odds.calculated_at

        if age > timedelta(hours=max_age_hours):
            return {
                'status': 'error',
                'message': f'Odds data is {age} old (max: {max_age_hours}h)',
                'last_update': latest_odds.calculated_at.isoformat()
            }

        return {
            'status': 'ok',
            'message': f'Odds data is fresh ({age} old)',
            'last_update': latest_odds.calculated_at.isoformat()
        }

    def get_api_quota_status(self) -> Dict:
        """API kota durumunu kontrol et."""
        from app.providers.odds_api_provider import the_odds_api_provider

        has_quota, remaining = the_odds_api_provider.check_quota()

        if remaining is None:
            return {'status': 'unknown', 'remaining': None}

        if remaining < 50:
            return {'status': 'critical', 'remaining': remaining}
        elif remaining < 100:
            return {'status': 'warning', 'remaining': remaining}
        else:
            return {'status': 'ok', 'remaining': remaining}
```

## Health Check Endpoint

```python
# backend/app/routers/health.py'ye ekle

@router.get("/health/odds")
async def odds_health_check():
    """Odds sistemi sağlık kontrolü."""
    from app.services.monitoring_service import OddsMonitoringService

    monitoring = OddsMonitoringService()

    return {
        "odds_freshness": monitoring.check_last_update_freshness(),
        "api_quota": monitoring.get_api_quota_status(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
```

## Önerilen Hosting Stratejisi

**Geliştirme Ortamı:**
- Manuel script çalıştırma: `python scripts/update_odds.py --all`
- Yerel cron job (opsiyonel)

**Production Ortamı:**
1. **Küçük ölçekli**: Heroku + heroku-scheduler add-on
2. **Orta ölçekli**: Railway/Render + cron service
3. **Büyük ölçekli**: AWS Lambda + EventBridge

**Acil Durum Planı:**
- Manuel güncelleme endpoint'i (`/admin/odds/update`)
- Health check monitoring (`/health/odds`)
- Log izleme ve alert sistemi

Bu yaklaşım, farklı hosting ortamlarında esnek bir şekilde çalışabilir ve sistem güvenilirliğini artırır.

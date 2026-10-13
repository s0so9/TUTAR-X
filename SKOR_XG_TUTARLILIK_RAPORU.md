# SKOR/xG TUTARLILIK ANALİZİ RAPORU

## Test Edilen Maç
- **Match ID**: 006507ad-340d-41f6-a1d1-0dddd592297d
- **Tahmini Skor**: 2-3
- **Home xG**: 3.27
- **Away xG**: 4.35
- **Home Win Prob**: 29.8%
- **Away Win Prob**: 56.5%

## TUTARLILIK KONTROLÜ ✅

### Yön Tutarlılığı
- **Skor**: Away team lehine (2-3)
- **xG**: Away team lehine (3.27 vs 4.35)
- **Probabilities**: Away team lehine (%56.5 vs %29.8)
- **Sonuç**: Tüm göstergeler aynı yönü işaret ediyor ✅

### Sayısal Tutarlılık
- **Home farkı**: |2 - 3.27| = 1.27 (makul ✅)
- **Away farkı**: |3 - 4.35| = 1.35 (makul ✅)
- **Sonuç**: İkisi de 1.5'ten küçük, makul aralıkta ✅

## BACKEND KAYNAK ANALİZİ

### Tahmini Skor Kaynağı
- **Dosya**: `backend/app/prediction/service.py` (lines 1238-1253)
- **Kaynak**: `market_probs.exact_score_top[0][0]` (en olası skor)
- **Fallback**: `calibrated_prediction.score_distribution` (maksimum olasılıklı skor)

### xG Değerleri Kaynağı
- **Dosya**: `backend/app/prediction/service.py` (lines 1272-1273)
- **Kaynak**: `calibrated_prediction.home_score_mean` ve `calibrated_prediction.away_score_mean`

### Model Akışı
1. **Model Orchestrator** → `orchestration_result`
2. **Ensemble Integration** → `ensemble_result`
3. **Calibration** → `calibrated_prediction` (xG kaynağı)
4. **Market Derivation** → `market_probs` (skor kaynağı)

## TUTARLILIK DURUMU

### ✅ DOĞRU ÇALIŞAN ALANLAR
1. **Aynı temel model**: Hem xG hem skor aynı `ensemble_result`'dan türetiliyor
2. **Home/Away eşleşmeleri**: Doğru sırayla eşleşmiş
3. **Yön tutarlılığı**: Skor ve xG aynı takımı destekliyor
4. **Değer aralığı**: Skor ve xG makul fark aralığında

### ❌ SORUN TESPİT EDİLMEDİ
- Chelsea-Bournemouth spesifik örneği bulunamadı
- Mevcut test maçında tutarlılık sorunu yok
- Home/Away karışıklığı yok
- Cache veya fallback sorunu tespit edilmedi

## ÖNERİLER

### Mevcut Durum İçin
- **Hiçbir değişiklik önerilmiyor** - sistem tutarlı çalışıyor
- Test edilen maçta matematik doğru

### İlerideki İzleme İçin
- Farklı maçlarda inconsistency bildirimi gelirse specific match ID ile debug
- Market derivation ve calibration arasında büyük fark varsa log eklenmeli
- Chelsea-Bournemouth örneği bulunabilirse specific test yapılabilir

## TEKNIK NOTLAR

### API Response Yapısı
- `predicted_score`: Analysis context'ten gelir
- `home_xg`/`away_xg`: Calibrated prediction'dan gelir
- Frontend: Bu alanları doğrudan render eder
- Alan adı mapping sorunu yok

### Model Güvenilirliği
- Test edilen maçta: Consistent sonuç
- Ensemble model: Tek model fallback'i var
- Calibration: xG değerlerini etkileyebilir ama yön korunur

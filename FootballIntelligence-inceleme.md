# FootballIntelligence — Teknik inceleme

İncelenen kaynak: kullanıcının yüklediği `FootballIntelligence-main.zip`.
Arşiv yorumundaki commit: `bcb8bf66b3ec2b2b05699436b21d7e765f1d41dc`.
İnceleme tarihi: 12 Ekim 2026 UTC.

**Karar:** Projede anlamlı bir modüler temel ve ciddi miktarda uygulama kodu var. Ancak mevcut sürümün tahmin doğruluğu, kalibrasyonu, geçmiş performans ölçümü ve canlı veri tutarlılığı güvenilir kabul edilemez. Öncelik yeni model eklemek değil, mevcut veri–tahmin–kayıt–sonuç zincirini düzeltmek olmalı.

Bu değerlendirme kârlılık veya tahmin başarısı ölçümü değildir. Gerçek veritabanı, çalışan dağıtım ve dış servis hesapları sağlanmadığı için bunlar doğrulanmadı. Projenin uygulama kaynakları değiştirilmedi.

## Kapsam ve kanıt düzeyi

Backend uygulama envanterinde 141 Python dosyası, `backend/tests` altında `test*.py` deseninde 93 dosya bulunuyor. Backend ağacındaki 382 Python dosyası AST ile sözdizimi açısından kontrol edildi; sözdizimi hatası bulunmadı. Bu, testlerin geçtiği veya uygulamanın çalıştığı anlamına gelmez.

Mimari, API bağlantıları, provider akışları, feature çıkarımı, model birleştirme, kalibrasyon, backtest, sonuç değerlendirme, veritabanı modelleri/migration'lar ve frontend veri erişiminin kritik bölümleri incelendi. Bütün dosyaların her satırının eksiksiz denetlendiği iddia edilmiyor.

Bağımlılık kurulumu sınırları:

- `pip install --target ... -r requirements.txt` ortamda `fastapi==0.109.0` paketine erişemedi. Bu sonuç paketin gerçekte mevcut olmadığını göstermez.
- `npm ci --offline --ignore-scripts --no-audit --no-fund` gerekli npm paketleri önbellekte bulunmadığı için `ENOTCACHED` ile durdu.
- Dolayısıyla tam pytest, frontend build/lint, API entegrasyonu ve PostgreSQL migration testleri çalıştırılamadı. Depodaki eski test raporları güncel doğrulama yerine kullanılmadı.
- Uygulamanın başlangıç import'larından bağımsız yüklenebilen gerçek sınıflar ve kaynak dosyalarından alınan gerçek yöntemler üzerinde hedefli Python kontrolleri çalıştırıldı. Veritabanı sıralaması ayrıca eşdeğer SQLite sorgusuyla gösterildi. Bunlar uçtan uca test değildir.

Önem düzeyleri: **P1** doğruluğu veya temel akışı bozan yüksek öncelik; **P2** işlev, güvenilirlik veya işletim sorunu; **P3** bakım/teslim eksikliği. Gerçek üretim ortamında istismar veya veri kaybı yaşandığı iddia edilmemektedir.

## Bulgular

### 1. P1 — Son maçlar yerine en eski maçlar kullanılıyor

**Kaynak:** `backend/app/database/repository.py`, satır 303, `get_team_matches_before_date`; `backend/app/features/aggregator.py`, satır 114 ve 121; `backend/app/features/match_features.py`, `_load_historical_matches_from_db`.

Sorgu önce `scheduled_at.asc()` ile sıralıyor, sonra `limit` uyguluyor. Aggregator 20 maç istediğinde takımın son 20 maçı yerine başlangıçtaki 20 maç geliyor. Diğer feature yolu da aynı repository üzerinden 100 maçla sınırlandırılıyor. Daha sonra bu listeyi yeniden sıralamak dışarıda kalan güncel maçları geri getirmez.

**Doğrulama:** Tarih sırası 1–30 olan bir takım için limit 20 sorgusu 1–20 kayıtlarını döndürdü. Bu kümeden alınan son beş maç 16–20 oldu; olması gereken 26–30.

**Etki:** Güncel form, gol ortalamaları ve takım gücü eski sezonlara dayanabilir. Daha çok tarihsel veri yüklemek hatayı büyütebilir.

**Düzeltme:** Önce azalan tarihle en yeni N kaydı seç, gerekliyse seçilmiş alt kümeyi kronolojik sıraya çevir. Sınırdan fazla geçmiş maç içeren regresyon testi ekle.

### 2. P1 — Kalibrasyon gerçek model çıktılarıyla eğitilmiyor

**Kaynak:** `backend/scripts/train_calibration.py`, satır 128, 136 ve 283.

`simulate_historical_predictions` sabit 0.43/0.28/0.29 başlangıç olasılıklarına `random.gauss` ile gürültü ekliyor. Üretimdeki tahmin motorunu veya takımların feature'larını çalıştırmıyor. Ardından bu sayılar gerçek maç sonuçlarıyla eşleştirilip üretim kalibrasyonu için kaydediliyor.

**Doğrulama:** Aynı maç ID'sini koruyup iki takımın kimliğini ve sonucu tamamen değiştirdiğimde tahmin olasılıkları değişmedi. Bu, gerçek takım modelinin kalibrasyonu değildir.

`random.seed(hash(match['id']))` ayrıca süreçler arası yeniden üretilebilirliği garanti etmez; Python string hash'i süreçler arasında değişebilir. Kontrolü ayrı süreçte tekrarlayınca aynı ID için farklı sayılar görüldü.

**Etki:** Bu betiğin ürettiği kalibrasyon, asıl modelin hatalarını öğrenmez. Dosyanın yüklenmesini düzeltmek tek başına çözüm değildir; yanlış eğitim ürününü etkinleştirebilir. ZIP'teki pickle güvenlik nedeniyle açılmadı; onun hangi çalıştırmadan üretildiği doğrulanmadı.

**Düzeltme:** Kronolojik olarak, her maçtan önce gerçekten mevcut bilgilerle üretilmiş model/ensemble olasılıklarını kaydet. Kalibrasyonu bu out-of-sample tahmin–sonuç çiftleriyle eğit, ayrı ileri zaman diliminde Brier/log loss karşılaştırması yap. Demo kalibrasyonunu üretimden ayır.

### 3. P1 — Kalibrasyon dosyasının yolu yanlış; temiz kurulumda eğitim bağımlılığı da eksik

**Kaynak:** `backend/app/prediction/calibration_loader.py`, satır 30 ve 64; `backend/config/calibration_config.json`; `backend/requirements.txt`; `backend/app/prediction/calibration_engine.py`, sklearn import bölümü.

Yükleyici `__file__` üzerinden iki üst dizine çıkarak `backend/app` dizinini buluyor; konfigürasyon ise `backend/config` altında. Dolayısıyla varsayılan yol `backend/app/config/calibration_config.json` oluyor ve bulunamıyor. Mevcut JSON ayrıca geliştiricinin `C:\FootballIntelligence\...` mutlak pickle yolunu içeriyor.

**Doğrulama:** Hesaplanan varsayılan dosya yok; arşivdeki gerçek dosya var. Servis bu durumda eğitilmemiş kalibratöre düşüyor.

Kalibrasyon motoru sklearn kullanıyor, ancak `requirements.txt` içinde scikit-learn yok. Kod bu bağımlılık bulunmadığında kalibrasyonsuz çalışmayı seçiyor. Lojistik modelin yükleyicisindeki çalışma dizinine bağlı `backend/app/config/logistic_model.pkl` yolu da taşınabilirlik açısından ayrıca düzeltilmeli.

**Düzeltme:** Model dizinini tek, açık bir konfigürasyondan yönet; yolları bulunduğu dosyaya göre çöz; gereken eğitim bağımlılıklarını tanımla. API'de modelin gerçekten yüklenip yüklenmediğini ve kalibrasyon durumunu göster.

### 4. P1 — Kalibre edilmiş 1X2 ile piyasa olasılıkları aynı dağılıma dayanmıyor

**Kaynak:** `backend/app/prediction/model_orchestrator.py`, `CalibrationIntegration.calibrate_prediction`, satır 571; `backend/app/prediction/service.py`, satır 1246 ve piyasa türetme akışı.

Kalibrasyon home/draw/away olasılıklarını değiştiriyor fakat `score_distribution` değerini aynen taşıyor. Piyasa motoru daha sonra eski skor dağılımından 1X2 ve diğer piyasaları tekrar hesaplıyor.

**Doğrulama:** Gerçek integration sınıfına kontrollü bir kalibratör verildi. Girişte ev sahibi 0.50, kalibrasyon sonrasında 0.70 oldu; piyasa motoru aynı çıktıdan hâlâ 0.50 hesapladı. Bunlar gerçek maç değerleri değil, çelişkiyi gösteren test girdileridir.

**Etki:** Ana kart, seçim kartı, adil oran ve piyasa karşılaştırması birbirini tutmayabilir. Kalibrasyon yükleme hatası giderildikten sonra bu ikinci hata görünür hâle gelir.

**Düzeltme:** Kalibrasyon ile skor dağılımını tutarlı bir yöntemle uzlaştır veya farklı olasılık ürünlerini açıkça ayır. Aynı piyasaya ait bütün sunumların tek kaynaktan geldiğini kontrol et.

### 5. P1 — Ensemble'a eklenen modeller beklenmedik şekilde baskınlaşıyor

**Kaynak:** `backend/app/prediction/ensemble_engine.py`, satır 66; `backend/app/prediction/ensemble_optimizer.py`; `backend/app/prediction/model_orchestrator.py`, varsayılan registry.

“Optimize” ağırlık tablosu dört model için toplam 1.0 veriyor. `StaticWeights` tabloda olmayan her modele 1.0 atıyor. Registry ise Elo ve Monte Carlo'yu da çalıştırıyor; uygun veride bunlar ensemble'a katılabiliyor.

**Doğrulama:** Dört yapılandırılmış model + Elo + Monte Carlo birlikte başarılı olduğunda normalize ağırlıklar: Poisson %8.33, Dixon–Coles %10, Negative Binomial %8.33, Form %6.67, Elo %33.33, Monte Carlo %33.33.

**Etki:** Belgelenen %25/%30/%25/%20 dağılımı uygulanmıyor. Ağırlığı tanımlanmamış iki model toplam etkinin üçte ikisini alabiliyor. Bu senaryo her maçta altı modelin başarılı olduğu iddiası değildir.

**Düzeltme:** Bilinmeyen modelin ağırlığını açıkça belirle veya onu dışla; yeni model eklenince sessizce 1.0 verme. Ağırlıkları kronolojik doğrulama ile seç. Monte Carlo varsayılanında `seed=None` kullanımı nedeniyle aynı girdinin yeniden hesaplanmasında değişkenlik olduğunu da ele al.

### 6. P1 — API'nin döndürdüğü tahmin sürümü kalıcı saklanmıyor

**Kaynak:** `backend/app/prediction/service.py`, satır 148; `backend/app/api/v1/endpoints/matches.py`, her istekte `PredictionService` oluşturulması; `backend/app/prediction/prediction_version.py`.

Servis, veritabanı session'ı verilse bile `PredictionVersionManager(persistence_service=None)` oluşturuyor. Sürümler isteğe özel nesnenin belleğinde tutuluyor. Yeni istekte yeni bir boş manager oluşuyor.

**Doğrulama:** Bir manager'da oluşturulan maç/aşama sürümü ikinci manager'da bulunamadı.

**Etki:** Kullanıcıya döndürülen version ID kalıcı denetim izi sağlamıyor. Maç öncesi önerinin ne olduğunu daha sonra kanıtlayamaz; settlement ve başarı geçmişi bu API yolundan beslenmez.

Ek olarak `PredictionVersionDB` modelinde maç+aşama için normal index var, unique constraint yok; ilgili migration da bunu sağlamıyor. Manager'ın yorumlarında istenen eşzamanlı yazma güvencesi veritabanında uygulanmıyor.

**Düzeltme:** Var olan persistence service'i bağla. Tahmin aşaması ve canlı güncelleme sürümleri için doğru idempotency anahtarını tasarla; uygun unique constraint ekle. Bir istekte oluşturulan kaydın başka istekte ve süreç yeniden başladığında bulunmasını doğrula.

### 7. P1 — Tam pipeline walk-forward yolu çalışma zamanında kırılıyor

**Kaynak:** `backend/app/prediction/walk_forward.py`, satır 424, 532 ve 558; `backend/app/prediction/feature_snapshot.py`.

`_build_snapshot` mevcut dataclass'ta olmayan `data_quality_score`, `team_strength` ve `form_metrics` gibi parametrelerle nesne oluşturuyor.

**Doğrulama:** Kaynaktaki gerçek yöntemi çağırınca `TypeError: MatchFeatureSnapshot.__init__() got an unexpected keyword argument 'data_quality_score'` oluştu.

Aynı akışta `EnsembleEngine()` gerekli strategy verilmeden kuruluyor ve sınıfta olmayan `combine_predictions` yöntemi çağrılıyor. `_fit_calibration` eğitim yapmadan yeni motor döndürüyor. `_evaluate_match` istisnaları sessizce `None` sonucuna çeviriyor.

**Etki:** Yeterli veri olsa bile bu pipeline değerlendirmesi boş sonuçlara dönüşebilir. Sorunu yalnızca “veri yetersizliği” olarak teşhis etmek yanlış olur. Bu bulgu ayrı `backtest.py` içindeki bütün temel model testlerinin bozuk olduğu anlamına gelmez.

**Düzeltme:** Canlı tahminle aynı çalışan pipeline'ı tarih sınırı enjekte ederek kullan; kontratları düzelt. Hatalı maç, veri yetersizliği ve bilinçli PASS ayrı sayılmalı. Bilinen küçük bir fixture setinden sıfırdan büyük değerlendirme kaydı bekleyen entegrasyon testi ekle. Varsayılan test pencereleri örtüştüğü için aynı maçın toplam metriklere kaç defa girdiğini de açıkça yönet.

### 8. P1 — KG Var seçimleri ters sonuçlandırılabiliyor

**Kaynak:** `backend/app/prediction/market_selector.py`, satır 388; `backend/app/prediction/settlement.py`, satır 164.

Selector `BTTS_YES` için `Both Teams to Score` metni üretiyor. Settlement ise metinde `YES` arıyor veya metnin tam `BTTS` olmasını bekliyor. Gerçek selector metni bu kontrole uymadığı için KG Yok gibi yorumlanıyor.

**Doğrulama:** Gerçek `_settle_btts` yöntemi `Both Teams to Score` seçimini 1–1 sonucunda LOSS, 1–0 sonucunda WIN saydı.

**Etki:** Settlement bu seçimlere bağlandığında başarı oranı ve kâr/zarar ters hesaplanır. Şu an API persistence bağlantısının eksik olması bu hatayı görünmez kılabilir.

**Düzeltme:** Sonucu gösterim metninden değil `BTTS_YES`/`BTTS_NO` gibi kanonik market/selection kimliğinden hesapla. Selector çıktısını doğrudan settlement'a veren test ekle. Selector'ın üretebildiği takım golü ve şut piyasaları için de destek sözleşmesini tamamla; desteklenmeyenleri sessizce değerlendirme.

### 9. P1 — Canlı maç kopyalanırken dakika ve devre verileri kayboluyor

**Kaynak:** `backend/app/providers/hybrid_provider.py`, satır 928; `get_match` içindeki `_update_single_match_status` çağrıları.

Yeni Match nesnesi elle kurulurken `minute`, `added_time`, `home_score_ht`, `away_score_ht` gibi alanlar taşınmıyor. Bu yöntem hem dış kaynaktan hem veritabanından gelen tek maç sonucuna uygulanıyor.

**Doğrulama:** 70. dakika, +2 uzatma, devre 1–0 içeren canlı Match; yöntemden sonra dakika, uzatma ve devre alanlarında `None` taşıdı. Ana skor korundu.

**Etki:** Provider doğru veri getirse de ayrıntı ekranında dakika/devre bilgileri kaybolabilir.

**Düzeltme:** Domain nesnesini alan kaybetmeden kopyala; yalnızca gerçekten doğrulanmış alanı güncelle. API'ye kadar dakika/devre alanlarını izleyen test ekle.

### 10. P2 — Durum ve tazelik politikası birbirini tutmuyor

**Kaynak:** `backend/app/providers/hybrid_provider.py`, satır 399 ve 960; `_should_refresh_from_external`; `backend/app/api/v1/endpoints/matches.py`, async listeleme.

Aktif async listeleme yolu status filtresiyle veritabanında kayıt bulursa bunları tazelik kontrolü yapmadan kullanıyor. Sync yolunda bulunan refresh politikası burada uygulanmıyor. Dolayısıyla eski SCHEDULED/LIVE kayıtlar dış kaynakla uzlaştırılmayabilir.

Ayrıca tek maç yolunda maç saati üzerinden üç saat geçmesi SCHEDULED kaydını FINISHED yapmaya yetiyor. Erteleme, iptal veya geç başlama bilgisi olmadan bu sonuca varılamaz.

**Etki:** Liste ve detay farklı durum gösterebilir; güncelliği bilinmeyen maç tamamlanmış gibi görünebilir.

**Düzeltme:** Tek bir tazelik politikası uygula. Süreyi, sonucu belirlemek için değil yeniden kontrol tetiklemek için kullan. Doğrulanamayan veriyi stale/unknown olarak işaretle.

### 11. P1 — Oran endpoint'i veri bulunduğunda olmayan alanları okuyor

**Kaynak:** `backend/app/routers/odds.py`, satır 117 ve 142; `backend/app/database/models.py`, `AverageMarketOdds`, satır 576.

Endpoint `AverageMarketOdds` kayıtlarından `home_team_name`, `away_team_name` ve `commence_time` okuyor. Bu üç alan bu modelde yok; ilgili bilgiler `BookmakerOdds`/Match tarafında bulunuyor.

**Doğrulama:** ORM sınıfının kaynak alanlarıyla endpoint erişimleri karşılaştırıldı; üç alan da eksik. HTTP sunucusu çalıştırılmadı.

**Etki:** Boş veritabanında düzgün `match_found=false` dönen endpoint, gerçek oran kaydı geldiğinde AttributeError ile 500'e dönüşür.

**Düzeltme:** Event/Match bilgilerini açık join veya ilişki üzerinden al. Testte yalnızca boş sonuç değil, gerçek h2h ve totals kaydı bulunan durumu da kullan.

### 12. P2 — İlk oran yüklemesinde ortalamalar henüz yazılmamış kayıtlardan hesaplanıyor

**Kaynak:** `backend/app/database/session.py`, `autoflush=False`; `backend/app/services/odds_updater_service.py`, satır 203 ve 207.

Yeni BookmakerOdds kayıtları session'a ekleniyor; flush/commit olmadan `_calculate_and_store_averages` veritabanını sorguluyor. Ana commit tüm event işlemlerinin sonunda.

**Etki:** SessionLocal kullanılan ilk yüklemede yeni kayıtlar ortalama sorgusuna yansımayabilir; bookmaker verisi yazıldığı hâlde ortalama sonuçları boş kalır. Varsayılan autoflush=True test session'ı bu üretim farkını gizleyebilir.

**Düzeltme:** Ortalamadan önce kontrollü flush yap veya aynı event'in doğrulanmış girdilerinden hesapla. İlk yüklemeyi üretimdeki session ayarlarıyla test et.

### 13. P2 — Gerçek oranlar tahmin seçim motoruna bağlanmamış

**Kaynak:** `backend/app/api/v1/endpoints/matches.py`, satır 661.

Tahmin servisine her zaman `odds_data=None` gönderiliyor. Oran tablosu ve ayrı endpoint olsa bile bu yol oranları okuyup market selector'a iletmiyor.

**Etki:** API tahminleri gerçek oran üzerinden edge/value/EV değerlendirmesi yapamaz. Arayüzün başka bir çağrıyla oran göstermesi, seçim motorunun o oranı kullandığını göstermez.

**Düzeltme:** Maç ve piyasa kimlikleri doğrulanmış, zaman damgalı oranları pipeline'a bağla. Tarihsel incelemelerde tahmin anından sonraki oranı kullanma; oran yoksa NO_ODDS olarak açıkça sun.

### 14. P2 — Senkron tahmin işi async endpoint'i blokluyor; timeout gerçekte sınır koymuyor

**Kaynak:** `backend/app/api/v1/endpoints/matches.py`, satır 659; `backend/app/providers/adapter.py`, `_exec`; `backend/app/prediction/service.py`, satır 579; `backend/app/features/match_features.py`, provider fallback.

Async endpoint senkron tahmin/veritabanı/provider işini doğrudan çağırıyor. Adapter farklı thread'de coroutine çalıştırsa da sonuç için senkron bekliyor; event loop yine bloklanıyor.

`with ThreadPoolExecutor()` içindeki `future.result(timeout=...)` aşımı da toplam süreyi sınırlamıyor. Context manager çıkışta çalışan thread'i bekliyor.

**Doğrulama:** Aynı executor örüntüsünde 10 ms timeout, 200 ms süren işin tamamlanmasını bekledi; ölçülen toplam süre yaklaşık 202–203 ms. Bu gerçek API latency ölçümü değil, kullanılan timeout örüntüsünün kontrolüdür.

**Etki:** Yavaş provider bir worker'daki diğer istekleri de geciktirebilir. Frontend'in 20 saniyelik prediction timeout'u backend çalışmasını otomatik iptal etmez.

**Düzeltme:** I/O için gerçek async akış veya bütün senkron iş biriminin uygun worker'a taşınması; CPU işi için gerekirse ayrı süreç/iş kuyruğu. Session'ı iş birimi içinde oluştur. HTTP istemcisinin gerçek deadline/cancellation davranışını kullan.

### 15. P2 — Provider cache her istekte yeniden oluşturuluyor; sayfalama veritabanına inmiyor

**Kaynak:** `backend/app/api/dependencies.py`, satır 52; `backend/app/api/v1/endpoints/live_matches.py`, `ProviderCache()`; `backend/app/api/v1/endpoints/matches.py`, satır 211.

Provider cache ve manager istek içinde kuruluyor; cache bir sonraki isteğe taşınmıyor. Liste endpoint'i limit/offset'i provider sorgusuna göndermiyor, bütün sonucu aldıktan sonra Python'da dilimliyor.

**Etki:** Aynı canlı veri için tekrarlayan dış API çağrıları; geniş tarih aralıklarında gereksiz veri yükleme ve bellek maliyeti. Sonradan takım sorgusunu sayfaya sınırlamak ilk büyük sorguyu çözmez.

**Düzeltme:** Uygulama ömrüne bağlı paylaşılan cache veya uygun ortak cache kullan. Provider yaşam döngüsünü merkezi yönet, veritabanı sayfalamasını sorguya taşı; toplam sayıyı ayrı hesapla.

### 16. P1 — Güvenilirlik kontrollerinden biri yanlış alanı okuyor; hata durumunda uydurma güven atanıyor

**Kaynak:** `backend/app/prediction/service.py`, satır 128, 994 ve 1228; `backend/app/prediction/feature_snapshot.py`, `MatchFeatureSnapshot`.

Minimum örnek kontrolü `snapshot.data_quality` alanını arıyor; gerçek snapshot'ta `data_quality_report` var. `hasattr` false olduğu için bu kontrol atlanıyor. İçerideki `self.config.min_sample_size` referansı için PredictionService içinde `self.config` kurulumu da bulunmuyor. Ayrı quality gate rapor üretiyor; bu raporun kritik başarısızlıkları burada açık bir durdurma koşuluna bağlanmıyor.

Feature extractor'ın min_matches değeri 1'e indirilmiş. Confidence bölümünde hata olursa overall ve bileşenler 0.5'e ayarlanıp pipeline devam ediyor.

**Etki:** Kodun iddia ettiği minimum örnek kapısı bu yolda çalışmıyor. Diğer modellerin/güven kontrollerinin bazı maçları reddedebileceği saklı kalmak üzere, hesaplanamayan güvenin “orta güven” gibi sunulması yanıltıcıdır.

**Düzeltme:** Tek minimum örnek politikası; gerçek rapor alanlarını kontrol et. Kritik veri/güven hatasında hesaplanmamış sonucu sayıya çevirmek yerine açıklamalı PASS/unavailable dön.

### 17. P1 — Yönetim amaçlı oran güncelleme endpoint'inde yetkilendirme yok

**Kaynak:** `backend/app/routers/odds.py`, satır 259; `backend/app/main.py` ve API router bağlantıları.

`POST /api/v1/odds/manual-update` veri yazan ve dış servisi çağırabilen bir işlem; yalnızca DB dependency'si var. Kodda bu rota için kimlik/rol denetimi veya hız sınırı görünmüyor.

**Etki:** API dışarıya açılır ve ayrıca korunmazsa istenmeyen kişiler bu işi tetikleyebilir. Provider cache/quota kontrolleri riski azaltabilir fakat kullanıcı yetkisi yerine geçmez. Üretimde ek gateway koruması olup olmadığı incelenmedi.

**Düzeltme:** Admin yetkisi, hız sınırı, aynı anda tek güncelleme ve görev kaydı ekle. CORS'u yetkilendirme olarak kullanma. İstemciye ham exception ayrıntısı dönme.

### 18. P2 — React StrictMode'da tahmin yüklemesi iptalden sonra yeniden başlamayabilir

**Kaynak:** `frontend/src/hooks/useLazyPrediction.ts`, satır 33 ve 105; `frontend/src/main.tsx`.

İlk effect isteği başlatıp shared cache'i loading yapıyor. StrictMode cleanup isteği abort ediyor. İkinci effect abort'un async temizliği bitmeden çalışırsa `cache.isLoading(matchId)` nedeniyle geri dönüyor. Sonradan cache temizlense de effect yalnızca matchId'ye bağlı; yeniden çalışmıyor.

**Etki:** Geliştirme sırasında bazı kartlar tahmin veya hata göstermeden boş kalabilir. Benzer durum, ortak isteğin sahibi unmount olurken diğer tüketicinin beklemesinde de oluşabilir. Bu bulgu effect yaşam döngüsü üzerinden statik olarak doğrulandı; React runtime testi bu ortamda çalıştırılamadı.

Mevcut hook testinin yeni provider ile unmount/remount yapması, aynı provider içindeki StrictMode çift effect senaryosunu birebir doğrulamıyor.

**Düzeltme:** İstek sahipliğini merkezi cache'te tut; tüketici unmount'unun ortak isteği körlemesine iptal etmesini önle. Aynı provider altında StrictMode testi ve retry durum makinesi ekle.

### 19. P2 — Oran hook'ları merkezi API adresini kullanmıyor; refetch çalışmıyor

**Kaynak:** `frontend/src/hooks/useOdds.ts`, satır 64 ve 84; `frontend/src/api/client.ts`, `getApiBaseUrl`; `frontend/vite.config.ts`.

Ana API client VITE_API_BASE_URL/Capacitor yönlendirmesi kullanırken oran hook'ları doğrudan `/api/v1/odds/...` çağırıyor. Ayrı frontend/backend origin veya native uygulamada bunlar farklı sunucuya gidebilir. Geliştirme proxy'si backend için 8003 kullanırken ana client varsayılanı 8000; tek yapılandırma yok.

`useMatchOdds` içindeki refetch yalnızca `setOdds(null)` çağırıyor. Effect sadece matchId'ye bağlı olduğu için yeni HTTP isteği başlatmıyor.

**Düzeltme:** Bütün veri erişimini aynı client'a taşı; refetch gerçek fetch fonksiyonunu çağırmalı. Hızlı maç değişiminde eski yanıtın yeni maça yazılmasını engelleyen abort/istek kimliği de ekle.

### 20. P2 — İstatistiklerin anlamı ve eksik veri hesapları bozulabiliyor

**Kaynak:** `frontend/src/api/client.ts`, satır 364; `backend/app/features/attack_defence.py`, satır 104, 130 ve ortalama hesapları.

Frontend `shots_off_target` değerini `shotsOutsideBox` alanına yazıyor. İsabetsiz şut ile ceza sahası dışından atılan şut aynı istatistik değildir.

Backend xGA hesabı rakibin maç xG'sini topladıktan sonra aynı maçın `stat.xg_against` değerini de ekleyebiliyor. Her iki kaynak varsa aynı veri iki kez sayılır. xGA ortalaması ayrıca kendi doluluk sayacı yerine xG sayacına bölünüyor. İsabetli şut ortalaması da total-shot doluluk sayacını kullanıyor; alanlar farklı sayıda maçta doluysa eksik değerler ortalamayı aşağı çekebilir.

**Etki:** Sayılar matematiksel olarak hesaplanmış olsa bile yanlış anlamı veya yanlış paydayı temsil eder.

**Düzeltme:** Her istatistiğin anlamını, kaynak önceliğini ve kendi geçerli örnek sayısını tanımla. İki kaynak dolu ve yalnız bir kaynak dolu fixture'larını test et; bilinmeyen alanı başka alanla doldurma.

### 21. P2 — Ürün kapsamının bazı parçaları henüz uçtan uca bağlanmamış

**Kaynak:** `frontend/src/api/client.ts`, satır 383 ve 401; `frontend/src/components/track-record/PerformanceOverview.tsx`; `frontend/src/pages/Analytics.tsx`; `frontend/src/pages/Settings.tsx`; `frontend/src/App.tsx`; `backend/app/api/v1/__init__.py`; `backend/app/ai/analyst.py`.

Live events/shots/markets helper'ları boş liste, live prediction helper'ı null döndürüyor. Performans ekranı açıkça boş durum iskeleti. Analytics ve Settings placeholder düzeyinde. AI analyst ve Ollama kodu var, ancak mevcut API router'larında bunları kullandıran bir endpoint bulunmuyor; AI analist sayfası da mevcut route listesine bağlı değil.

Bu açıkça etiketlenmiş boş durumlar sahte veri değildir; doğru olan eksikliği göstermeleri. Sorun, sınıf veya component varlığının tamamlanmış ürün özelliği gibi sayılmasıdır. Canlı skor listesi bulunması, canlı olasılık güncelleme motorunun entegre olduğu anlamına gelmez.

**Düzeltme:** README ve roadmap'te çalışan uçtan uca akışları ayrı belirt. Özellikleri küçük dikey akışlarla tamamla. AI çıktısını yalnız prompt talimatıyla güvence altına alma; sayısal iddiaları yapılandırılmış referanslarla doğrula.

### 22. P3 — Tekrarlanabilir teslim ve entegrasyon testleri eksik

**Kaynak:** `README.md`; `backend/requirements.txt`; `frontend/package.json`; `frontend/capacitor.config.ts`; `backend/tests/test_settlement.py`; `frontend/src/hooks/useLazyPrediction.test.tsx`.

README hâlâ Phase 1 durumunu anlatırken kod çok daha ileri parçalar içeriyor. Ana kurulum akışında veritabanı migration ve başlangıç veri yüklemesi adımları yeterince açık değil. Android sync komutları/config mevcut, fakat package.json'da Capacitor CLI ve Android bağımlılıkları tanımlı değil; temiz checkout için deterministik Android build yolu eksik.

Test sayısı yüksek olmasına rağmen gerçek producer–consumer sözleşmeleri kaçmış: selector'ın ürettiği BTTS metni settlement testine gitmiyor; dolu oran kaydı endpoint'i doğrulanmıyor; güncel form için N'den fazla geçmiş kayıt kritik; gerçek StrictMode senaryosu ayrı test edilmeli. Depoda test/analiz çıktısı ve geçici inceleme dosyalarının yoğunluğu da hangi kanıtın güncel olduğunu belirsizleştiriyor.

**Düzeltme:** Temiz ortamda backend testleri, frontend type-check/build ve migration çalıştıran CI ekle. Gerçek entegrasyon sınırlarını test et. Kurulumu tek komut dizisiyle belgele. Bağımlılıkların güncel güvenlik taramasını ayrıca yap; bu incelemede bir CVE taraması yapılmadı ve belirli açık var/yok sonucu çıkarılmadı.

## Çalıştırılan hedefli kontrollerin özeti

| Kontrol | Gözlenen sonuç | Sınır |
|---|---|---|
| Backend Python sözdizimi | 382 dosya; hata yok | Import, çalıştırma veya pytest değildir |
| Tarih sıralaması | Son 20 yerine ilk 20 | Eşdeğer SQLite sorgusu |
| Kalibrasyon eğitim girdisi | Takımları değiştirince olasılık değişmedi | Betiğin gerçek fonksiyonu, kontrollü maçlar |
| Kalibrasyon dosya yolu | Varsayılan yol yok, gerçek dosya başka dizinde | Dosya konumu kontrolü; pickle açılmadı |
| Kalibrasyon/piyasa tutarlılığı | 0.70 ve 0.50 farklı sonuç | Gerçek integration + kontrollü kalibratör |
| Ensemble ağırlıkları | Elo ve MC ayrı ayrı %33.33 | Altı başarılı model senaryosu |
| BTTS settlement | KG Var: 1–1 LOSS; 1–0 WIN | Gerçek settlement yöntemi |
| Canlı Match kopyası | 70. dakika ve devre alanları None | Gerçek kopyalama yöntemi/domain nesnesi |
| Tahmin history | Yeni manager önceki kaydı bulamadı | API'nin kullandığı bellekte saklama modu |
| Walk-forward snapshot | Beklenmeyen keyword nedeniyle TypeError | Gerçek yöntemin izole çağrısı |
| Oran model/endpoint sözleşmesi | Üç istenen alan modelde yok | AST/kaynak karşılaştırması, HTTP testi değil |
| Executor timeout | 10 ms sınırda yaklaşık 202–203 ms bekleme | Uygulamadaki aynı örüntünün küçük deneyi |

## Düzeltme sırası ve kabul ölçütleri

1. **Veri doğruluğu:** Son N maç sorgusu, canlı alan kaybı, durum/tazelik ve istatistik anlamları. Kabul: elle hesaplanabilen fixture'larla beklenen alanlar ve ortalamalar birebir tutmalı.
2. **Tahmin tutarlılığı:** Rastgele kalibrasyonu üretimden ayır, model yollarını/ağırlıklarını düzelt, bütün piyasalarda aynı olasılık kaynağını kullan. Kabul: aynı maçın ana olasılığı, market olasılığı ve adil oranı tutarlı olmalı; kritik veri eksikliğinde PASS dönmeli.
3. **Kalıcı kanıt:** Tahmin sürümlerini veritabanına yaz, kanonik seçimlerle settlement yap. Kabul: maç öncesi kaydı başka süreçten tekrar oku; maç sonucu geldiğinde özgün seçim değişmeden doğru WIN/LOSS hesapla.
4. **Gerçek değerlendirme:** Walk-forward'u çalışan pipeline'a bağla. Kabul: kronolojik fixture setinde beklenen sayıda kayıt, görünür hata sayacı, ileri zaman diliminde baseline karşılaştırması. Sadece isabet oranı değil Brier/log loss, coverage ve örnek sayısı raporla.
5. **Oran ve API entegrasyonu:** Dolu oran endpoint'i, ilk ingest ortalamaları, predictor'a zamanlı oran geçişi, merkezi frontend client. Kabul: taze checkout'ta sahte servis fixture'ından kayda ve ekrana kadar tek akış.
6. **İşletim ve güvenlik:** Yetkilendirme, cache ömrü, bloklamayan istekler, gerçek timeout, StrictMode/retry, CI. Kabul: yavaş bir provider temel API yanıtlarını durdurmamalı; yetkisiz güncelleme reddedilmeli.

Projenin güçlü tarafları FastAPI/React katman ayrımı, provider soyutlamaları, kanonik feature snapshot yaklaşımı, olasılık doğrulama yapıları ve çeşitli testlerin bulunması. Bunları koruyup bağlantı hatalarını düzeltmek mantıklı. Şu aşamada model sayısını artırmak, ölçüm ve veri sorunları çözülmeden tahmin kalitesini kanıtlamaz.

# 2026-10-15 — Bahis oranı kaynakları (odds sources)

Amaç: tahmin ettiğimiz maçlar (10 büyük lig + Şampiyonlar / Avrupa / Konferans Ligi, FotMob lig no: 47, 87, 55, 54, 53, 57, 61, 40, 71, 122, 42, 73, 10216) için
bahis şirketi oranlarını yasal ve pratik yoldan almak: maç öncesi (ve mümkünse kapanış) 1X2, çifte şans, alt/üst 1,5 / 2,5 / 3,5, karşılıklı gol (KG), ve mümkünse İddaa oranları.
Bu rapor yalnızca **oran kaynaklarını** inceler; genel doğruluk yol haritası için bkz. `docs/research/2026-10-15-accuracy-roadmap.md` (oranların değeri orada, tekrar edilmedi).

Tüm bulgular 2026-10-15 tarihli ve bu bilgisayardan (Türkiye ağı) ölçüldü. `samples/` = `backend/data/research/odds_samples/` (ham örnekler, git'e girmez). `[D]` = resmi sayfa/doküman okundu, `[V]` = sadece satıcı blogu / karşılaştırma sitesi / arama özeti
(doğrulanmadı), `[T]` = bu makineden gerçek istekle denendi, `[A]` = Internet Archive kopyası (güncel olmayabilir, tarihi yazıldı).

---

## 1. Özet (Türkçe)

**Kısa cevap**

1. **Şu an, kayıtsız kullanabileceğimiz tek kaynak: FotMob'un `matchOdds` adresi.** Anahtar/hesap gerekmiyor, oranlar zaten bizim FotMob maç numaramıza bağlı geliyor (isim eşlemesi gerekmiyor).
   Bugün Salzburg–Milan ve Hoffenheim–Beşiktaş için gerçek oranları çektik; 1X2, çifte şans, alt/üst, KG verileri geliyor (hangi bahis şirketi olduğuna göre eksik marketler var).
   **Ama iki büyük sorun var:** (a) FotMob'un `robots.txt` dosyası `/api/*` yolunu genel istemcilere yasaklıyor ve kullanım şartları ("DATA USAGE & SCRAPING") yazılı izin olmadan otomatik / toplu veri çekmeyi yasaklıyor — yani **izinli değil**,
   şu an kullandığımız `matchDetails` ile aynı gri bölge. Bu yüzden hazırladığım toplayıcı, `--accept-fotmob-terms-risk` bayrağı olmadan çalışmıyor; bu kararı **sahibi** vermeli (ya da FotMob'dan yazılı izin istenmeli).
   (b) **Türkiye için oran dönmüyor** (`TUR` → boş), yani **İddaa oranı yok**; gelen oranlar Almanya (Tipico/Letsbet), Avusturya (Interwetten), İspanya (Bet365/1xBet), İngiltere (Bet365/Betfair/Betfred) gibi ülkelerin şirketlerinden. Aynı ülke için şirket zamana göre değişebiliyor.
2. **Kayıt gerektirenler (sahibi açmalı), en iyiden başlayarak:**
   - **OddsPapi — ücretsiz hesap** (ayda 250 istek; Pinnacle ve Bet365 dahil 350+ şirket iddiası `[V]`). Sitesi ve API adresi bu bilgisayardan açılıyor `[T]`. Bir çalıştırma ≈ 3–4 istek harcar, yani ayda ~60 çalıştırma yeter. Pinnacle gibi "keskin" (sharp) çizgi önemli kazanç demek. **Bilinmeyen:** İddaa gibi Türk şirketleri var mı (herkese açık listede görünmüyor), kapsama ve piyasa adları gerçek denemede doğrulanmalı. Toplayıcı hazır, canlı denenmedi.
   - **Odds-API.io — İddaa'yı listesinde tutan tek servis** (430 şirketin herkese açık listesinde `Iddaa` var, aktif `[T]`). **Ama**: yeni ücretsiz anahtarlar "süresiz durduruldu" (fiyat sayfası, 3 Ekim 2026 kopyası `[A]`); en ucuz ücretli plan **Solo £49/ay (≈ $65)**, 2 bahis şirketi, saatte 5.000 istek, kartla ödemede 7 gün iade garantisi `[D][A]`. İddaa'nın gerçekten hangi marketleri/maçları (Süper Lig, UEFA kupaları) verdiği **anahtar alınmadan doğrulanamıyor**. Ayrıca odds-api.io sitesi/dokümanı bu ağdan açılmıyor (bağlantı sıfırlanıyor), sadece API adresi (`api.odds-api.io`) açılıyor `[T]` — kaydı başka bir ağdan/tarayıcıdan yapmak gerekebilir. Toplayıcı hazır, canlı denenmedi.
   - **The Odds API — önerilmez:** bu ağdan hiç açılmıyor (bağlantı anında sıfırlanıyor, 3 denemede aynı `[T]`; bir erişim engeli, aşmayı önermiyoruz), listesinde İddaa yok, Çekya ligi görünmüyor `[A]`. Ücretsiz plan 500 kredi/ay, ücretli $30/ay (20.000 kredi) `[D][A]`.
   - **API-Football** (yol haritasındaki C1 seçeneği): ücretsiz günde 100 istek, ücretli Pro $19/ay `[V]`. Resmî sayfaları bu istemciye 403 veriyor (aşılmadı), bu yüzden kapsamı/oran markelerini/İddaa'yı **doğrulayamadım**; toplayıcı yazmadım. Anahtar alındığında tek bir `/odds` örnek cevabı ile aynı ortak modülle ~yarım günde eklenebilir.
3. **Resmî İddaa verisi:** kamuya açık, izinli, makine-okunur bir İddaa API'si/lisansı **bulunamadı**. iddaa.com `robots.txt` dosyası genel istemcilere sadece `*/mac-detay/*` yolunu kapatıyor, ama oranlar statik sayfada değil, belgelenmemiş bir uygulama arka ucundan (SPA) geliyor ve üyelik sözleşmesi metni statik sayfadan okunamadı → **dokunmadık**. Nesine `api.*`/`bulten.*` adreslerini, Misli `iddaa-bahis-detay`, Tuttur `mac-detayi` sayfalarını robots ile kapatmış, Mackolik `/api/` yolunu ve yapay zekâ botlarını kapatmış. Eski karar geçerli: İddaa için elle giriş (C3) ya da yazılı izin.
4. **Diğerleri:** Pinnacle'ın herkese açık API'si 23 Temmuz 2025'ten beri kapalı `[D]`. Betfair API adresi bu IP'ye 403 (Cloudflare) veriyor, aşılmadı; gecikmeli anahtar ücretsiz ama Türkiye'den hesap uygunluğu doğrulanamadı `[D][V]`. football-data.co.uk bu ağdan açılmıyor (zaman aşımı); canlı `fixtures.csv` sadece ana yerel ligleri içerir, Avrupa kupaları yok, en yeni arşiv kopyası 30 Temmuz 2026 (bayat), ve kullanım "özel kişiler için, bot/scraper/yapay zekâ ürünleri için değil" `[A]`.

**Tavsiye**

| | Kaynak | Neden |
|---|---|---|
| Şimdi (kayıtsız) | FotMob `matchOdds` — **sahibi riski kabul ederse** | Çalışıyor, maç numarası bizimle aynı, 1X2/ÇŞ/AÜ/KG var. İzinli değil; İddaa yok. |
| Kayıtla (ücretsiz) | **OddsPapi** ücretsiz hesap | Bu ağdan erişilebilir, Pinnacle iddiası, izinli API, ayda 250 istek yeter. İddaa belirsiz. |
| Kayıtla (İddaa için) | **Odds-API.io Solo £49/ay** (7 gün iade) | Listede `Iddaa` var; tek aday. Önce 1 ay/1 hafta deneyip kapsamı doğrulayın. |

**Sahibin yapması gerekenler** (ayrıntı §6): (1) FotMob kararı: bayrağı kabul et / yazılı izin iste / vazgeç. (2) OddsPapi'de ücretsiz hesap aç, anahtarı `ODDSPAPI_API_KEY` ortam değişkenine koy, bir kez `collect_odds_oddspapi.py` çalıştır (ilk çıktıyı birlikte kontrol edelim). (3) İddaa gerçekten şart ise odds-api.io Solo planını dene.
Ben hesap açmadım, anahtar girmedim, şifre yazmadım.

---

## 2. Karşılaştırma tablosu

Kapsam sütunu: 13 hedef lig. `[T]` ile işaretli olanlar bu makinede denendi.

| Kaynak | Hesap/anahtar | Maliyet | Bu PC'den erişim `[T]` | Hedef liglerin kapsamı | İddaa / Türk şirketi | Marketler (1X2, ÇŞ, A/Ü 1,5-2,5-3,5, KG) | Maç öncesi / kapanış | İstek sınırı | Şartlar / robots | Durum |
|---|---|---|---|---|---|---|---|---|---|---|
| **FotMob `matchOdds`** | yok | ücretsiz | evet (200) | FotMob'un tüm maçları; **sadece 2 Avrupa Ligi maçı denendi**, UECL ve yerel ligler denenmedi | **hayır** (`TUR` boş; ayrıca USA, ITA, NLD, BRA boş) | sağlayıcıya bağlı: Tipico/Interwetten 1X2+ÇŞ+A/Ü 2,5+KG; 1xBet İspanya hepsi (1,5/2,5/3,5); Bet365 1X2+KG+DNB+AH (A/Ü ve ÇŞ yok); FR/BE/PT/PL: 1X2+KG+A/Ü | maç öncesi anlık görüntü; geçmiş yok → kapanışı T-30 dk'da yoklayarak yaklaşıklarız | ortak sınırlayıcı 5 istek/sn | **robots `Disallow: /api/*`; ToS: izinsiz otomatik/toplu çekim yasak** | çalışıyor, **izinli değil** |
| **OddsPapi** (ücretsiz hesap) | evet (e-posta) | $0; 250 istek/ay `[V]` | API evet (401), site evet | `/v4/tournaments` ile doğrulanacak (UCL, LaLiga, PL listede örnek) | herkese açık listede görünmüyor; `/v4/bookmakers` ile doğrulanacak | 1X2, ÇŞ (Double Chance), A/Ü, KG, DNB `[D]` (market kimlikleri `/v4/markets`'ten) | maç öncesi + **ücretsiz geçmiş oran** (`/v4/historical-odds` sayılmaz) `[D]` | 250/ay, her uç noktada 1 sn bekleme | veriyi bağımsız ürün olarak satma yasak; tarama/limit aşımı izlenir `[D]` | toplayıcı hazır, **canlı denenmedi** |
| **Odds-API.io** | evet | **ücretsiz yeni anahtar durduruldu** `[A]`; Solo £49/ay ($65), Starter £99, Growth £179, Pro £229 `[A]` | API evet; site/doküman **hayır** (bağlantı sıfırlanıyor) | `events?league=` slug'larıyla doğrulanacak | **`Iddaa` listede, aktif** `[T]` | ML, Totals, Both Teams To Score, Double Chance, Draw No Bet `[D]` | maç öncesi; geçmiş kapanış `/historical/odds` `[D]` | 5.000/saat (ücretli); 10 maç = 1 istek | yeniden satış yok, abonelik kademesi dışına tarama yok; ücretsiz plan "geliştirme/test" `[A]` | toplayıcı hazır, **canlı denenmedi**, ücretli |
| The Odds API | evet | ücretsiz 500 kredi/ay; $30 = 20 bin; $59 = 100 bin; $119 = 5 M `[D]` | **hayır** (bağlantı sıfırlanıyor) | EPL, Bundesliga, La Liga, Serie A, Ligue 1, Eredivisie, Primeira, Belçika, Süper Lig, UCL/UEL/UECL var; **Çekya yok** `[A]` | **yok** | h2h (1X2), totals; KG ve çifte şans sadece olay-bazlı uç nokta (daha çok kredi) `[D]` | maç öncesi; geçmiş 10× kredi | kredi = market × bölge | şartlar sayfası alınamadı | **önerilmez** (erişilemiyor) |
| API-Football | evet | ücretsiz 100 istek/gün; Pro $19/ay `[V]` | API evet (403: anahtar yok), resmî sayfalar 403 | doğrulanamadı | doğrulanamadı | doğrulanamadı | maç öncesi (günde bir güncelleme iddiası `[V]`) | 10/dk `[V]` | doğrulanamadı | **doğrulanamadı**, toplayıcı yok |
| Sportmonks | evet | ücretsiz plan yalnız 2 lig `[V]`; oran eklentisi ücretli `[V]` | API evet (401) | hedef ligler ücretsiz değil | doğrulanamadı | var (ücretli) | maç öncesi; geçmiş oran ≈7 gün `[V]` | — | — | önerilmez |
| TheStatsAPI | evet | **ücretsiz plan yok**; 7 gün deneme; $50/ay `[V]` | API evet (401) | doğrulanamadı | yok (Bet365, Pinnacle, Betfair Exchange, Paddy Power, BetMGM UK) `[D]` | 1X2 + diğerleri; **açılış ve son fiyat** `[D]` | açılış + son görülen | 100 bin istek/ay | football-data.co.uk'un ortağı | ücretli, denenmedi |
| Betfair Exchange | Betfair hesabı | gecikmeli anahtar ücretsiz; canlı anahtar £299 tek sefer + doğrulanmış, fonlu hesap `[D]` | API adresi **403** (Cloudflare engeli, aşılmadı) | — | — | — | — | — | Türkiye'den hesap uygunluğu doğrulanamadı | uygun değil |
| Pinnacle | — | — | — | — | — | — | — | — | **herkese açık API 23.07.2025'ten beri kapalı** `[D]` | yok |
| football-data.co.uk `fixtures.csv` | yok | ücretsiz | **hayır** (zaman aşımı); arşiv kopyası var | yalnız ana yerel ligler, **UEFA kupaları yok** | yok | 1X2, A/Ü 2,5, AH; çok şirket (B365, Pinnacle, Max, Avg) | maç öncesi + kapanış sütunları; **en yeni arşiv kopyası 30.07.2026** | — | "özel kişiler için; bot/scraper/yapay zekâ ürünleri için değil" `[A]` | canlı kaynak olamaz |
| İddaa / Nesine / Misli / Tuttur / Bilyoner / Mackolik | — | — | robots dosyaları okundu | — | **evet ama izin yok** | — | — | — | herkese açık izinli API yok; robots/ToS (aşağıda) | **dokunulmadı** |

---

## 3. Ayrıntılar

### 3.1 FotMob

**Kontrol edilen yerler** (`https://www.fotmob.com/api/data/...`, UA: `Mozilla/5.0 (TUTAR X research collector; low-rate)`, `fotmob_rate.acquire()` ile):

* `matchDetails?matchId=6112353` içinde **gerçek oran yok.** `content.matchFacts.poll.oddspoll` bir *taraftar anketi*: 4 başlık (`1x2`, `bts`, `ou`, `dc`) altında sadece "son 5 maçta 1G 0B 4M" gibi form cümleleri var (örnek: `samples/fotmob_matchDetails_6112353_full.json`). `matchInsightsConfig.urlTemplate` (`https://data.fotmob.com/generated-match-insights/73/6112353/matchinsights_en.json`) sadece metin içgörüsü veriyor (`bettingInsight`: "Beşiktaş won seven of eight European matches…"), fiyat yok.
* **Oran veren uç nokta:** `GET /api/data/matchOdds?matchId=<FotMob maç no>&ccode3=<ISO3 ülke>`. Cevap, ülkenin ortak bahis şirketinin oranlarıdır (`persistentKey`, `providerId`, `odds.oddsTabMarkets[].markets[]`, `odds.matchfactMarkets`, `odds.oddsType = "PreMatch"`, `restrictions`). İstek önce `307` ile `&bettingProvider=<şirket anahtarı>` eklenmiş adrese yönlenir (bu bir CloudFront yönlendirmesi, bot koruması değil); toplayıcı yönlendirmeyi elle izler ve **her adımdan önce** sınırlayıcıyı çağırır.
* Ülke matrisi (Salzburg–Milan, 6112294, 12:05–12:20 UTC): `GBR` Bet365_UK (sonra Betfair/Betfred), `DEU` Tipico_Germany (bazen Letsbet_Germany), `AUT` Interwetten_Austria, `CHE`/`GRC`/`IND` Bet365_default, `ESP` Bet365_Spain (bir sorguda 1xBet_Spain), `FRA` Unibet_France, `BEL` Ladbrokes_Belgium, `PRT` Bwin_Portugal, `POL` SuperBet_Poland, `MEX` Novibet_Mexico. **Boş (`null`): `TUR`, `USA`, `ITA`, `NLD`, `BRA`.** Ülke kodu olmadan 204.
* Şirket **zamanla değişebiliyor** (DEU: Tipico→Letsbet, ESP: 1xBet→Bet365, GBR: Betfair→Betfred aynı saat içinde). `&bettingProvider=` ile aynı ülkedeki geçerli şirket sabitlenebilir (`DEU` + `Tipico_Germany` çalıştı; ülkede geçerli olmayan şirket sessizce varsayılana düştü). Bu yüzden her satırda `bookmaker` ve `region` saklanıyor.
* Market kümesi şirkete göre değişiyor (tam liste `samples/`): Bet365 varyantlarında A/Ü ve çifte şans **yok** (1X2, KG, DNB, handikap, doğru skor…); Tipico/Interwetten 1X2 + çifte şans + sadece **2,5** A/Ü + KG; yalnız 1xBet_Spain 1,5/2,5/3,5 A/Ü verdi; FRA/BEL/PRT/POL yalnız 1X2 + KG + A/Ü.
* **Kapanış oranı yok** (geçmiş uç noktası yok); T-30 dk'da yoklayıp son satırı almak tek yol.

**Hukuki durum (önemli):**
* `https://www.fotmob.com/robots.txt`: `User-agent: *` için `Allow: /` ama `Disallow: /api/*`; yalnız Googlebot, Qwantbot, Bingbot, AmazonAdBot için `Allow: /api/*`.
* `https://www.fotmob.com/tos.txt`, "DATA USAGE & SCRAPING": "Use of the data, content, or any information displayed on FotMob for any purpose, including but not limited to scraping … without the express written consent of FotMob is strictly prohibited" ve "The use of automatic services (robots, spiders, indexing, etc.), as well as other methods for systematic, regular, or bulk retrieval of data, is expressly forbidden."
* Projedeki mevcut FotMob toplayıcıları (`matchDetails`, `leagues`, `matches`) aynı `/api/` yolunda çalışıyor; `docs/PROGRESS.md`'deki eski not Mackolik'in `/api/` yasağı yüzünden "sadece FotMob" demişti; FotMob'un kendi `robots.txt` dosyasının da `/api/*`'yı genel istemcilere kapattığı o kararda not edilmemiş görünüyor. **Bu rapor bunu açıkça işaretler; karar sahibinde.**
* Ek not: oranlar FotMob'un ortaklık (affiliate) vitrini; cevapta tıklama/komisyon bağlantıları var. Toplayıcı bu bağlantıları **saklamıyor**.

**Bugün yapılan istek miktarı:** yaklaşık 100 FotMob isteği (robots, tos, 1 gün listesi, 2 maçın `matchDetails`'i, sahte uç nokta denemeleri 404/boş, `matchOdds` 2 maç × ≤5 ülke, 12 ülkelik matris, 3 sabitleme testi). Hepsi `fotmob_rate.acquire()` ile yapıldı; ilk keşif denemelerinde (`follow_redirects=True`) yönlendirmenin ikinci adımı sınırlayıcıdan geçmeden httpx tarafından ardışık yapıldı (en çok 2 istek arka arkaya, hız < 5/sn). 429 veya 403 hiç alınmadı.

### 3.2 Odds-API.io

* Herkese açık, anahtarsız: `GET https://api.odds-api.io/v3/bookmakers` (430 şirket, 390 aktif; listede `Iddaa`, `Bet365`, `Betfair Exchange`, `Unibet`, `1xbet`; **Pinnacle yok**; başka Türk şirketi (Nesine, Misli, Bilyoner, Tuttur…) yok) ve `GET /v3/sports` `[T]` (örnek: `samples/oddsapiio_bookmakers_public_2026-10-15.json`). Diğer her şey `apiKey` ister (401 `You need to provide a valid apiKey`).
* Uç noktalar (OpenAPI `docs.odds-api.io/api-reference/openapi.json` `[A]`): `/events` (sport, league, status, from, to, limit, skip), `/odds?eventId=&bookmakers=`, `/odds/multi?eventIds=<≤10>&bookmakers=` (10 maç = 1 istek), `/leagues`, `/bookmakers/selected`, `/historical/odds` (bitmiş maç, kapanış oranı).
* Marketler: `ML`, `Totals` (satır `hdp`/`max`), `Both Teams To Score`, `Double Chance` (`1X`, `12`, `X2`), `Draw No Bet`, … `[D]`.
* **Fiyat/plan** (fiyat sayfası, 3 Ekim 2026 kopyası `[A]`): Ücretsiz plan "New free API keys are paused indefinitely. Existing free keys keep working." Ücretli: Solo £49 ($65) 2 şirket; Starter £99 ($129) 5; Growth £179 ($239) 10; Pro £229 ($299) 15; hepsi 5.000 istek/saat; WebSocket plan fiyatının 2 katı; "card payments are covered by a 7-day money-back guarantee". Eski ücretsiz plan: 2 "recreational" şirket, 100 istek/saat (500/gün), "geliştirme ve test amaçlı". (Eski `.agents/tasks/iddaa-integration` notundaki "ücretsiz 100 istek/saat sonsuza dek" artık geçerli değil.)
* Şartlar (`odds-api.io/terms` `[A]`): yeniden satış/dağıtım yok, abonelik kademesi dışına tarama yok; ticari yeniden dağıtım için yazılı lisans.
* **Doğrulanamayanlar:** `Iddaa` verisinin hangi maçları/marketleri kapsadığı (Süper Lig, UEFA kupaları, A/Ü 1,5-3,5, KG), gecikmesi, ve hangi planda seçilebildiği. Servisin İddaa verisini nereden aldığı ve bunun İddaa'nın şartlarıyla uyumu bu raporda **değerlendirilmedi**.

### 3.3 OddsPapi

* Ücretsiz hesap (aylık 250 istek, "1 istek = faturalanabilir bir uç noktaya 1 çağrı, dönen veri miktarı fark etmez"; `/v4/historical-odds` ücretsiz ve sayılmaz) `[D]` (docs: `oddspapi.io/us/docs/requests-and-quota`); 250/ay rakamı OddsPapi'nin kendi blogundan `[V]`. Fiyatlandırma sayfası "Customize your plan" ile bağımsız seçim; ücretsiz hesap tavsiye ediliyor `[D]`.
* Uç noktalar `[D]`: `/v4/markets`, `/v4/fixtures` (sportId=10 futbol; `from`/`to` <48 sa), `/v4/odds-by-tournaments?tournamentIds=a,b&bookmakers=pinnacle,bet365` (en çok 3 şirket; turnuvadaki tüm yaklaşan maçlar tek istekte), `/v4/historical-odds` (ücretsiz). Her uç noktada 1000 ms bekleme.
* Şartlar `[A]`: "may not resell, repackage, or redistribute our data as a standalone product"; kullanım "scraping" ve limit aşımı için izlenir.
* **Doğrulanamayanlar:** Türk şirketleri (herkese açık "sportsbooks" sayfasında Pinnacle, Bet365, Betfair, 1xBet, Bwin, Unibet görünüyor; İddaa/Nesine/Misli/Bilyoner görünmüyor), 13 ligin turnuva kimlikleri, çifte şans market adı, ücretsiz hesapta kart istenip istenmediği.

### 3.4 The Odds API

* `api.the-odds-api.com` ve `the-odds-api.com`: bu makineden `ConnectError WinError 10054` (bağlantı 0,1 sn'de sıfırlanıyor), 3 ayrı denemede aynı; `WebFetch` aracı da `ECONNRESET` aldı `[T]`. Muhtemelen ağ/ISP düzeyinde engel; **aşılmaya çalışılmadı**. Docs Internet Archive'dan okundu `[A]`.
* Ücretsiz Starter 500 kredi/ay, $30/ay 20 bin, $59/ay 100 bin, $119/ay 5 M, $249/ay 15 M `[D]`. Maliyet = market × bölge; `/sports` ve `/events` ücretsiz. KG, çifte şans, DNB sadece `/events/{id}/odds` ile `[D]`.
* Futbol anahtarları `[A]`: `soccer_epl`, bundesliga, la_liga, serie_a, `soccer_france_ligue_one`, `soccer_netherlands_eredivisie`, `soccer_portugal_primeira_liga`, `soccer_belgium_first_div`, `soccer_turkey_super_league`, `soccer_uefa_champs_league`, `soccer_uefa_europa_league`, `soccer_uefa_europa_conference_league`; Çekya anahtarı bulunamadı. Bookmaker listesinde İddaa/Nesine yok.
* Uygulama içinde zaten `backend/app/providers/odds_api_provider.py` var (anahtar `.env` içinde yok, `the_odds_api_enabled=False`); bu ağdan çalışmayacağı için bu yol tıkalı.

### 3.5 API-Football, Sportmonks, TheStatsAPI

Yalnızca satıcı bloglarından/arama özetlerinden `[V]`: API-Football ücretsiz plan günde 100 istek (dakikada 10), Pro $19/ay günde 7.500; ücretsiz planın sezon kısıtı ve oranların plan kapsamı **çelişkili**, kendi `/leagues?...` `coverage` bayraklarıyla doğrulanmalı. Resmî sayfalar (`api-football.com`) bu istemciye 403 verdi, aşılmadı. Sportmonks: ücretsiz plan 2 lig, oranlar ücretli eklenti. TheStatsAPI: ücretsiz plan yok, 7 gün deneme, $50/ay, açılış + son fiyat `[D]` (`thestatsapi.com/docs/guides/odds`). Üçü için API adresleri bu ağdan erişilebilir (anahtarsız 401/403 cevabı) `[T]`.

### 3.6 Betfair ve Pinnacle

* Betfair: `api.betfair.com` ve `identitysso.betfair.com` bu IP'ye Cloudflare "Sorry, you have been blocked" (403) `[T]` — aşılmadı. Resmî: hesaba bağlı iki uygulama anahtarı; **gecikmeli** (delayed) anahtar bahis yapmadan gecikmeli fiyat verir; canlı anahtar için £299 tek seferlik ücret + tam doğrulanmış, fonlanmış hesap `[D]` (`betfair-developer-docs.atlassian.net`). Türkiye'den hesap açılıp açılamayacağı resmî kaynaktan doğrulanamadı; açıkça riskli.
* Pinnacle: resmî doküman "access to Pinnacle API suite has been closed for the general public since July 23rd, 2025"; yalnızca özel anlaşma `[D]` (`github.com/pinnacleapi/pinnacleapi-documentation`). Pinnacle çizgileri artık sadece toplayıcılar (OddsPapi gibi) üzerinden.

### 3.7 football-data.co.uk

* `www.football-data.co.uk` bu ağdan `ConnectTimeout` (3 denemede) `[T]`. Internet Archive `fixtures.csv` kopyaları: son kopya 2026-07-30 (içinde 31 Mayıs 2026 maçları; sezon arası dosyası), sütunlar: B365/BF/BMGM/BV/BW/CL/LB/PS(Pinnacle)/Max/Avg 1X2, A/Ü 2,5, AH ve kapanış karşılıkları `[A]` (`samples/footballdata_fixtures_wayback.csv`). UEFA kupaları ve ligin dışındaki maçlar yok.
* Site ana sayfası (2026-10-09 güncel, arşiv): "FREE … its use is intended for private individuals only, NOT commerical or data training products using automated bots/scrapers/AI"; abonelikli API için ortağı TheStatsAPI.
* Sonuç: geçmiş eğitim verisi olarak (zaten kullanıyoruz) değerli; canlı kaynak değil.

### 3.8 İddaa ve Türk siteleri

* `https://www.iddaa.com/robots.txt` `[T]`: `*` (ve Googlebot) için sadece `Disallow: */mac-detay/*` ve `/dosyalar/bayimalzemeleri/`; `claude-code`, `claude-web`, `anthropic-ai` dahil yapay zekâ ajanları için `Allow: /`. Oranlar ise statik sayfada değil; `sitemap.xml` yalnızca program/canlı skor sayfalarını listeliyor. Uygulama verisini aldığı bilinen `sportsbookv2.iddaa.com` adresinin `robots.txt` dosyası yok (404) — bu "izin var" demek değil, belgelenmemiş bir arka uç. Üyelik sözleşmesi (`/bilgi/uyelik-sozlesmesi`) metni statik HTML'de yok, otomatik erişim maddeleri **okunamadı**. Kamuya açık İddaa API'si/lisansı bulunamadı; eski araştırma (`.agents/tasks/iddaa-integration/TECHNICAL-FINDINGS.md`) de otomatik toplamayı önermiyordu. **Hiçbir İddaa/Nesine/Misli/Tuttur oran adresine istek atılmadı** (yalnız robots.txt ve sitemap.xml okundu).
* `nesine.com/robots.txt`: `*` için `api.nesine.com`, `bulten.nesine.com`, `istatistik.nesine.com`, `/iddaa/futbol/populer-bahisler` vb. yasak. `misli.com`: `/iddaa-bahis-detay/*`, `/iddaa-canli-bahis-detay/*` yasak. `tuttur.com`: `/mac-detayi`, `/canli-mac-detayi` yasak. `bilyoner.com/robots.txt` 400 (giriş istiyor). `mackolik.com`: `/api/` ve GPTBot/anthropic-ai/CCBot yasak.
* Sonuç: İddaa oranları için izinli otomatik yol yok. Kısa vadede (a) elle giriş (yol haritası C3), (b) satıcı akışındaki `Iddaa` verisi (odds-api.io, ücretli, doğrulanmadı), (c) İddaa/Spor Toto'ya veri erişimi için yazılı başvuru.

---

## 4. Deneme sonuçları (gerçek örnekler)

Maçlar FotMob'un gün listesinden (`/api/data/matches?date=20261015`): **6112294 Salzburg–Milan** (16:45 UTC) ve **6112353 Hoffenheim–Beşiktaş** (19:00 UTC), her ikisi Avrupa Ligi, kayıt anı ≈12:04 UTC (henüz başlamadı). Ham cevaplar `backend/data/research/odds_samples/raw_matchodds_2026-10-15/`; ayrıştırılmış 6 satır `backend/data/odds/2026-10-15.jsonl`.

| Maç | Ülke / şirket | 1 · X · 2 oranı | Marj (aşırı yuvarlama) | Shin olasılık 1 / X / 2 | Diğer marketler |
|---|---|---|---|---|---|
| Salzburg–Milan | DEU / Tipico | 3,40 · 3,60 · 2,05 | %5,97 | 0,275 / 0,259 / 0,466 | ÇŞ 1X 1,75 · 12 1,32 · X2 1,25; A/Ü 2,5: 1,55 / 2,40; KG 1,50 / 2,40 |
| Salzburg–Milan | ESP / 1xBet | 3,68 · 3,78 · 2,02 | %3,13 | 0,262 / 0,255 / 0,483 | A/Ü 1,5: 1,17 / 4,50; 2,5: 1,67 / 2,32; 3,5: 2,47 / 1,49; KG 1,53 / 2,37; ÇŞ 1,85 / 1,30 / 1,31 |
| Salzburg–Milan | GBR / Betfair UK | 3,80 · 3,75 · 1,91 | %5,34 | 0,247 / 0,250 / 0,504 | ÇŞ, A/Ü 2,5, KG var |
| Hoffenheim–Beşiktaş | DEU / Letsbet | 1,95 · 4,05 · 3,50 | %4,55 | 0,496 / 0,233 / 0,271 | KG 1,45 / 2,65 |
| Hoffenheim–Beşiktaş | ESP / Bet365 | 1,91 · 3,90 · 3,50 | %6,57 | 0,499 / 0,236 / 0,265 | KG 1,44 / 2,63; DNB (takım adlı) |
| Hoffenheim–Beşiktaş | GBR / Betfred | 1,95 · 4,00 · 3,50 | %4,85 | 0,495 / 0,235 / 0,270 | KG 1,45 / 2,70 |

**Doğru maç mı?** `matchOdds` cevabı takım adı/saat taşımıyor; eşleşme istekteki FotMob maç numarasından geliyor. Ek kontroller: (1) Bet365 `Draw No Bet` seçenek adları `Hoffenheim` / `Beşiktaş` (toplayıcı bunu otomatik doğrular: `team_name_check = verified`), (2) üç bağımsız şirket her sonuçta ≤ 3,8 puan farkla aynı favoriyi veriyor, (3) çalışan uygulamanın modeli de aynı yönde: Salzburg–Milan model 0,235 / 0,237 / 0,528 (piyasa 0,247–0,275 / 0,250–0,259 / 0,466–0,504); Hoffenheim–Beşiktaş model 0,581 / 0,214 / 0,206 (piyasa 0,495–0,499 / 0,233–0,236 / 0,265–0,271) — model Hoffenheim'a piyasadan ~8 puan fazla veriyor, yani oranlar tam da yol haritasındaki "piyasayla doğrula/harmanla" kullanımı için bilgi taşıyor. (Modelin çıktısı uygulamanın `GET /api/v1/matches/{id}/prediction` cevabından salt-okunur alındı.)

Odds-API.io ve OddsPapi için gerçek örnek **yok** (anahtar yok); yalnız herkese açık uç noktalar (`/v3/bookmakers`, `/v3/sports`) ve dokümanlar okundu.

---

## 5. Hazırlanan prototip toplayıcılar (hiçbiri uygulamaya/modele bağlı değil; `backend/app/**` ve `backend/config/**` değişmedi)

`backend/scripts/data_collection/`:

| Dosya | Ne yapar | Test durumu |
|---|---|---|
| `odds_common.py` | oran doğrulama (`>1,0`, yoksa `None`, asla 0), marj temizleme (orantılı + Shin; çifte şans için toplam 2'ye ölçekleme), kanonik marketler, takım adı + saat eşleme (güven skoru; eşleşmeyen maçlar nedeniyle listelenir, tahmin edilmez), FotMob gün listesi + sınırlayıcılı GET, anahtar gizleme, JSONL yazma, ortak istek bütçesi | 53 test |
| `collect_odds_fotmob.py` | FotMob `matchOdds`; maç numarasına göre; `--from-raw` çevrimdışı ayrıştırma; `--accept-fotmob-terms-risk` olmadan çalışmaz | 21 test (sentetik + 2 gerçek kayıtlı cevap) |
| `collect_odds_oddspapi.py` | OddsPapi v4; anahtar `ODDSPAPI_API_KEY`; ≈3–4 istek/çalışma; market sınıflandırması `/v4/markets`'ten, sınıflanamayan raporlanır | 19 test (sentetik, dokümandan) |
| `collect_odds_oddsapiio.py` | Odds-API.io v3; anahtar `ODDS_API_IO_KEY`; 10 maç = 1 istek; seçili şirketleri otomatik alır | 19 test (sentetik, OpenAPI'den) |

Çıktı: `backend/data/odds/<tarih>.jsonl` (+ `.fotmob_run.json` / `.oddspapi_run.json` / `.oddsapiio_run.json`), biçim ve kurallar `backend/data/odds/README.md` içinde. Testler: `backend/tests/test_collect_odds_{common,fotmob,oddspapi,oddsapiio}.py`.
**Doğrulama:** `venv/Scripts/python.exe -m pytest tests/test_collect_odds_*.py tests/test_fotmob_rate.py tests/test_collect_fotmob_details.py` → 133 geçti. **Canlı doğrulama yok:** FotMob toplayıcısı `--accept-fotmob-terms-risk` ile **çalıştırılmadı** (bayrağı sahibi verecek); yalnız kayıtlı gerçek cevaplar çevrimdışı ayrıştırıldı. OddsPapi ve Odds-API.io toplayıcıları hiç gerçek servisle çalışmadı.

---

## 6. Sahibin yapması gerekenler

1. **FotMob kararı** (bir cümle): `matchOdds`'u kullanmaya devam etmek robots.txt (`/api/*`) ve kullanım şartlarıyla çelişiyor; mevcut `matchDetails` toplayıcılarıyla aynı kategori. Seçenekler: (a) riski kabul et → toplayıcı `--accept-fotmob-terms-risk` ile çalıştırılır; (b) FotMob'dan yazılı izin iste; (c) bırak, yalnız aşağıdaki izinli kaynakları kullan.
2. **OddsPapi ücretsiz hesap:** https://oddspapi.io → *Sign Up* (e-posta + şifre; **şifreyi/anahtarı bana yazmayın**). Hesap sayfasından API anahtarını kopyalayıp makinede `ODDSPAPI_API_KEY` ortam değişkenine koyun (PowerShell: `$env:ODDSPAPI_API_KEY = "..."`). Sonra `venv/Scripts/python.exe scripts/data_collection/collect_odds_oddspapi.py --date <bugün> --bookmakers pinnacle,bet365` ve çıktıdaki `…oddspapi_run.json`'u bana/lead'e gösterin (eşlenemeyen maçlar, sınıflandırılan marketler). İsteğe bağlı ilk adım: tarayıcıda API'nin `/v4/bookmakers` çağrısıyla Türk şirketi var mı bakmak (1 istek).
3. **İddaa şart ise:** Odds-API.io Solo planı (£49/ay, 7 gün iade, kartla). Site bu ağdan açılmıyorsa kaydı başka bir ağdan yapın; sonra `ODDS_API_IO_KEY` ve `PUT /v3/bookmakers/selected/select?bookmakers=Iddaa,Bet365` ile şirketleri seçin, `collect_odds_oddsapiio.py` çalıştırın. Önce bir hafta deneyin: Süper Lig + UEFA kupaları + A/Ü 1,5-3,5 + KG gerçekten geliyor mu?
4. Ağ notu: The Odds API, odds-api.io sitesi, football-data.co.uk, Betfair bu ağdan ulaşılamıyor/engelli; bunları aşmaya çalışmadık, çalışmamalı.
5. API-Football için (yol haritası C1): hesap açılırsa tek bir `/odds?fixture=…` örnek cevabını ve `/leagues?id=…&season=2026` kapsam bayraklarını ekleyin; ortak modülle bir adaptör ~yarım gün.

## 7. Açık noktalar ve sınırlar

* Tüm "ücretsiz plan" rakamları `[V]` ise satıcının kendi blogundan; kaydolmadan doğrulanamaz. Odds-API.io'nun ücretsiz kayıt durumu 3 Ekim 2026 arşiv kopyasına dayanıyor; güncel sayfada kontrol edin.
* FotMob örnekleri yalnız 2 Avrupa Ligi maçı (bir maç 12 ülkeyle): UECL, UCL ve yerel liglerde oranın varlığı bugün **denenmedi** (bugün yalnız UEL+UECL oynanıyor).
* "Kapanış" için FotMob geçmiş vermiyor; OddsPapi `historical-odds` (ücretsiz, satıcı iddiası) ve Odds-API.io `/historical/odds` kapanış çizgisi için aday, doğrulanmadı.
* Shin ile orantılı marj temizleme arasındaki fark ölçüldü: anlamlı değil (`xdata_devig.json`); ikisi de kaydediliyor.
* Uygulama sunucusuna (8003) salt-okunur `GET .../prediction` çağrısı yapıldı (frontend'in yaptığıyla aynı); DB'ye doğrudan yazılmadı, sunucular durdurulmadı.

## Kaynaklar

* FotMob: https://www.fotmob.com/robots.txt · https://www.fotmob.com/tos.txt
* Odds-API.io: https://api.odds-api.io/v3/bookmakers (herkese açık) · https://odds-api.io/pricing (arşiv 2026-10-03) · https://odds-api.io/terms (arşiv) · https://docs.odds-api.io/api-reference/openapi.json (arşiv) · https://docs.odds-api.io/guides/fetching-odds (arşiv)
* OddsPapi: https://oddspapi.io/us/docs · https://oddspapi.io/us/docs/requests-and-quota · https://oddspapi.io/us/docs/get-odds-by-tournaments · https://oddspapi.io/us/docs/get-markets · https://oddspapi.io/us/legal/terms · https://oddspapi.io/blog/?p=2967 `[V]` · https://oddspapi.io/blog/?p=2498 `[V]`
* The Odds API: https://the-odds-api.com/ · https://the-odds-api.com/liveapi/guides/v4/ · https://the-odds-api.com/sports-odds-data/betting-markets.html · https://the-odds-api.com/sports-odds-data/sports-apis.html · https://the-odds-api.com/sports-odds-data/bookmaker-apis.html (hepsi arşiv kopyası)
* Betfair: https://betfair-developer-docs.atlassian.net (arama özetleri `[V]`) · Pinnacle: https://github.com/pinnacleapi/pinnacleapi-documentation
* football-data.co.uk: arşiv kopyaları https://web.archive.org/web/2026/https://www.football-data.co.uk/data.php · …/fixtures.csv
* İddaa/Nesine/Misli/Tuttur/Mackolik robots.txt dosyaları; https://www.iddaa.com/sitemap.xml
* API-Football / Sportmonks / TheStatsAPI özetleri: arama sonuçları ve https://www.thestatsapi.com/docs/guides/odds.md `[V]`/`[D]`
* Yerel: `docs/research/2026-10-15-accuracy-roadmap.md`, `backend/data/research/xdata_devig.json`, `.agents/tasks/iddaa-integration/`

---

# English summary

* **Works now without signup:** FotMob `GET /api/data/matchOdds?matchId=&ccode3=` returns real bookmaker prices keyed by our own FotMob match id (1X2, double chance, over/under, BTTS depending on the provider; provider depends on country and varies over time; `TUR`/`USA`/`ITA`/`NLD`/`BRA` return `null`, so **no Iddaa**). It is **not permitted**: robots.txt `Disallow: /api/*` for generic clients and the ToS forbid automated/bulk retrieval without written consent. The collector refuses to run without `--accept-fotmob-terms-risk` (owner decision). Tested on 2 Europa League matches (6 real snapshots in `backend/data/odds/2026-10-15.jsonl`); three providers agree within 3.8 points and agree with the model's favourite.
* **Best with signup (free):** OddsPapi free account (250 requests/month, vendor-stated; Pinnacle/Bet365; API reachable). **For Iddaa:** only Odds-API.io lists `Iddaa` (public bookmaker list) but new free keys are paused (archive capture 2026-10-03); entry plan GBP 49/month with a 7-day refund. **The Odds API:** unreachable from this network, no Iddaa.
* **No permitted Iddaa access found** (no public API/licence; robots and ToS checked for iddaa.com, Nesine, Misli, Tuttur, Mackolik; nothing fetched except robots/sitemaps).
* Collectors for FotMob, OddsPapi and Odds-API.io plus the shared `odds_common.py` (de-vig proportional + Shin, mapping with confidence, limiter use, key redaction) are written and tested (133 tests pass); only FotMob parsing was exercised on real recorded answers, the two keyed collectors have never touched the live services.

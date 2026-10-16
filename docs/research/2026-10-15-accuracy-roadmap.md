# TUTAR X: en yüksek isabet için yol haritası (15 Ekim 2026, gözden geçirilmiş sürüm)

**Durum.** Bu bir araştırma sentezi. Uygulama kodu, config, veritabanı ve git değiştirilmedi. Burada önerilen hiçbir
şey devreye alınmadı. Her sayı aşağıdaki kaynaklardan birine dayanıyor; hangi kaynaktan geldiği köşeli parantezde
yazıyor. Bu sürüm iki bağımsız incelemenin [V] düzeltmelerini içeriyor: bazı beklenen kazançlar küçültüldü, öncelik
sırası değişti, hukuki ve veri kaynağı riskleri eklendi (ayrıntı: 8. bölüm).

| Anahtar | Kaynak | Script → çıktı |
|---|---|---|
| [L] | Literatür ve piyasa tavanı raporu (15.10) | `backend/scripts/research/sota_*.py` → `backend/data/research/sota_*.json` |
| [E] | Hata analizi raporu (15.10) | `err_*.py` → `err_*.json`, `err_*_stdout.txt` |
| [D] | Ek veri kaynakları raporu (15.10) | `xdata_*.py` → `xdata_*.json` / `.csv` |
| [S] | Seçici tahmin (Banko/Oranlı kuralları) raporu (15.10) | `sel_*.py` → `sel_*.json`; kurallar test açılmadan önce `sel_frozen_rules.json` dosyasında donduruldu (2026-10-15T10:53:45Z) |
| [V] | Bu belgenin iki bağımsız incelemesi (15.10) | `review_indep_banko.py` → `review_indep_banko.txt`; `review_shin_fav_shift.py` → `review_shin_fav_shift.txt`; `review_roadmap_feasibility.py` → `review_roadmap_feasibility.json`; `backend/data/research/review_fotmob_robots_2026-10-15.txt` |
| [T13] / [T14] / [CAL] | `docs/training/2026-10-13-model-training.md`, `2026-10-14-full-training.md`, `2026-10-14-favourite-calibration.md` | — |
| [LIVE] | `docs/live-tests/2026-10-14/results.md` | — |
| [R] | Bu belge için yazılan binom hesabı (futbol verisi okumaz) | `backend/scripts/research/roadmap_live_sample_size.py` → `backend/data/research/roadmap_live_sample_size.json` |

Veri bölümleri [T14]:
- Eğitim: 2022-08 … 2025-06, 13.187 maç.
- Doğrulama: 2025-07 … 2026-01, 3.396 maç.
- Test: 2026-02-01 … 2026-10-12, 3.402 maç, 254 takvim günü, 165 maç günü (171'i UEFA).
- "Doğrulama+test": 6.798 maç [E].
- Test kümesi 20 turnuva: 17 lig + 3 UEFA kupası (Şampiyonlar Ligi, Avrupa Ligi, Konferans Ligi) [S].

**Önemli uyarı: test bölümü defalarca okundu.** Her sayı tek başına örneklem dışı (out-of-sample). Ama aynı test
bölümü bu turda birçok kez okundu:
- [T14] son değerlendirmesi;
- [CAL], iki kez;
- [L]: GBM, stack, havuzlama, Banko uyumu;
- [E]: hata cepleri ve yaklaşık 8 aday düzeltme; cepler (UEFA beraberlikleri, lig gol seviyeleri, lige yeni çıkanlar)
  doğrulama+test üzerinde bulundu;
- [D]: hava, seyahat, rakım, zemin, hakem, dinlenme, teknik direktör;
- [S].

Bu belge testte işe yarayanları öne çıkarıyor, yaramayanları 4. bölüme koyuyor. Bu seçim yüzünden beklenen kazançlar
iyimser ("kazananın laneti"). Ayrıca üretimdeki β/γ katsayıları Ocak–Haziran 2026'da fit edildi ve doğrulama/testle
çakışıyor; [T14] bunun 1X2'yi şişirmediğini buldu, ama seçici Banko oranları için bu kontrol yapılmadı.
- **İstisna:** [S]'nin Banko/Oranlı kuralları test açılmadan donduruldu; B1 ve B2 sayıları bu açıdan en temiz olanlar.
- **Sonuç:** A2, A3 (lig ofsetleri), A4 ve B3 devreye alınmadan önce **yeni bir bekletme kümesinde** doğrulanmalı:
  2026-10-12 sonrası maçlar ya da takip sisteminin ileriye dönük sonuçları. Bu test bölümünü yeniden puanlamak yetmez.

---

## 1. Türkçe özet (sade dil)

### İki farklı "isabet" var, ikisini ayırmak gerekiyor

**(1) Genel isabet: her maçta "1, X ya da 2" tahmini.**
- **Bugün:** model doğrulama+test maçlarında %51,8 doğru (ligler %51,1, UEFA %59,8) [E].
- **Tavan bahis piyasasının kendisi.** Pinnacle kapanış oranları büyük 5 ligde %54,3 (8.053 maç), 28 ligin tamamında
  %51,4 (24.070 maç) isabet veriyor [L].
- **Bizim 4.805 oranlı lig maçımızda** (doğrulama+test, kapanış kaynakları karışık) piyasa %51,6, model %50,7 [E].
- **Piyasa seviyesine çıkmak genel isabete yaklaşık +0,9 puan ekler.** Büyük 5 ligin test maçlarında fark daha büyük:
  +1,75 puan (model %50,16, piyasa %51,91, 917 maç) [L].
- **Neden piyasa bile daha yukarı çıkamıyor?** Maçların %26,3'ü berabere bitiyor, ama kapanış oranları maçların yalnızca
  %0,57'sinde beraberliği favori görüyor [L]. Beraberliği neredeyse kimse favori yapmadığı için piyasa bile %51–54
  civarında kalıyor.
- **Literatür.** Kapanış oranlarını aynı maçlarda düzenli olarak geçen yayımlanmış bir açık model bulmadık [L].
  - 2017 Soccer Prediction Challenge: RPS'te bahis oranları yarışmanın en iyi modelinden iyiydi (0,2020'ye karşı
    0,2063). Ama oran değeri yarışma sonrası bir çalışmadan geliyor; isabette ise en iyi model (%52,4) bahisçilerden
    (%51,9) biraz yukarıdaydı (https://arxiv.org/pdf/2403.07669, Tablo 1.2).
  - 2023 için "birinci 0,2095, bahisçiler 0,2063" eşleşmesi ikincil kaynaklardan; aynı maç kümesinde olduğu
    doğrulanmadı.

**(2) Seçilmiş tahmin isabeti: Banko ve Oranlı.**

Yüksek yüzdeler burada mümkün. Ama bu ancak **daha az maçta, daha düşük oranlı** tahmin göstererek oluyor:

| Kural (test, 20 turnuva = 17 lig + 3 UEFA) | İsabet | Kaç tahmin | Kaynak |
|---|---|---|---|
| Bugünkü Banko (her maça, p 0,70–0,95) | %81,3 | her maç | [S] |
| Banko yalnız p ≥ 0,85 | **%90,0** (%90 GA %87,6–92,0), n 490 | maçların %14,4'ü; maç günü başına ~3 (takvim günü başına ~1,9) | [S][V] |
| Aynı kural, takipteki 13 turnuvada (10 lig + 3 UEFA) | %90,1, n 374 | takvim günü başına ~1,5 | [V] |
| Banko yalnız p ≥ 0,90 ("çok güçlü") | %93,2 (%89,1–95,8), n 161 | maç günü başına ~1 | [S] |
| Bugünkü Oranlı (bugünkü Banko ile) | %56,8 | maçların %95,5'i | [S] |
| Oranlı, p ≥ 0,85 Banko kuralıyla birlikte | %57,9 | maçların %99,5'i | [S] |
| Oranlı yalnız p ≥ 0,55, p ≥ 0,85 Banko kuralıyla birlikte | **%60,2** (%58,6–61,8) | maçların %76,2'si | [S][V] |
| 3'lü kombine, p ≥ 0,85 Bankolardan | Beklenti ~%70 (bacak olasılıklarının çarpımı); testte %75,4 gerçekleşti (63 gün, beklentinin üstünde, gürültülü) | — | [S] |

- **%90 yalnız bu 20 turnuvada ölçüldü.** Uygulama ise her turnuvada Banko gösteriyor (`MatchDetailV2.tsx` satır 233,
  turnuva filtresi yok). Diğer turnuvalarda seçim yüzdesiz ve "bu ligde test edilmedi" notuyla gösterilmeli.
- **Oran verisi olunca:** piyasa ≥ 0,85 kuralı aynı lig maçlarında **benzer isabette daha çok Banko** veriyor: günde
  ~3,6 Banko ~%92 isabetle, modelde günde ~2,2 Banko ~%89 isabetle [S].
  - Aynı sayıda Bankoda sıralamaya katkısı **+1…+2 puan**: tasarım döneminde +1,3 (GA +0,6…+2,1). Testteki +4,9 iyimser
    bir üst değer.
  - Model+piyasa ortalaması ≥ 0,88'in %94,5'i aynı kapsamda modelden anlamlı olarak iyi değil: model aynı sayıda
    seçimde %92,9 [S].
- p ≥ 0,85 Bankoların adil oranı yaklaşık **1,10–1,15** [L].
- Test döneminde bu Bankoların 490'ından 460'ı çifte şans (1X 336, X2 103, 12 21), 28'i 1.5 Üst idi [S].
- **Oranlı'nın tavanı.**
  - Adil fiyat yolunda (oran = 1/p ≥ 1,60) p ≤ 0,625 olduğu için isabet yapısal olarak ~%60–63'te kalıyor.
  - Gerçek bahisçi oranı yolunda modelin p'si 0,625'i geçebilir; orada sınırı bahisçi fiyatının doğruluğu koyuyor.
  - Ölçülen (bugünkü kural): adil yol %56,8, fiyatlı yol %54,8 [S].

**Para kazandırır mı?** Beklenmemeli. Yüksek isabet bahisçiyi yenmekten değil, düşük orandan geliyor.
- Kapanış oranına karşı "değer" bahisleri −%9,4 getirdi (4.834 bahis) [L][T13].
- Oranlı kuralları kapanış oranlarında zarar etti [S]:
  - bugünkü Banko kuralıyla −%2,9 (adil yol, n 663) ve −%6,1 (fiyatlı yol, n 892);
  - p ≥ 0,85 Banko kuralıyla −%7,1 (n 753) ve −%5,4 (n 1.305).

**14 Ekim canlı sonucu.** Sistem 10/14 tuttu; Claude'un kendi seçimleri 8/14 [LIVE].
- Banko 5/7 ve Oranlı 5/7: ikisinin de %90 güven aralığı %40,9–90,0 [R]. Bu iki seçim aynı 7 maçtan geliyor, yani
  birbirinden bağımsız değil. Bu sonuç hiçbir şey kanıtlamıyor.
- "Banko %90 tutuyor" demek için yaklaşık **300 kayıtlı Banko** gerekir. Gözlenen oran %90 ise aralık o zaman
  %86,8–92,5 olur [R].
- Takip sistemi yalnız 13 turnuvayı kaydediyor. Testte bu 13 turnuvada p ≥ 0,85 takvim günü başına 1,47 Banko verdi
  [V]. 300 Banko yaklaşık **204 takvim günü** sürer: kural bu ay devreye girerse **ilk güvenilir sonuç Nisan–Mayıs
  2027 civarı**.
- 0,90 "çok güçlü" katmanı günde ~0,52 Banko veriyor; 300'e ~573 gün gerekir. Onun %93'ü bir yıldan uzun süre yalnız
  bir backtest sayısı olarak kalacak [V].

### Ne yapabiliriz: öncelik sırası

| Sıra | Adım | Beklenen etki (dürüst) | Ne zaman |
|---|---|---|---|
| 1 | **Paket 1, tek kural sürümü:** Banko yalnız p ≥ 0,85 ("çok güçlü" 0,90+; 0,70–0,85 arası "güçlü" etiketi ve kendi bant isabeti) (B1) + Oranlı yalnız p ≥ 0,55 (B2) + kombinede geçmiş tutma oranı satırı (B4) + takip ekranını kural sürümüne göre ayırma (T) + "ön tahmin / kesin" etiketleri (A1) | Banko %81 → %90, Oranlı %57,9 → %60,2 (maçların %76'sı) [S]. Yüzde yalnız test edilen turnuvalarda gösterilir | **İlk hafta**, ücretsiz |
| 1b | **Paralel: oran arşivi (C1).** Sahibi ücretsiz API-Football anahtarını alır. İlk gün 13 takip turnuvasının bu sezonu için oran çekimi denenir, sonra günde bir çekimle arşiv başlar | Doğrudan isabet kazancı yok; 3. ve 4. adımların ön koşulu. Servis oranları ~7 gün saklıyor [D]: beklenen her hafta veri kaybı demek | **İlk gün**, ücretsiz hesap (bu sezonun kapsamı doğrulanmadı) |
| 2 | **UEFA beraberlik düzeltmesi** (A2), ardından UEFA Banko sayılarını yeniden kontrol | UEFA maçı başına log loss ~−0,005, toplamda ~−0,0004; doğrulamada anlamlı değil [E] | Paket 1'den sonra; yeni UEFA maçlarında doğrulanarak |
| 3 | **Oranı olan maçlarda olasılıkları piyasaya dayandır** (A5; Shin marj temizliği A6 bunun içinde) | 1X2 log loss −0,011…−0,014; genel isabet +~0,9 puan [L][D] | 4–8 haftalık arşivden sonra |
| 4 | **Oran varsa Bankoyu piyasaya göre sırala** (B3) | Aynı sayıda Bankoda +1…+2 puan, ya da benzer isabette daha çok Banko [S] | A5 ile; yeni maçlarda doğrulanarak |
| 5 | **Gol pazarları modeli** (A3) | 2.5 Alt/Üst −0,0052 [T14]; lig ofsetleri −0,001 ama doğrulamada anlamlı değil [E] | Canlı özellik hattı bağlanıp doğrulandıktan sonra (haftalar) |
| 6 | **Piyasadan öğrenen düzeltme katmanı** (A4), yalnız lig maçları | Lig maçında −0,0025 [E]; A5'ten sonra yalnız oransız maçlarda işe yarar, orada anlamlı değil | Canlı özellik hattı + C1 kapsamı belli olunca |
| 7 | **Banko eşiğini kayıtlarla yeniden belirle** (B5, Learn-then-Test) | "%90" sözünü canlı sonuçla kanıtlamak | İlk kez Nisan–Mayıs 2027 civarı, sonra kayan ~6 aylık pencere |
| — | T-60 oran yenileme (A7) | Sabah → T-60 kazancı ölçülmedi | Yalnız gerçek zamanlıya yakın (ücretli) bir oran kaynağıyla |

### İşe yaramayanlar (hepsi test edildi)

Aşağıdakilerin hepsi denendi; ya kazanç yok ya da sonucu kötüleştiriyor (ayrıntı ve sayılar 4. bölümde). Bunların
çoğu da aynı test bölümünde ölçüldü.
- hava durumu;
- hakem (1X2 için);
- seyahat mesafesi, rakım, suni çim;
- dinlenme günü, teknik direktör değişikliği;
- sakat/cezalı listesi;
- başka xG kaynakları, Elo;
- gradient boosting (HistGradientBoosting; CatBoost tarzı), oyuncu RAPM, kalibrasyon katmanları;
- "son 5 maç" doğrulaması (isabeti 2–6 puan düşürüyor [S]);
- 2/3 oylama kuralları;
- belirsiz maçları atlamak.

### Bugün mü, hesap/para mı? Hukuk ve veri kaynağı riskleri

- **Bugün, ücretsiz:** Paket 1 (B1, B2, B4 satırı, T, A1 etiketleri) ve A2.
- **Ücretsiz hesap gerekli (sahibi açmalı): API-Football anahtarı.**
  - Günde 100 istek [D]. Testte 13 takip turnuvasında maç günü başına medyan 8, %90'lık dilimde 38, en çok 53 maç vardı
    [V].
  - Günde bir çekim, maç başına yaklaşık bir istekle sığar; yoğun günlerde ikinci (T-60) çekim sığmaz.
  - Ücretsiz planın bu sezona erişimi doğrulanmadı. İkincil bir kaynak "sezonlar sınırlı" diyor
    (https://getbruin.com/docs/ingestr/soccer-sources/api-football.html).
  - [D]'nin API-Football fiyat, yenileme ve saklama bilgileri bu makineden yeniden doğrulanamadı (resmî sayfalar
    Cloudflare engeli veriyor). API'nin kendisi erişilebilir: anahtarsız istek "Missing application key" döndü [V].
- **Ücretli seçenekler** [D]; bu makineden yeniden doğrulanmadı:
  - API-Football Pro: aylık $19, günde 7.500 istek.
  - Sportmonks: bu turnuva kümesi için gerçekçi seçenek aylık €99 (30 lig), artı oran eklentisi aylık €15–24.
  - Gerçek zamanlıya yakın oran (A7 için): Sportmonks premium oranlar aylık €129'dan.
  - The Odds API: aylık $30, ama bu ağdan TLS bağlantısı sıfırlanıyor. Bu bir erişim engeli; aşılmasını önermiyoruz.
  - Tahmini kadro servisi (aylık €199): önerilmez.
- **Hukuk.**
  - Yabancı bahisçi oranları yalnız iç girdi olarak (marjı temizlenmiş olasılık) kullanılmalı. Arayüzde yabancı bahisçi
    adı, logosu ya da bağlantısı gösterilmemeli.
  - 7258 sayılı Kanun md. 5 yasa dışı bahsin reklamını ve teşvikini cezalandırıyor (ikincil kaynak:
    https://www.kazimceylan.av.tr/yasa-disi-bahis-oynatma-sucu; resmî metne bu ağdan erişilemedi).
  - Sahibi kayıt sırasında API-Football kullanım şartlarını okumalı, uygulamayı herkese açmadan önce hukuki görüş almalı.
- **FotMob riski.**
  - Uygulama maç, kadro ve oyuncu verisini FotMob'un `/api/` uçlarından alıyor. FotMob'un robots.txt dosyası genel
    ajanlar için `/api/*` yolunu yasaklıyor (2026-10-15 kopyası: `backend/data/research/review_fotmob_robots_2026-10-15.txt`).
  - Proje Maçkolik'i aynı gerekçeyle dışlamıştı (`docs/live-center-data-sources.md`).
  - Bu yol haritası FotMob kullanımını genişletmiyor. Lisanslı bir API-Football anahtarı fikstür ve kadro da verdiği için
    C1 aynı zamanda bu tek kaynağa bağımlılığa karşı bir yedek.

---

## 2. Önceliklendirilmiş yol haritası

**Puanlama.** Öncelik = (kazanç × güven) / efor.
- Güven: yüksek = 3, orta = 2, düşük = 1.
- Efor: düşük = 1, orta = 2, yüksek = 3.
- Kazanç G, adımın kategorisine göre:
  - **A, model doğruluğu.** Etkilenen maçlardaki log loss değişimi: ≥ 0,010 → 3; 0,002–0,010 → 2; < 0,002 ya da
    ölçülmemiş → 1.
  - **B, seçim kuralıyla tahmin isabeti.** Gösterilen tahminlerin isabeti, aynı ya da belirtilen kapsamda:
    ≥ +5 puan → 3; +2…+5 → 2; < +2 veya yalnızca beklenti yönetimi → 1.
  - **C, veri ekleme.** Açtığı en büyük A/B adımı üzerinden puanlanır.
- Güven ve efor dereceleri kaynak raporun verdiği derecelerdir; [V] sonrası değişenlerin gerekçesi 3. bölümde.

**Sıra yalnız puana göre değil.** Puan, bağımlılık ve gecikme maliyeti birlikte belirliyor:
- A5'in puanı yüksek, ama C1'e ve birkaç haftalık arşive bağlı.
- C1'in puanı orta, ama oranlar ~7 gün saklandığı için başlamayan her hafta veri kaybı; bu yüzden ilk gün başlıyor.
- A1, B4 ve T düşük puanlı ama ucuz; B1 ile aynı kural sürümünde gitmeleri gerekiyor.

| # | ID | Kat. | Adım | Beklenen kazanç (kanıt) | Güven | Efor | Bağımlılık | Ana risk | Ne zaman | Puan |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | B1 | B | Banko taban eşiği 0,85; 0,90 "çok güçlü"; 0,70–0,85 "güçlü" + bant isabeti; yüzde yalnız test edilen turnuvalarda | Test: %81,3 → %90,0 (n 490, 20 turnuva); 13 takip turnuvasında %90,1 (n 374) [S][V] | yüksek | düşük | T ile aynı anda; A1 etiketleri | Kapsam %14'e düşer; UEFA testi %85,7 (n 35); 20 turnuva dışında test edilmedi; β/γ çakışması Banko için kontrol edilmedi | İlk hafta (Paket 1) | 9 |
| 2 | B2 | B | Oranlı yalnız p ≥ 0,55 (B1 ile aynı sürümde) | B1 ile birlikte %57,9 → %60,2 (maçların %76,2'si) [S][V] | yüksek | düşük | B1 (iki kural etkileşiyor) | Kâr yok (kapanışta −%5,4…−%7,1) [S] | İlk hafta (Paket 1) | 6 |
| 3 | T | — | Takip raporunu `rule_version`'a göre ayır; arayüz varsayılan olarak güncel sürümü göstersin | İsabet değişmez; canlı "%90" kontrolünü mümkün kılar [V] | yüksek | düşük | — | Yapılmazsa eski (%81) ve yeni (%90) seçimler tek tabloda karışır | İlk hafta (Paket 1) | zorunlu |
| 4 | A1 | A | Seçimleri "ön tahmin" / "kesin" diye etiketle; sahibi kesin seçime oynasın | Yeni model kazancı yok. Beklemenin kazancı ölçülmedi; en fazla tüm XI katmanının değeri: −0,0025 (doğrulama) … −0,0043 (test) [D][V] | orta | düşük | FotMob kadro verisi | Tek resmî olmayan kaynak (robots.txt riski) | İlk hafta (Paket 1) | 2 |
| 5 | B4 | B | Kombinede geçmiş "hepsi tuttu" oranını göster (çarpım zaten gösteriliyor) | Beklenti yönetimi: 3 bacakta beklenti ~%70 [S] | orta | düşük | B1 | Gün sayıları küçük | İlk hafta (Paket 1) | 2 |
| 6 | C1 | C | Oran akışı + günlük arşiv; önce 13 takip turnuvası, günde bir çekim | A5'in önünü açar (≤ −0,014 log loss) [L][D]; UEFA için ilk piyasa karşılaştırması | orta | orta | Sahibin API anahtarı | Ücretsiz planın bu sezon erişimi ve kotası doğrulanmadı; kullanım şartları; isim eşleme; hukuk | İlk gün, paralel | 3 |
| 7 | A2 | A | UEFA beraberlik kesimi | UEFA maçında doğrulama+test birlikte ~−0,005, toplamda ~−0,0004; doğrulamada anlamlı değil [E] | orta | düşük | — | Test UEFA beraberlik oranı alışılmadık düşük (0,152); daha önceki UEFA ev sahibi düzeltmesi testte tutmadı [CAL] | Paket 1'den sonra | 4 |
| 8 | A5 (+A6) | A | Oranı olan maçlarda olasılık marjı Shin/power ile temizlenmiş piyasaya dayanır; model yedek ve uyarı olur | Kapanış oranı −0,0136 [L]; kapanış öncesi −0,0110 (test) / −0,0136 (13.840 maç) [D]; isabet +0,9 puan [L]; Shin ek −0,0004…−0,0007 [L][D] | yüksek | orta | C1 + 4–8 hafta arşiv | İddaa marjı ölçülmedi; UEFA'da doğrulanmadı; Oranlı'nın fiyatlı yol kuralı yeniden tanımlanmalı | Arşivden sonra | 4,5 |
| 9 | B3 | B | Oran varsa Bankoyu piyasaya göre sırala | Aynı kapsamda +1…+2 puan (tasarım +1,3, GA +0,6…+2,1; test +4,9 iyimser üst değer) [S][V] | orta | orta | C1, A5 | Dondurulmuş ana kural (R5a) testte anlamlı değil (+1,2) | A5 ile | 1 |
| 10 | A3 | A | Gol modeli adayını gol pazarlarında kullan + lig gol seviyesi ofsetleri | 2.5 Alt/Üst −0,0052, KG −0,0015, skor −0,0065 [T14]; ofsetler üretime göre −0,0010, doğrulamada anlamlı değil [E] | orta | yüksek | Canlı özellik hattı; absent grubu çıkarılarak yeniden fit; yeni bekletme kümesi | Ofsetlerin adaya eklenebilirliği test edilmedi; 1X2 ile tutarsızlık | Haftalar sonra | 1,3 |
| 11 | A4 | A | Piyasadan damıtılmış ridge düzeltme katmanı, yalnız lig maçları | Lig maçında −0,0025, doğrulama ve testte anlamlı [E] | orta | yüksek | Canlı özellik hattı; C1 kapsamı | Özelliklerin çoğu canlı yolda yok; UEFA'da hiç denenmedi; oransız maçlarda anlamlı değil | C1 kapsamı belli olunca | 1,3 |
| 12 | B5 | B | Learn-then-Test ile sertifikalı eşik | Testte hedefin ~1 puan içinde kaldı [S] | orta | orta | ≥ 300 kayıtlı Banko [R][V] | Değiştirilebilirlik varsayımı; dönemsel kayma | Nisan–Mayıs 2027'den | 1 |
| 13 | A7 | A | T-60 dk'da oranları yenile | Sabah → T-60 ölçülmedi; 1–3 gün önceki → kapanış farkı (0,002–0,0035) bunun üst sınırı [L][D] | orta | yüksek | Gerçek zamanlıya yakın ücretli kaynak | API-Football oranları 3 saatte bir yeniliyor [D]; T-60 çekimi kadrodan önceki fiyatı getirebilir | Sonra | 0,7 |
| 14 | A8 | A | Lige yeni çıkan takımlar için önsel | Gerçekçi 0,0005–0,001, henüz gösterilmedi [E] | orta | orta | — | Basit kaydırma testte tutmadı | Sonra | 1 |
| 15 | A9 | A | Aşamaya duyarlı UEFA katmanı | Lig aşaması maçında −0,009…−0,021, küçük n [E] | düşük | orta | A2; ≥ 300 ikinci maç | Eleme turlarına zarar verdi (+0,0104) [E] | Sonra | 1 |
| 16 | C2 | C | Geçmiş UEFA oranlarını doldur | UEFA için ilk piyasa karşılaştırması; kazanç bilinmiyor [D] | düşük | orta | Ücretli API; ağ engeli | The Odds API bu ağdan erişilemiyor [D] | Para + sahibin kararı | 0,5 |
| — | C3 | C | Oranlı ≥ 1,60 için gerçek İddaa fiyatı (elle giriş) | İsabet değişmez; doğru Oranlı seçimini sağlar [D] | orta | düşük | — | Herkese açık API yok; otomatik toplama için yazılı izin gerekir [D] | Bugün (elle) | kolaylaştırıcı |

A6 (Shin/power marj temizliği) artık ayrı bir adım değil, A5'in parçası. A5'ten önce Banko ve Oranlı model
olasılığını kullanıyor; elle girilen oranlara Shin uygulamak yalnız gösterilen piyasa karşılaştırmasını değiştirir.

**Tümü birlikte, gerçekçi beklenti:**
- **Yakın dönem, oran verisi olmadan (Paket 1 + A2):**
  - Banko yaklaşık %90 (p ≥ 0,85), test edilen turnuvalarda, maçların ~%14'ünde [S].
  - Oranlı yaklaşık %60 [S].
  - 1X2 log loss'ta yalnız A2'nin küçük kazancı (toplamda ~−0,0004), yeni maçlarda doğrulanmayı bekliyor [E].
  - Genel 1X2 isabeti değişmez; oranlı lig maçlarında model piyasanın yaklaşık 0,014–0,015 log loss gerisinde kalır
    [E].
- **Orta dönem, canlı özellik hattıyla:** A4 ile A2'nin ayrı ayrı ölçülmüş kazançlarının toplamı ~−0,003 1X2 log loss,
  yani 0,992 → ~0,989 [E]. Bu birleşik bir çalıştırma değil ve aynı test bölümünden seçildiği için iyimser. A3 1X2'yi
  değil gol pazarlarını iyileştirir.
- **Oran verisiyle (C1 + A5 + B3):**
  - Oranı olan maçlarda piyasa seviyesi: genel isabet +~0,9 puan (büyük 5'te +~1,7) [L][E].
  - Banko daha çok maçta benzer isabette: ~%92, günde ~3,6 [S]. Aynı sayıda Bankoda +1…+2 puan beklenir.
  - Oranlı yaklaşık %60 civarında kalır [S].

---

## 3. Details per step

### Phase 1, package 1: one rule version (first week, free)

B1, B2 and the B4 history line ship together as one new `RULE_VERSION`, changing `headline_picks.py`,
`headlinePicks.ts` and the shared fixtures in one step. Shipping them separately would need two version bumps and would
split the tracker record [V]. The tracker change (T) and the A1 labels go in the same week.

#### B1. Banko floor 0.85, "çok güçlü" ≥ 0.90, "güçlü" 0.70–0.85 (score 9)

**What.** Show a Banko only when its probability is ≥ 0.85, and keep the 0.95 cap. Default display for matches without
such a pick: a weaker "güçlü" pick labelled with its own band rate. This keeps one clear pick per match, which the owner
has asked for, instead of "Bu maçta banko yok" on about 86 % of matches [V].

Test band rates for the "güçlü" tier: 0.70–0.75 → 75.4 %, 0.75–0.80 → 78.6 %, 0.80–0.85 → 85.1 %
(`sel_test.json` → `C_rules.banko_bands`) [S].

**Evidence [S] (`sel_test.json` → `C_rules.all_test`, Wilson 90 % CIs), reproduced independently in
`review_indep_banko.txt` [V]:**

| Rule | Hit rate | 90 % CI | n | Picks per match day | Coverage |
|---|---|---|---|---|---|
| R0, current | 81.3 % | 80.2–82.4 | 3,402 | 20.62 | 100 % |
| R1, ≥ 0.85 | 90.0 % | 87.6–92.0 | 490 | 2.97 | 14.4 % |
| R2, ≥ 0.88 | 92.1 % | 89.0–94.3 | 277 | 1.68 | 8.1 % |
| R3, ≥ 0.90 | 93.2 % | 89.1–95.8 | 161 | 0.98 | 4.7 % |

- "Per match day" uses the 165 test days with matches. Per calendar day (254 days), R1 gives 1.93 [V].
- The hit rate tracks the mean probability in every band. For example, 0.85–0.90 predicted 0.873 and landed 0.885.
- On train+validation R1 was 92.0 %. Plan for about 90 %, not 92 %.

**Scope.** The 90 % was measured on 20 competitions (17 leagues and Champions League, Europa League, Conference League:
FotMob ids 42, 73, 10216) [S]. The 13 competitions the tracker follows (`featured_competition_ids` in
`backend/app/config.py`) gave 374 Bankos at 90.1 % on test (`review_roadmap_feasibility.json`) [V]. The app computes a
Banko for every match with a prediction (`frontend/src/pages/MatchDetailV2.tsx` line 233 calls
`selectHeadlinePicks(matchCandidates(rows))` with no competition gate). Outside the tested competitions show the pick
with a "bu ligde test edilmedi" note and no percentage.

**Where the picks come from (test R1, `C_rules.by_type`) [S]:**

| Pick | n | Hit rate | Mean p |
|---|---|---|---|
| 1X | 336 | 91.7 % | 89.1 % |
| X2 | 103 | 84.5 % | 88.1 % |
| 12 | 21 | 81.0 % | 90.2 % |
| 1.5 Üst | 28 | 96.4 % | 87.8 % |
| MS1 | 2 | 2 of 2 | 94.1 % |

- X2 and 12 landed below their stated probability. The samples are small, so watch them in the tracker; do not act
  on them yet.
- Single-outcome 1X2 favourites ≥ 0.85 are rare and noisy. The production model had 21 test matches at 76.2 % [T14].
  Do not advertise 90 % for "MS1" picks.

**UEFA.**
- Test R1: 85.7 % (n 35, CI 73.4–92.9).
- Train+validation R1: 91.6 % (n 382).
- Treat UEFA as noisier, not as worse [S]. A2 changes UEFA probabilities, so re-run the UEFA slice of `sel_test` after A2.

**Where the change goes.** `BANKO_MIN_P`, now 0.7, in two files that must stay in sync:
- `backend/app/prediction/headline_picks.py`
- `frontend/src/utils/headlinePicks.ts`

Both are tested against `frontend/src/utils/__tests__/headlinePicks.fixtures.json`. Bump `RULE_VERSION`
(`headline_v1`). No change was made here.

**Caveats.**
- The backtest predictions used confirmed line-ups [E]. The 90 % applies to picks made after line-ups (A1).
- The β/γ overlap with the test period was audited for 1X2 [T14], not for these selective rates.

#### T. Tracker reports per rule version (required with B1)

Today `backend/app/services/headline_tracking/report.py` `build_track_record()` groups picks by competition and by week
over a 30-day window. `rule_version` is stored on each pick (`records.py` line 116) and returned per item (`report.py`
line 72), but it never filters or groups the summary [V]. After B1 the `/sonuclar` hit rate would mix `headline_v1` picks
(every match, about 81 %) with the new ≥ 0.85 picks, and could neither confirm nor refute the 90 %.

**Change.** Filter or group `build_track_record` by `rule_version`; the UI defaults to the current version. Ship it
before or with B1.

#### B2. Oranlı only when p ≥ 0.55 (score 6)

The Oranlı must come from a different market family than the Banko. With B1, most matches have no Banko, so that
exclusion mostly disappears and the Oranlı numbers change [V]. Both sets are shown:

| Rule (`sel_test.json`) | With today's Banko (`oranli_current`) | With the ≥ 0.85 Banko (`oranli_with_R1_banko`) |
|---|---|---|
| Current Oranlı | 56.8 % (CI 55.4–58.2), 95.5 % of matches | 57.9 % (CI 56.5–59.3), 99.5 % |
| p ≥ 0.55 | 60.6 % (CI 58.7–62.5), 51.7 % | **60.2 % (CI 58.6–61.8), 76.2 %** |
| p ≥ 0.58 | 62.7 % (CI 60.2–65.2), 29.4 % | 62.5 % (CI 60.4–64.5), 45.5 % |

- With the ≥ 0.85 Banko, KG Var becomes the most common Oranlı pick (898 of 3,385) [S].
- Returns at closing odds were negative on every path [S]:
  - with today's Banko: fair-path picks that have a price −2.9 % (n 663), priced path −6.1 % (n 892);
  - with the ≥ 0.85 Banko: −7.1 % (n 753) and −5.4 % (n 1,305).

**Why it is capped.**
- On the fair-price path (fair odds 1/p ≥ 1.60), p ≤ 0.625 by construction.
- `headline_picks.py` prefers a priced candidate (bookmaker odds ≥ 1.60, p ≥ 0.45, p × odds ≥ 1). There model p can
  exceed 0.625, and the ceiling comes from how accurate the bookmaker price is, not from the definition [V].
- Measured with today's rule: fair path 56.8 %, priced path 54.8 % (n 2,126) [S].
- [L] measured the market-ranked best of {1, X, 2, 1X, X2, 12} at a fair price of at least 1.60: hit 49.45 %, mean fair
  odds 2.24. [S] scores higher because its candidate set also includes goal lines and BTTS and it applies the app's
  p ≥ 0.45 floor, so the two figures are not comparable.

**UI.** Say "Oranlı ≈ %60 tutar" plainly. The qualifying price should be the actual Iddaa price (C3).

#### A1. "Ön tahmin" / "kesin" labels (score 2)

**What the evidence does and does not show.** The XI layer is already in production, and it already uses FotMob's
predicted XI before kick-off (`backend/app/prediction/squad_value.py`: "upcoming ones use predicted line-ups";
`lineup_form.py` applies the shift for a "predicted or confirmed" line-up). So a morning pick already uses the predicted
XI [V].

| Measure | Change | 90 % CI | Source |
|---|---|---|---|
| Whole XI layer vs no line-up layer, 1X2 log loss, validation (3,337 matches) | −0.0025 | −0.0042 … −0.0008 | [D] `xdata_lineup_value.json` |
| Whole XI layer vs no line-up layer, 1X2 log loss, test (3,397 matches) | −0.0043 | −0.0058 … −0.0028 | [D] `xdata_lineup_value.json` |
| Predicted XI vs confirmed XI (the benefit of waiting) | not measured | — | [T14] line 225: "predicted (not confirmed) line-ups were not tested" |

The benefit of waiting for the confirmed XI is therefore unmeasured and at most about −0.0025 … −0.0043. The test value
also carries the β/γ overlap caveat [D][T14].

**What remains.** A1 is a process and UI step with no new model gain:
- the automatic tracker already freezes picks 20 minutes before kick-off from a fresh, line-up-aware prediction
  (`docs/PROGRESS.md`, 2026-10-15);
- the match page marks picks made before line-ups as "ön tahmin" and marks a pick "kesin" once the confirmed XI is in;
- the owner bets on the "kesin" pick.

**Pre-registered check.** Log the morning pick next to the T-20 pick in the tracker, or re-score test matches with
archived FotMob predicted XIs where snapshots exist. Only then is there a number for the benefit of waiting.

**Timing.** Team sheets are due 75 minutes before kick-off [D]: Premier League Handbook Rule L.23; UEFA Champions League
regulations, Art. 55.

**Source risk.** The line-ups come from FotMob's `/api/` endpoints, which its robots.txt disallows for generic agents
(see section 1). This dependency predates the roadmap; do not expand it.

#### B4. Kombine: add the historical rate (score 2)

The combined model probability is already shown: `frontend/src/components/combine/slipMath.ts`
`combinedModelProbability()` is rendered in `CombineSlip.tsx`, and the slip allows one leg per match, so the
independence assumption holds [V]. Only the historical all-legs rate is new.

Same-day coupons on test [S] (`E_kombine`):

| Coupon | R1 (≥ 0.85): model expected | R1: landed | Days | R0 (current): landed |
|---|---|---|---|---|
| 2 legs | 79.2 % | 78.9 % | 90 | 65.2 % |
| 3 legs | 69.9 % | 75.4 % | 63 | 53.3 % |
| 4 legs | 62.1 % | 69.8 % | 55 | 42.6 % |
| 5 legs | 54.9 % | 65.8 % | 40 | 35.4 % |

- The expectation is the product of the leg probabilities, about 70 % for three p ≥ 0.85 legs. The landed rates for
  3–5 legs are above expectation over few, overlapping days; treat them as noisy, not as the expectation.
- If Iddaa requires a minimum number of matches per coupon (MBS) on many matches, the owner effectively plays kombine.
  This is unverified; check the current rule.

### Phase 1b: odds archive (day 1, in parallel)

#### C1. Odds feed plus a daily snapshot archive (score 3, started on day 1 for lead time)

**Why day 1.** By [D], API-Football keeps only about 7 days of odds, so every week without an archive is data lost for
good. The archive is needed to check A5 on the real feed and to get the first market comparison for UEFA. Starting it
needs no app code.

**Plan.**
1. The owner creates the free API-Football key. An agent cannot.
2. Day 1: test the odds endpoint for the current season of the 13 tracked competitions. A secondary source says the free
   plan has all endpoints but limited seasons (https://getbruin.com/docs/ingestr/soccer-sources/api-football.html).
3. Start one archive pull per day for those 13 only: 1X2 and O/U 2.5 at minimum, double chance and goal lines if
   available. Store every snapshot with timestamp and source; map each match to its FotMob id.
4. Upgrade to Pro ($19/month [D]) only if season access or volume fails.

**Quota.** Free plan 100 requests a day [D]. The 13 tracked competitions had median 8, 90th percentile 38 and maximum 53
matches per match day on test (`review_roadmap_feasibility.json`) [V]. One daily pull fits only if odds cost about one
request per match; a second T-60 pull does not fit on busy days. The app shows hundreds of competitions; covering them all
is not realistic on the free plan.

**Not re-verified.** [D]'s API-Football pricing, 3-hour refresh and 7-day retention could not be re-checked from this
machine: api-football.com pricing, docs and terms pages and api-sports.io/terms return a Cloudflare challenge. The API
itself is reachable: `v3.football.api-sports.io/status` returned "Missing application key" [V].

**Other sources [D].**
- Sportmonks: €29 covers 5 leagues, €99 covers 30, €249 covers 120. For 10 leagues plus 3 UEFA competitions the
  comparable option is €99/month plus an odds add-on of €15–24/month.
- Not usable: The Odds API (TLS reset on this network; do not circumvent it), Pinnacle API (closed to the public since
  2025-07-23), Betfair API (Turkey is a restricted region), OddsPortal (geo-blocked in Turkey, terms prohibit scraping),
  Iddaa (no public API).

**Legal.** Use foreign odds only as internal inputs (de-vigged probabilities); show no foreign bookmaker names, logos or
links in the UI. Law 7258 Art. 5 penalises advertising or encouraging illegal betting (secondary source:
https://www.kazimceylan.av.tr/yasa-disi-bahis-oynatma-sucu; the official text was unreachable). The owner should read
the API-Football terms at sign-up and get legal advice before any public release.

**Also a fallback.** A licensed API-Football key also provides fixtures and line-ups, which reduces the single-source
dependency on FotMob's `/api/` [V].

**Why any major book is enough.** 1X2 log loss of different books' closing odds, top-5 leagues
(`sota_market_benchmarks.json` → `by_group`; not identical match sets):

| Odds | Log loss | Matches |
|---|---|---|
| Bet365 closing | 0.96928 | 9,098 |
| Pinnacle closing | 0.96581 | 8,053 |

The difference between books is small next to the model's gap of 0.0136 [L].

### Phase 2: model work without new data

#### A2. UEFA draw reduction (score 4)

**The problem [E].** In the group/league phase, the model predicts too many UEFA draws and too few home wins:

| Period | Draw: predicted / observed | Home win: predicted / observed |
|---|---|---|
| Train | 0.224 / 0.192 | 0.436 / 0.495 |
| Validation+test | 0.220 / 0.183 | 0.446 / 0.514 |

**The fix [E]** (`err_details.json` → `draws.fixes`). A draw intercept of −0.149 fitted on train UEFA matches:

| Split | UEFA matches | Change per UEFA match | 90 % CI | Observed draw rate |
|---|---|---|---|---|
| Validation | 396 | −0.00285 | −0.00752 … +0.00202 (not significant) | 0.189 |
| Test | 171 | −0.00934 | −0.01603 … −0.00212 | 0.152 |
| Pooled (weighted mean of the two) | 567 | about −0.0048 | — | — |

- Over all 6,798 validation+test matches the pooled effect is about −0.0004.
- The test draw rate was unusually low (0.152, against 0.189 in validation and 0.203 in train UEFA), which inflates the
  test gain.
- By stage, from a related fit (`err_uefa_recal.json`, group-phase draw shift −0.192): the point estimate is negative in
  every stage, but no stage is individually significant. Validation group −0.00302 (−0.00905 … +0.00327); test group
  −0.01653 (−0.03209 … +0.00137); test knockout −0.0100 (−0.01955 … +0.00079).

**Why it is still early in the order.** The owner's live use is UEFA nights ([LIVE], `docs/live-tests/2026-10-13-ucl.md`),
the change is cheap, and no UEFA odds exist for a market check [L][D].

**Confidence: medium.** Confirm on new UEFA matches before relying on it. The 2026-10-14 UEFA home-advantage fix failed on
test [CAL]; [E] explains that failure by the knockout-heavy test period. After A2, re-run the UEFA slice of `sel_test`.

### Phase 3: odds-based steps (after 4–8 weeks of archive)

#### A5. Market-anchored probabilities, with Shin/power de-vig (A6) (score 4.5)

**What.**
- Where odds exist, base the shown 1X2 and O/U probabilities on the Shin- or power-de-vigged market.
- Optionally sharpen them: the blend fitted on train+validation put weight 1.176 on the market [D].
- Use the model for matches without odds, and as a disagreement warning.
- Keep both visible, so the PRODUCT.md principle "the market is the benchmark" still holds.

**Evidence.** 1X2 log loss, model vs market on the same matches:

| Comparison | Matches | Model | Market | Gap, model minus market (90 % CI) | Source |
|---|---|---|---|---|---|
| Closing odds, test | 2,234 | 1.0057 | 0.99213 | +0.01357 (+0.0084 … +0.0189) | [L] |
| Pre-closing odds, all splits | 13,840 | 0.98044 | 0.96680 | +0.01364 (+0.01165 … +0.01558) | [D] |
| Pre-closing odds, test | 1,965 | 0.99947 | 0.98847 | +0.0110 (+0.0059 … +0.0159) | [D] |

A positive gap means the market is ahead. [D] reports the two pre-closing rows as market minus model; the signs are
flipped here so that all rows read the same way.

- The model adds no information on top of the market: log-pool weight on the model −0.14 [L]; blend weight 0.0008 [D].
- Accuracy on the same matches: 50.5 % → 51.4 % [L].
- Each source's 10 % most confident 1X2 picks: 78.7 % → 81.7 %, +3.0 (CI +1.7 … +4.4) [D].
- O/U 2.5: −0.0057 [D].
- The gap is largest in the Süper Lig (−0.0247, n 1,367) [D].
- The market-side gap is well established on 13,840 matches. The archive check is that the real feed's odds de-vig to a
  similar log loss; 4–8 weeks of the 13 tracked competitions is a few hundred matches, enough for that sanity check but
  not to resolve gains of 0.002.

**Shin/power de-vig (formerly A6).**

| Measure | Change in log loss | Source |
|---|---|---|
| Shin minus proportional, Pinnacle | −0.00035 | [L] |
| Shin minus proportional, Bet365 | −0.00067 | [L] |
| Shin minus proportional, market average | −0.00065 | [L] |
| Power minus proportional (13,841 matches) | −0.00070 | [D] |
| Shin minus proportional, test only (1,966 matches) | −0.00043 (CI −0.0014 … +0.0005, not significant) | [D] `xdata_devig.json` |

- With proportional de-vig, favourites priced 0.7–0.9 are under-priced by about 2.5–3.5 points
  (`sota_market_benchmarks.json`: 0.7–0.8 band implied 0.7439, observed 0.7786; 0.8–0.9 band 0.837 vs 0.8621) [L].
- Shin closes only part of that. It moves these favourites up by about +1 to +2 points, depending on the book's margin
  (`review_shin_fav_shift.txt`, closing odds, bands 0.7–0.8 / 0.8–0.9) [V]:
  - Pinnacle: +1.07 / +1.33 (n 1,423 / 534);
  - Bet365: +1.87 / +2.23;
  - market average: +1.62 / +1.88.
- After Shin, favourites are still under-priced (Pinnacle 0.7–0.8 band +3.5 points, Bet365 0.8–0.9 band +3.1) [V]. A
  fitted recalibration that would close this scored −0.00061 (closing) and −0.00106 (pre-closing) on test, both with
  CIs spanning 0 [L].
- Before A5, Shin on manually entered odds only changes the displayed market comparison, and needs a complete 1X2 book
  from one bookmaker. So it is folded into A5 [V].

**Risks.**
- The Iddaa margin is not measured; there is no Iddaa history in the repo [D].
- UEFA cannot be validated without odds history (C2).
- The model becomes mostly a fallback and a warning layer.
- **Oranlı rule must be redefined.** After A5 the priced Oranlı rule (p × Iddaa odds ≥ 1) will rarely trigger, because
  Iddaa's margin is larger than the de-vigged market's [V].

#### B3. Banko ranked by the market (score 1)

**Evidence [S].** 1,965 test league matches with closing 1X2 + O/U 2.5 (`C_rules.odds_rows`), compared with the
design period (train+validation, 11,875 odds rows, `sel_design2.json` → `odds_rows_banko.by_threshold.lo0.85`):

| Rule | Test hit rate (90 % CI) | n | Picks per day | Test: vs model at the same n | Design: vs model at the same n | Frozen before test? |
|---|---|---|---|---|---|---|
| Model-only ≥ 0.85 (B1 on these rows) | 89.2 % (85.8–91.8) | 286 | 2.17 | — | — | yes (R1) |
| Model and market both ≥ 0.85 (R5a) | 91.1 % (87.7–93.7) | 248 | 1.88 | +1.2 (CI −0.6 … +3.2) | +1.4 (CI +0.85 … +2.0) | yes, primary odds rule |
| Blend ≥ 0.85 (R5b) | 90.3 % (87.4–92.7) | 341 | 2.58 | +1.8 (CI −0.3 … +3.8) | +1.2 (CI +0.6 … +1.9) | yes |
| Blend ≥ 0.88 (R5c) | 94.5 % (91.0–96.7) | 182 | 1.38 | +1.7 (CI −1.3 … +4.8); model at the same n 92.9 % | — | yes |
| Market-only ≥ 0.85 | 91.95 % (89.6–93.8) | 472 | 3.58 | +4.9 (CI +2.6 … +7.2) | +1.3 (CI +0.6 … +2.1) | no |

**Reading.**
- The robust message is **more Bankos at a similar hit rate**: market ≥ 0.85 gives about 3.6 picks/day at about 92 %,
  against the model's 2.2/day at about 89 % on the same rows.
- At the same coverage, expect about **+1 to +2 points**. The test's +4.9 is 3.7 times the design estimate and comes from
  a rule that was not frozen; treat it as an optimistic upper value.
- None of the frozen odds rules (R5a, R5b, R5c) was significantly better than the model on test.
- The meta-model raised the top quarter of test Bankos from 87.4 % to 90.7 %, +3.3 (CI +1.8 … +4.8). It is the only
  significant cut of three: top 10 % +0.29 (CI −1.68 … +2.14), top 50 % +0.76 (CI −0.30 … +1.82); the design-period top
  quarter was +1.2 (`sel_test_ci.json`, `sel_frozen_rules.json`).
- **Same direction in [L]** (≥ 0.85, validation+test). Picks where model and market agree hit 92.7 % (589 picks). Picks
  only the model likes hit 81.1 % (90 picks); on test alone 77.5 % (40 picks).

**Rule.** Where odds exist, rank Bankos by the market and drop model-only picks. Without odds, fall back to B1. Confirm on
the archive's new matches before deploying.

**Rating.** G = 1 (expected gain below +2 points at the same coverage), confidence medium, effort medium: score 1.

### Phase 4: after the runtime feature pipeline is wired (weeks)

A3 and A4 both need features that are not in the live prediction path. No app module imports
`app/features/match_model_features.py` or `app/prediction/player_impact.py`; the integration is paused
(`docs/PROGRESS.md`; [T14]) [V]. Both are "weeks, not today".

#### A3. Goal markets: goal-model candidate plus league scoring offsets (score 1.3)

**Part 1: the `train:lean` candidate [T14].**

| Market (test) | Change in log loss | 90 % CI |
|---|---|---|
| O/U 2.5 | −0.00524 | −0.00668 … −0.00381 |
| BTTS | −0.00147 | −0.00250 … −0.00042 |
| Exact score | −0.00650 | −0.00902 … −0.00401 |

- Against a baseline on the same goal layer, O/U 2.5 is still −0.00451 [T14].
- It closes about half of the O/U gap to the market. On 1,965 matches: market 0.66494, candidate 0.66971, production
  0.67556 [T14][L].
- It is not deployed. It failed the 1X2 and European deploy criteria [T14], and its "absent" coefficients have the wrong
  signs [T14][D].
- It needs the RAPM XI-vs-usual terms and a regularly refreshed ratings export, i.e. the paused pipeline [V].
- The test split has already been scored for this candidate. Before deployment it needs a re-fit without the absent
  group plus a rolling-origin re-validation on train+validation, or a fresh holdout. A clean holdout of about 2,000 matches
  takes about 5 months (test had 3,402 matches in 254 days) [V].

**Part 2: per-league ln-total offsets [E]** (`err_distill.json` → `league_total_offsets`). Fitted on train and shrunk with
200 pseudo-matches. Measured against the production baseline, not on top of the `train:lean` candidate.

| Measure | Change | 90 % CI |
|---|---|---|
| O/U 2.5, validation | −0.00027 | −0.00166 … +0.00103 (not significant) |
| O/U 2.5, validation odds rows | worse: 0.68363 → 0.68424 | — |
| O/U 2.5, test | −0.00171 | −0.00308 … −0.00039 |
| O/U 2.5, validation+test | −0.00099 | −0.0019 … −0.0001 |
| Exact score, validation+test | −0.00176 | −0.00286 … −0.00062 |

- The significance comes from test. Additivity to the candidate (which already uses a different, train+validation goal
  layer) is untested; re-validate the two together.
- The current goal layer shrinks league scoring levels toward the global mean. In the Bundesliga, for example, the model
  puts the over-2.5 rate at 0.565; it was 0.655 observed, and the market had 0.605.

**Pick implications.**
- BTTS barely beats a constant: 0.6844 vs 0.6884 [E]. Keep KG out of Banko.
- Market O/U sides at ≥ 0.65 hit about 70 % on about 11 % of matches (70.1 %, 10.9 %) [L]. This is not a hard cap:
  closing-market sides at ≥ 0.70 hit 75.0 % on test (n 104, `xdata_market_value.json` → `picks_ou25_by_threshold`) [D].

**Risks.** 1X2 and goal markets would come from two different lambda sets, so they can disagree. The European O/U CI
spans 0 (−0.0034, CI −0.0113 … +0.0049) [T14].

**Rating.** Confidence medium (test already used; additivity untested), effort high (pipeline wiring): score 1.3.

#### A4. Market-distilled correction layer, league matches only (score 1.3)

**What [E].** A ridge regression of the market-minus-model logit differences (supremacy and draw) on pre-match features,
trained on historical closing odds that are already local. At runtime it needs no odds, but it needs these features
(`scripts/research/err_distill.py`), most of which are **not** in the live prediction path [V]:
- `home/away_xi_d_off`, `xi_d_def`: from the paused player-impact pipeline;
- injury and suspension counts: the team-news refresh loop defaults to off (`team_news_refresh_enabled = False` in
  `backend/app/config.py`);
- derby distance (stadium coordinates), new-team flags, matchday and last-4-rounds flags;
- also last-5 xG, goals and points, value ratio, line-up form, rest days, Euro flags, competition dummies.

**Evidence [E]** (`err_distill.json`), 1X2 log loss change on league matches:

| Split | Change | 90 % CI |
|---|---|---|
| Validation | −0.00227 | −0.00439 … −0.00009 |
| Test | −0.00276 | −0.00497 … −0.00063 |
| Validation+test | −0.00252 | −0.00407 … −0.00101 |

- The gap to the market falls from 0.0148 to 0.0121. RPS −0.0006. Top-pick accuracy 51.08 % → 51.20 %.
- 1X2 favourites ≥ 0.75 on odds rows: 199 picks at 78.4 % → 266 picks at 80.1 %.
- Market-distilled −0.0025 vs results-fit −0.0018 with the same features. The results-fit value is the best of three
  ridge strengths, chosen after seeing validation+test (λ 30 / 300 / 3000 gave +0.00189 / −0.00064 / −0.00179); the
  difference between the two was not tested.

**Caveats.**
- Fitted and scored on league rows only; never tested on UEFA, so the deploy criterion "European subset not worse"
  [T14] cannot be checked. Limit it to league matches.
- Once A5 exists, A4 only matters on matches without odds, where its gain was not significant: −0.00182, CI
  −0.00486 … +0.00124. Decide on A4 only once C1's coverage is known; if odds cover the leagues, A4 adds little.
- It already contains a draw intercept (+0.070). Do not also add the separate global draw intercept (−0.00058 [E]).

### Phase 5: when data accumulates, or with paid real-time odds

#### B5. Certified threshold (Learn then Test) (score 1)

**Evidence [S]** (`sel_design2.json`; test results in `sel_test.json`). Each target miss rate α was certified on
train+validation and gives a threshold:

| α | Threshold | Test | Target |
|---|---|---|---|
| 0.08 | 0.87 | hit 92.2 % (2.03 per day) | held |
| 0.10 | 0.83 | hit 89.15 % | slightly exceeded |
| 0.12 | 0.81 | miss rate 12.7 % | slightly exceeded |
| 0.15 | 0.78 | miss rate 14.6 % | held |

**How long this takes [R][V].**
- About 300 tracked picks are needed. At an observed 90 %, the 90 % CI is then 86.8–92.5. After 100 picks, a rule whose
  true rate is 90 % still shows ≤ 85 % 7.3 % of the time.
- The tracker freezes picks only for the 13 tracked competitions. On test, ≥ 0.85 in those gave 374 Bankos over 254
  calendar days: 2.44 per match day, 1.47 per calendar day, 47–79 per in-season month (`review_roadmap_feasibility.json`).
- 300 Bankos therefore take about 123 match days, about 204 calendar days: **first certification realistic around
  April–May 2027**, then a rolling roughly 6-month window, with a margin of 1–2 points. For a "90 % Banko" this gives a
  threshold of about 0.86–0.87 [S].
- The 0.90 tier gives 0.52 per calendar day, about 573 days to 300 picks.

Method: Angelopoulos et al., "Learn then Test", https://arxiv.org/abs/2110.01052

#### A7. Late odds refresh, T-60 (score 0.7)

**What was measured.** football-data pre-closing odds against closing odds. Pre-closing odds are collected on Friday
afternoons (weekend) and Tuesday afternoons (midweek), 1–3 days before kick-off (`xdata_market_value.json` note):

| Odds | Matches | Log loss, pre-closing minus closing (90 % CI) | Source |
|---|---|---|---|
| Pinnacle, top 5 | 8,051 | +0.00197 (+0.00069 … +0.00326) | [L] |
| Pinnacle, all divisions | 23,249 | +0.00351 (+0.00268 … +0.00436) | [L] |
| Market odds, all splits | 13,840 | +0.00343 (+0.00243 … +0.00446) | [D] |
| Market odds, test | 1,965 | +0.0018 (−0.0007 … +0.0043, not significant) | [D][L] |

**What A7 would change.** From a morning-of snapshot to T-60. The morning snapshot is already much closer to closing, so
the gain is unmeasured and below the 0.002–0.0035 above.

**Feasibility.** By [D], API-Football pre-match odds refresh every 3 hours, so a T-60 pull can return a price taken before
the T-75 team sheets. The extra pull may also not fit the free quota (C1). A7 therefore needs a near-real-time pre-match
odds source; [D] lists Sportmonks premium odds from €129/month. Check the gain first on archived snapshot timestamps.

**Rating.** G = 1, confidence medium, effort high: score 0.7, ranked below A2 and B3.

#### A8. Promoted-team prior (score 1)

**The problem [E].** Matches with a team new to the league are 27 % of odds rows. Their gap to the market is 0.0212,
against an average of 0.0148, with a stable excess. The model overrates new teams away from home:

| New team away, win probability | Model | Market | Observed |
|---|---|---|---|
| Validation+test, matchday > 12 | 0.261 | 0.246 | 0.184 |

**What has been tried.** A constant shift failed: −0.0003, CI −0.0030 … +0.0022.

**Next step.** A step-up prior tied to the division the team came from, decaying over 10–15 matches. A realistic gain
is 0.0005–0.001, which has not been shown yet. This pocket was found on validation+test, so it needs a fresh holdout.

#### A9. Stage-aware UEFA layer (score 1)

**League-phase home lift [E].**
- Group-phase matches: −0.0092 on validation, −0.0213 on test (36 matches); both CIs span 0 (`err_uefa_recal.json`).
- It hurts test knockout matches: +0.0104 (135 matches).

**Second legs [E].** The model ignores the aggregate score:

| First-leg situation (home team) | Matches | Home win predicted | Home win observed |
|---|---|---|---|
| Led by 2+ | 44 | 0.607 | 0.477 |
| Trailed by 2+ | 40 | 0.366 | 0.500 |

Wait for at least 300 second legs before fitting anything.

**Confidence: low.** [E] rated the UEFA finding medium. It is set to low here because the samples are small (36 group
matches, 40–44 second legs), the home lift hurt knockout matches, and the 2026-10-14 UEFA home term failed on test
[CAL].

#### C2. UEFA odds history backfill (score 0.5)

The Odds API historical endpoint (paid, from June 2020) could backfill UCL, UEL and UECL odds. It is blocked on this
network [D]. Collecting going forward through C1 is the free alternative.

**Ratings.** [D] gives no confidence or effort rating for this step. Both are this roadmap's own: the gain on UEFA is
unknown, and the source is not reachable from this network.

#### C3. Iddaa prices (enabler, no accuracy change)

Iddaa has no public API. Its membership terms on data reuse could not be read, and no Iddaa odds history exists in the
repo [D]. Keep manual entry for the ≥ 1.60 Oranlı qualification, or ask the operator for written permission.

---

## 4. What will NOT help (tested and failed, or no gain)

Log loss deltas are "new minus baseline"; negative is better. Most of these were measured on the same test split as the
promoted steps (see the caveat at the top).

| Idea | Measured result | Source |
|---|---|---|
| Gradient boosting on our rating features (sklearn HistGradientBoosting, CatBoost-style; CatBoost itself was not run) | Alone: +0.00208 (worse). Stacked: −0.00033, CI −0.00257 … +0.0019 | [L] `sota_gbm_experiment.json` |
| Switching rating family (Elo, pi, bivariate Poisson, state-space) | RPS differences about 0.0002 in the literature; no source shows > 0.002 against a tuned time-weighted model | [L] |
| Player xG-RAPM / player-impact model for 1X2 | −0.0009, CI −0.0023 … +0.0006; UEFA point estimate worse (+0.0039) | [T14] |
| Calibration layers (temperature, Platt, isotonic, UEFA home term) | Temperature +0.0008; UEFA home term +0.0083 on test | [E][CAL] |
| Per-league home advantage | +0.00098, CI +0.00016 … +0.00175 (worse) | [E] |
| Per-league draw intercepts | Nothing beyond one global intercept | [E] |
| Model + market pooling | Model weight −0.14 (pool) / 0.0008 (blend) | [L][D] |
| Weather (ERA5 at kick-off, an upper bound for any forecast) | 1X2 −0.0002 … −0.0004; every CI includes 0 | [D] |
| Referee (for 1X2) | +0.00016; O/U −0.0005; already used for cards props | [D] |
| Travel distance / altitude / artificial turf | −0.00011 (ns) / 0.0000 / +0.00003 (O/U −0.0005) | [D] |
| Rest days / fixture congestion | +0.00077, CI +0.00005 … +0.0015 (worse) | [D] |
| Coach change | −0.00003 (ns) | [D] |
| Injury / suspension lists | +0.0002 (ns); coefficient signs wrong | [D][T14] |
| Other xG sources (Understat, FBref, StatsBomb), ClubElo | Not legally usable or not current; Elo is the same results signal | [D] |
| Predicted line-ups (Sportmonks, €199/month) | At best part of the 0.003–0.004 line-up value | [D] |
| Last-5 form as a probability or Banko filter | When form put the favourite ≥ 0.85, it won 45.5 % (n 11). As a filter: −5.9 to −6.5 points at the same coverage | [S] |
| Elo agreement / 2-of-3 or 3-of-3 voting | Elo 1X2 LL 1.0057 vs model 0.9960; voting inconsistent between design and test | [S] |
| Abstaining on uncertainty flags (UEFA, early season, promoted, few matches, long break) | About 0 points; R1 without UEFA and early season 89.7 % vs 90.0 % | [S] |
| "Value" betting against closing odds | −9.4 % on 4,834 bets | [L][T13] |

---

## 5. Honest ceilings (with sources)

| What | Ceiling | Source |
|---|---|---|
| 1X2 accuracy, top-5 leagues | Pinnacle closing: 54.28 %, RPS 0.19391, log loss 0.96581 (8,053 matches) | [L] `sota_market_benchmarks.json` |
| 1X2 accuracy, all 28 divisions | Pinnacle closing: 51.43 %, RPS 0.2002, log loss 0.99044 (24,070 matches) | [L] |
| Our model today | Validation+test 51.8 % (leagues 51.1 %, UEFA 59.8 %). On our 4,805 league matches with odds (mixed closing sources): 50.7 % vs market 51.6 % | [E] `err_details.json` |
| Gain from reaching market level | About +0.9 points overall; +1.75 on top-5 test matches (50.16 % vs 51.91 %, 917 matches) | [E][L] `sota_model_vs_market.json` |
| Draws | 26.3 % of results; the market makes a draw its favourite in 0.57 % of matches (largest draw probability 0.395) | [L] |
| Published models vs bookmakers | 2017 Soccer Prediction Challenge (Table 1.2 of https://arxiv.org/pdf/2403.07669): best challenge entry in the table (XGBoost + pi-ratings, Hubáček et al.) RPS 0.2063, accuracy 52.43 %; bookmaker odds RPS 0.2020, accuracy 51.94 %, from a post-challenge study (marked "*", not part of the challenge; same match set not stated). Some later post-challenge studies in the same table report lower RPS (down to 0.1925); none of these is a verified same-match comparison with closing odds. 2023: winner 0.2095 vs bookmakers 0.2063 comes from secondary sources (https://arxiv.org/html/2309.14807 lists "Bookmakers 0.2063" without stating the match set), not verified on the same set | [L][V] |
| Market efficiency | Statistical models failed to beat odds on about 10,000 English matches; 8 of 11 markets efficient at best odds | [L] https://salford-repository.worktribe.com/output/1472154/odd-setters-as-forecasters-the-case-of-english-football ; https://ideas.repec.org/a/eee/intfor/v35y2019i2p712-721.html |
| O/U 2.5 | Market 58.24 %, log loss 0.67248 (23,244 matches). Sides ≥ 0.65 cover 10.9 % of matches and hit 70.1 % [L]; closing sides ≥ 0.70 hit 75.0 % on test (n 104) [D] | [L] `sota_ou_market.json`; [D] `xdata_market_value.json` |
| Banko, model only | 90.0 % at p ≥ 0.85 (2.97 per match day, 20 competitions); 90.1 % in the 13 tracked competitions (1.47 per calendar day); 93.2 % at ≥ 0.90. Every match: 81.3 % | [S][V] |
| Banko with odds | Market ≥ 0.85: 91.9 % at 3.6 per day vs model 89.2 % at 2.2 per day on the same rows. At the same coverage about +1 to +2 points (design); blend ≥ 0.88 at 94.5 % is not significantly above the model's 92.9 % at the same n | [S][V] |
| Closing-market 1X2 favourites | ≥ 0.85: 90.8 % on 163 picks (1.2 % of matches). Top 10 % of double-chance picks: 95.4 % | [D] `xdata_market_value.json` |
| ≥ 95 % at usable coverage | Not supported anywhere in the data; ≥ 0.95 picks pay about 1.05 fair odds | [S] |
| Oranlı (price ≥ 1.60) | Fair-price path: p ≤ 0.625 by construction. Priced path: capped only by bookmaker accuracy. Today's rule 56.8 % (fair) / 54.8 % (priced); with the ≥ 0.85 Banko and p ≥ 0.55: 60.2 % on 76 % of matches. Market-ranked 1X2/double chance ≥ 1.60: 49.45 % | [S][L][V] |
| Profit | None expected against the closing line. Value bets −9.4 %; Oranlı −2.9 % … −7.1 %; published profits come from soft-book outliers and led to account limits (Kaunitz et al. 2017) | [L][S] https://arxiv.org/pdf/1710.02824 |
| Live record so far | Banko 5/7 and Oranlı 5/7, each 90 % CI 40.9–90.0 %; paired per match, not independent | [LIVE][R] |

---

## 6. How to verify each step

**The test split is used up.** The "fit on train, choose on validation, score test once" protocol can no longer use the
2026-02-01 … 2026-10-12 test split: it has been read many times (see the caveat at the top).
- **Fresh holdout:** matches after 2026-10-12, scored by a frozen model or rule, or the tracker's forward results.
- Resolving about 0.002 log loss needs at least 2,000 matches [L]. At the test period's rate (3,402 matches in 254 days,
  about 400 a month) that is about 5 months [V].
- Model steps (A2, A3, A4, A8): freeze the change, score the fresh holdout once, paired bootstrap. Deploy only if the CI
  upper bound is below 0 and UEFA is not worse [T14]. For A2 a smaller cheap check is acceptable because the change is
  small and reversible: watch UEFA draw rates and log loss on new UEFA matches.
- Alternatively for A3: a rolling-origin re-validation on train+validation only.

**Selection steps (B).**
- **The tracker must report each rule version separately first (step T).** Today it does not: `report.py` mixes all
  versions in a 30-day summary [V].
- Then bump `RULE_VERSION` for every rule change, and judge a rule only after about 300 settled Bankos [R] (around
  April–May 2027 for the ≥ 0.85 rule in the 13 tracked competitions [V]).
- Report the Banko and the Oranlı separately; their expected rates differ (about 90 % vs about 60 %).

**Odds steps (C, A5, B3).** Before A5 goes live:
- archive every snapshot with its timestamp and source;
- re-run [L]'s `sota_model_vs_market.py` on the archived odds;
- check that the Iddaa-price matches de-vig the same way;
- confirm B3's market ranking on archived matches that were not in the test split.

---

## 7. Leads found but not evaluated

- **odds-api.io.** A bookmaker list from odds-api.io (`backend/data/research/odds_samples/oddsapiio_bookmakers_public_2026-10-15.json`).
  `docs/research/2026-10-15-odds-sources.md` notes that its public list includes Iddaa, that new free keys are paused,
  and that the cheapest paid plan is £49/month; coverage cannot be confirmed without a key. Not checked here: terms of
  use, league coverage, history, and Turkish-law compliance. Do not build on it before these checks.

**Dropped lead: FotMob `matchOdds`.** The probe (`backend/data/research/odds_samples/fotmob_matchOdds_probe.json`)
returned `null` for TUR and USA. Odds came back only with the country code set to GBR, DEU or ESP, and those payloads are
bookmaker affiliate promotions (promo text and affiliate links for Betfred, Tipico, Bet365). Requesting another country's
odds from Turkey works around a deliberate geo-restriction; showing that content in Turkey risks Law 7258 Art. 5
(secondary source above); and FotMob's robots.txt disallows `/api/*` for generic agents [V]. Do not use it.

---

## 8. What changed in this revision (after review [V])

- **Test-split reuse** is now stated at the top: gains of the promoted steps are optimistic; A2, A3 offsets, A4 and B3
  need a fresh holdout. Section 6 no longer relies on "score test once".
- **A1:** −0.0043 was the whole XI layer vs no layer, not the benefit of waiting for confirmed line-ups. That benefit is
  unmeasured; A1 is now a UI/process step (score 6 → 2).
- **A6:** the "+2.5–3.5 points" was the calibration gap, not Shin's effect. Shin moves favourites +1 to +2 points; A6 is
  folded into A5.
- **B3:** "+4.9 points" was a non-frozen test result 3.7 times the design estimate; now "+1 to +2 points at the same
  coverage", and the 94.5 % is marked as not significantly better than the model (score 2 → 1).
- **A2:** quoted as the pooled validation+test effect (~−0.005 per UEFA match, ~−0.0004 overall); "helps in every stage"
  replaced.
- **B2:** numbers now assume the new Banko rule (57.9 % → 60.2 % on 76 % of matches); B1, B2 and the B4 line ship as one
  rule version.
- **B1:** the 90 % is scoped to the tested competitions; tracker grouping by rule version (T) added as a required step;
  two-tier display is the default.
- **C1:** confidence medium; starts on day 1 in parallel, scoped to the 13 tracked competitions and one daily pull;
  Sportmonks cost corrected to €99/month; legal note added; [D]'s API-Football claims marked as not re-verified.
- **A3 / A4:** moved after the runtime feature pipeline (weeks, not today); A4 limited to league matches; A3 offsets'
  validation weakness and untested additivity stated.
- **A7:** gain marked as unmeasured for morning → T-60; needs a near-real-time paid source (score 3 → 0.7).
- **B4:** the combined probability is already shown; only the historical rate is new; expectation is the product
  (~70 % for 3 legs), not the realised 75.4 %.
- **B5 / live record:** 300 Bankos take ~204 calendar days (around April–May 2027), not ~100 days; Banko and Oranlı live
  intervals reported separately.
- **Summary and ceilings:** "+~1 point" now derived from the model-to-market gap (+0.9, up to +1.75 in the top 5);
  2017/2023 literature comparison corrected; "CatBoost" wording fixed (not run); "20 lig" → 20 competitions (17 leagues
  + 3 UEFA); Oranlı cap stated only for the fair-price path; O/U "cap" removed.
- **FotMob:** robots.txt risk stated; `matchOdds` lead dropped.

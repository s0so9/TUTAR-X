# Favori kalibrasyonu: üretim 1X2 modeli favorilerde aşırı güvenli mi? — 14 Ekim 2026

## Özet (Türkçe)

**Soru (sahibi):** "Sistem Aston Villa ve Man City gibi büyük takımları fazla güçlü değerlendiriyor." Bu gece Villa'ya
%59 (Fenerbahçe, iç saha; Villa son 5 iç sahanın 3'ünü kaybetmişti), City'ye %66 (PSG, iç saha) verildi.

**Cevap: Veri bu şikâyeti desteklemiyor. Üretim modeli favorilerde sistematik olarak aşırı güvenli DEĞİL; tersine, geçmişte
favorileri çoğunlukla olduğundan biraz DÜŞÜK değerlendirmiş.** Bu yüzden "favorileri aşağı çeken" bir kalibrasyon katmanı
önermiyorum, hiçbir aday düzeltme de test kriterini geçmedi. **Canlıya alma: HAYIR.**

- **Veri.** Üretim modelinin örneklem-dışı 1X2 tahminleri, 19.985 maç (2022-08 → 2026-10-12). Teşhis yalnızca eğitim +
  doğrulama dönemlerinde yapıldı (16.583 maç, 1.741'i UEFA); test dönemi (3.402 maç, 171 UEFA) düzeltme dondurulduktan sonra
  **bir kez** okundu.
- **Lig maçları (14.842).** Favoriler tahmin edilenden daha sık kazandı: %60-70 bandında tahmin 0,646 / gerçek 0,686,
  %70-80'de 0,743 / 0,778, %80-90'da 0,837 / 0,869; favori olasılığı ≥ %70 olanlarda tahmin 0,765, gerçek 0,798 (%90 GA
  0,779-0,817). Kalibrasyon eğimi 1,17 (1'den büyük = *düşük* güvenli). Kapanış piyasasıyla (12.085 maç) karşılaştırınca da model
  favorilere piyasadan *daha az* olasılık veriyor (%60-70: −1,7 puan, %70-80: −2,1 puan). Doğrulama döneminde fark küçüldü
  (≥ %70: tahmin 0,766, gerçek 0,772), test döneminde kalibrasyon iyi (%70-80: 0,742 / 0,746; %80-90: 0,838 / 0,830).
- **Avrupa kupaları (1.741).** Genel eğim 0,96 (GA 0,80-1,12), yani ölçülebilir bir aşırı güven yok. Ev sahibi favoriler
  tahminden *daha çok* kazanmış (ev sahibi favori ≥ %70'te tahmin 0,75-0,84 iken gerçek 0,84-0,92), deplasman favorileri
  tahmine yakın. **Premier League kulüpleri:** Avrupa'da favori olarak ≥ %60 verilen 107 maçta tahmin 0,728, gerçek 0,813
  (fark −0,085, %90 GA −0,149 … −0,022); diğer favoriler tahmine yakın (0,697 / 0,710). Yani City / Villa gibi takımlar
  Avrupa'da tarihsel olarak *düşük* değerlendirilmiş. Bu gecenin %59 ve %66'sı, geçmişte aynı bantlardaki Avrupa ev sahibi
  favorilerinin gerçekleşme oranlarının (%63 ve %66) altında/yanında; yani aşırı değil (yalnızca anekdot, ayar için
  kullanılmadı).
- **Aşırı güvenin görüldüğü tek yerler** küçük ve kararsız: test döneminde Avrupa ≥ %70 favoriler (22 maç: tahmin 0,797,
  gerçek 0,727; %90 GA 0,553-0,852 tahmini kapsıyor), eğitim+doğrulamada Conference League %60-70 bandı (105 maç: 0,643 / 0,552),
  Avrupa ≥ %90 bandı (eğitim+doğrulama 10 maç: 0,933 / 0,900; test 4 maç: 0,928 / 0,750). Hiçbiri bağımsız bir dönemde teyit edilmedi.
- **Aday düzeltmeler** (eğitimde fit, yalnızca doğrulamada seçim, 1X2 log loss farkı = sonra − önce, negatif = iyi):

| Aday | Parametre (eğitimde) | Doğrulama genel | Doğrulama UEFA |
|---|---|---|---|
| (a) tek sıcaklık T (tüm maçlar) | T = 0,886 (keskinleştirir) | +0,00089 (kötü) | −0,00092 |
| (a) T lig + T UEFA | 0,889 / 0,869 | +0,00087 (kötü) | −0,00069 |
| (a) yalnız UEFA için T | 0,869 | −0,00008 | −0,00069 |
| (b) UEFA oran küçültme k | k = 1,153 (küçültme değil, genişletme) | +0,00006 | +0,00055 |
| (b) UEFA ev avantajı terimi h | h = +0,155 | **−0,00104** (−0,00203 … +0,00001) | **−0,00892** (−0,01748 … −0,00003) |
| (b) k + h | 1,10 / 0,147 | −0,00093 | −0,00801 |
| (c) favori olasılığı Platt, tüm maçlar | a 0,078, b 1,171 | +0,00104 (kötü) | −0,00064 |
| (c) favori Platt, yalnız UEFA | a 0,156, b 1,004 | −0,00047 | −0,00399 |
| (c) isotonic (67 basamak) | — | +0,00395 (kötü) | +0,01509 |

  Düzleştirme (T > 1; "favorileri aşağı çek") hem eğitimi hem doğrulamayı **kötüleştiriyor** (doğrulama: T=1,1 → 0,98922, T=1,2 →
  0,99145, taban 0,98801). Önceden yazılmış seçim kuralı (1 standart hata, en az parametre) **yalnız UEFA ev avantajı terimi h**
  adayını seçti. Bu terim favorileri düşürmüyor, aksine Avrupa'da ev sahibini yükseltiyor.
- **Test (bir kez okundu; 3.402 maç, 171 UEFA; eşli bootstrap, 2.000 örnek, tohum 7, %90 GA):**

| Ölçü | Önce (üretim) | Sonra (h = +0,155) | Fark (%90 GA) |
|---|---|---|---|
| 1X2 log loss, tüm maçlar | 0,99601 | 0,99642 | +0,00042 (−0,00026 … +0,00110) |
| 1X2 log loss, lig (3.231) | 0,99829 | 0,99829 | 0 (değişmedi) |
| 1X2 log loss, UEFA (171) | 0,95284 | 0,96111 | **+0,00827 (−0,00570 … +0,02210)** |
| 1X2 Brier, tüm / UEFA | 0,59442 / 0,56304 | 0,59468 / 0,56827 | +0,00026 / +0,00523 |

  Ölçüt (genel ya da hedef alt kümede GA üst sınırı < 0) **sağlanmadı**; nokta tahmini de kötüleşme yönünde. Doğrulamadaki
  kazanç testte tutmadı (tarihsel UEFA ev avantajı sinyali var: h dönemlere göre 0,10 → 0,15 → 0,19 → 0,21 artıyor, ama test
  döneminde beraberlik oranı %15 (tahmin %22,7), deplasman galibiyeti %37 (tahmin %32,5): sinyal gürültüye karşı sağlam değil).
  Eğitim+doğrulama ile yeniden fit (h = 0,167) da aynı: UEFA +0,00938 (−0,00571 … +0,02430).
- **Favori ≥ %70 / ≥ %80 (test), önce → sonra:** tüm maçlar ≥ %70: 268 → 272 maç, isabet %76,1 → %76,5; ≥ %80: 60 → 66, %83,3
  → %80,3. UEFA ≥ %70: 22 → 26, isabet %72,7 → %76,9; UEFA ≥ %80: 7 → 13, %85,7 → %69,2 (h bu bantta daha çok maçı
  eşiğin üstüne çıkarıyor). Lig maçları aynen kaldı (≥ %70: 246 maç, %76,4; ≥ %80: 53 maç, %83,0).
- **Tur 2: (d) kulüp başına "Avrupa ofseti" (koordinatör isteği).** Her UEFA maçı için, kulübün yalnızca *önceki* UEFA
  maçlarındaki (gerçek − modelin beklediği) gol farkı (ya da xG farkı) ortalaması, küçültülmüş (k ∈ {3, 6, 12, 24}) ve isteğe bağlı
  zaman sönümlü (yarı ömür yok / 730 gün), log gol oranına `d' = d + h + γ·(ev ofseti − deplasman ofseti)` olarak ekleniyor;
  γ eğitimde fit, 16 ayar doğrulamada. Sonuç: **kulüp başarısı kalıcı değil.** Doğrulamada tek başına ofsetin 16 ayarının
  hiçbiri kazanç getirmedi (UEFA fark +0,00000 … +0,00113), eğitimde fit edilen γ ≈ 0 (gd metriğinde hafif negatif, xG
  metriğinde +0,005 … +0,09). Sonraki maç artığının ofset üzerindeki eğimi: gd için eğitim 0,01 ± 0,11, doğrulama 0,11 ± 0,19
  (0 ile uyumlu); xG için eğitim +0,16, doğrulama −0,15 (işaret değişiyor). Yani Real Madrid / PSG / Bayern'in geçmişteki
  fazla performansı (PSG +39,1 gol farkı, 55 maç; Real Madrid +27,2 / 54; Bayern +26,5 / 51; Dortmund +22,1; Villa +15,0 / 40; City −4,8
  / 44; Fenerbahçe −8,1 / 41) bir sonraki maçı öngörmüyor. h ile birlikte (d)+h, tek başına h ile aynı (doğrulama genel −0,00106
  vs −0,00104). Önceden yazılmış seçim kuralı, tur 1'in h adayına çok benzeyen (d)+h adayı eklenince "en iyi"yi ona kaydırdı
  ve 1-SE kuralı **k + h** (2 parametre; k = 1,10, h = +0,147) adayını seçti; bu bir kural artefaktı (iki aday neredeyse aynı),
  yine de kurala uyuldu. **Test (ikinci okuma; 171 UEFA):** (d) tek başına UEFA −0,00002 (−0,00009 … +0,00006); (d)+h
  +0,00817 (−0,00591 … +0,02199); seçilen k + h +0,01006 (−0,00535 … +0,02476), genel +0,00051 (−0,00022 … +0,00128): üçü de
  ölçütü geçmedi. **Bu geceki maçlar (yalnızca örnek, ayar için kullanılmadı):** City 65,6 / 19,3 / 15,1 → (d) tek başına 65,6;
  (d)+h 69,6; yalnız h 69,8; sıcaklık T = 0,886 → 69,4; k + h 71,8. Villa 59,4 / 21,5 / 19,1 → (d) 59,4; (d)+h 64,2; yalnız h 64,0;
  k + h 65,7. Yani doğrulamada tutan adayların hepsi City ve Villa'yı *yukarı* çekiyor, (d) ise hiçbir şeyi değiştirmiyor.
  **Not:** test dönemi bu turda ikinci kez okundu; (d) fikri tüm UEFA maçlarından (test dönemi dahil) gelen kulüp başarı
  tablosundan doğduğu için bağımsız sayılmaz; tasarım (metrik, k ve yarı ömür ızgarası) hiçbir (d) sayısı hesaplanmadan önce
  yazıldı ve bu aşama test satırlarını okumuyor.
- **Öneri.** (1) Hiçbir kalibrasyon katmanı (h, k + h, sıcaklık, favori Platt, kulüp ofseti) canlıya alınmasın; `backend/config` ve `app/` değiştirilmedi. (2) Modelin favorilere
  verdiği olasılıklar, geçmiş verinin gösterdiği gerçekleşme oranlarıyla uyumlu; "büyük takımlar fazla güçlü" izlenimi bu
  veriden doğrulanmıyor. (3) Bu gecenin tek tek maçlarındaki (Villa'nın iç saha formu gibi) bilgi modele kısmen `lineup_form` ile
  giriyor; son 5 iç saha sonucu eklenirse kazanç olup olmadığı ayrı ve önceden yazılmış ölçütlerle test edilmeli. (4) Avrupa
  örneklemi küçük (171 test, 1.741 eğitim+doğrulama); ≥ 1.000 test maçı birikmeden Avrupa'ya özel bir ayar yapılmamalı. (5) UI'da
  favori ≥ %70 gösterimleri için not: lig maçlarında isabet tahminin altında değil; Avrupa ≥ %70 için güven aralığı geniş.
- **Dikkat edilecekler.** Taban = üretim modelinin eğitim-dönemi gol katmanıyla yeniden üretilmiş hâli; üretimin `beta` / `gamma`
  katsayıları Ocak-Haziran 2026'da fit edildiği için doğrulamanın Ocak'ı ve testin Şubat-Haziran'ı onlar için örneklem-içi (taban
  hafif avantajlı). Kapanış oranı yalnızca lig maçlarında var; Avrupa için piyasa karşılaştırması yapılamadı. Kullanılan
  favori tanımı: 1X2'de en yüksek olasılıklı sonuç (beraberlik hiç favori olmadı).

Yeniden çalıştırma ve ayrıntılar aşağıda (İngilizce; tur 2 için bölüm 7).

---

## Details (English)

### 1. Question, data, rules

- Question: is the production 1X2 model systematically over-confident on favourites, and where (UEFA vs league, cross-league
  matches such as Premier League clubs vs other leagues, home favourites, favourite-probability bands); fix with a calibration
  layer **if and only if** the fix holds on held-out data.
- Data: `backend/data/training/baseline_predictions_full.csv.gz` (the production model, walk-forward rating lambdas, **train-only
  goal layer**, out-of-sample; 19,985 matches with a lambda and a result). The 1X2 columns were re-derived from `mu_home` /
  `mu_away` with the goal layer (NB x Dixon-Coles, max |diff| 7e-7). Splits: train 2022-08-01..2025-06-30 (13,187; 1,345 UEFA),
  validation 2025-07-01..2026-01-31 (3,396; 396 UEFA), test 2026-02-01..2026-10-12 (3,402; 171 UEFA). UEFA rows are the
  Champions / Europa / Conference League (ids 42 / 73 / 10216); there are no qualifier rows. No network, DB read-only (only to map
  football-data `db_match_id` to FotMob ids for the closing odds), `backend/app/**` and `backend/config/**` untouched.
- Procedure: (1) diagnosis on train + validation only (`calibration_diagnose.py`); (2) fit candidates on **train**, choose on
  **validation** only, write the frozen choice (`calibration_fit.py`; the test rows are dropped right after loading, and the
  evaluate stage refuses to run without the frozen file); (3) read the **test split once** (`calibration_evaluate.py`).
  Favourite = outcome with the largest 1X2 probability (a draw was never the favourite in the 19,985 rows).
  Intervals: observed rates use Wilson 90 %; differences use a paired bootstrap, 2,000 resamples, seed 7, resampled within
  each subset (overall / league / UEFA).

### 2. Diagnosis (train + validation, 16,583 matches)

Favourite win probability by band (pred = mean predicted, obs = observed rate, Wilson 90 % CI; gap = pred − obs, negative =
under-confident):

| Segment | Band | n | pred | obs | 90 % CI | gap |
|---|---|---|---|---|---|---|
| All | < 0.50 | 8,614 | 0.430 | 0.435 | 0.426-0.444 | −0.005 |
| | 0.50-0.60 | 4,156 | 0.546 | 0.566 | 0.553-0.579 | −0.020 |
| | 0.60-0.70 | 2,336 | 0.646 | 0.681 | 0.665-0.697 | −0.036 |
| | 0.70-0.80 | 1,132 | 0.744 | 0.781 | 0.760-0.800 | −0.037 |
| | 0.80-0.90 | 324 | 0.838 | 0.876 | 0.843-0.903 | −0.039 |
| | ≥ 0.90 | 21 | 0.929 | 0.905 | 0.749-0.968 | +0.024 |
| League | 0.50-0.60 | 3,724 | 0.546 | 0.564 | 0.550-0.577 | −0.018 |
| | 0.60-0.70 | 2,031 | 0.646 | 0.686 | 0.669-0.703 | −0.040 |
| | 0.70-0.80 | 969 | 0.743 | 0.778 | 0.755-0.799 | −0.035 |
| | 0.80-0.90 | 260 | 0.837 | 0.869 | 0.831-0.900 | −0.032 |
| | ≥ 0.90 | 11 | 0.925 | 0.909 | 0.677-0.980 | +0.016 |
| UEFA | 0.50-0.60 | 432 | 0.547 | 0.583 | 0.544-0.622 | −0.036 |
| | 0.60-0.70 | 305 | 0.644 | 0.652 | 0.606-0.696 | −0.008 |
| | 0.70-0.80 | 163 | 0.746 | 0.797 | 0.741-0.844 | −0.051 |
| | 0.80-0.90 | 64 | 0.839 | 0.906 | 0.829-0.951 | −0.068 |
| | ≥ 0.90 | 10 | 0.933 | 0.900 | 0.652-0.977 | +0.033 |

Calibration fit "favourite won ~ a + b logit(p_fav)" (b < 1 over-confident): league b = 1.173 (90 % CI 1.109-1.237); UEFA
b = 0.961 (0.798-1.125); league train 1.192, league validation 1.099 (0.959-1.238). Favourites ≥ 0.70: league n = 1,240,
pred 0.765, obs 0.798 (gap −0.034, bootstrap CI −0.052 … −0.014); UEFA n = 237, pred 0.779, obs 0.831 (CI of the gap
−0.092 … −0.013). Per-competition league slopes range 0.54 (Danish, n = 300) to 1.47 (Liga Portugal); no league has a stable
over-confidence.

Where (UEFA, train + validation; a "−" gap = favourites win more than predicted):

| Cut | n | Finding |
|---|---|---|
| Home favourite (UEFA) | 1,046 | slope 0.87 (0.66-1.07); obs above pred in every band except ≥ 0.90: 0.50-0.60 pred 0.547 / obs 0.628; 0.70-0.80 0.747 / 0.839; 0.80-0.90 0.840 / 0.924 |
| Away favourite (UEFA) | 695 | calibrated to slightly over-confident, all within noise: 0.50-0.60 0.546 / 0.512; 0.70-0.80 0.744 / 0.689 (n = 45) |
| Champions / Europa / Conference | 583 / 615 / 543 | CL under-confident (0.60-0.70: 0.645 / 0.737); EL mixed; **Conference 0.60-0.70: 0.643 / 0.552 (n = 105)** is the one significant over-confident cell |
| Favourite from the Premier League | 266 | 0.50-0.60 0.549 / 0.671 (n = 79); 0.60-0.70 0.645 / 0.780 (n = 50); favourite ≥ 0.60: n = 107, pred 0.728, obs 0.813 (gap −0.085, CI −0.149 … −0.022) |
| Favourite from another top-5 league | 702 | calibrated at 0.60-0.70 (0.644 / 0.651), under-confident above 0.70 |
| Favourite from another covered league | 550 | slightly over-confident at 0.60-0.80 (0.647 / 0.613; 0.741 / 0.714), within noise |
| Favourite's league not covered by the data | 223 | n too small per band |
| Other (non-PL) favourite ≥ 0.60 | 435 | pred 0.697, obs 0.710 (gap −0.013, CI −0.050 … +0.022) |

The favourite's domestic league is the league of the club's most recent earlier domestic match in the feature file (clubs of
uncollected leagues are "not covered", never guessed).

Closing market (league matches with odds, 12,085 train + validation; no European closing odds exist): model 1X2 log loss
0.97834, market 0.96068. Favourite probability, model vs market for the same outcome: band 0.60-0.70 model 0.646, market
0.663 (diff −0.017, CI −0.020 … −0.015), observed 0.690; 0.70-0.80 model 0.743, market 0.764 (−0.021), observed 0.786;
0.80-0.90 model 0.837, market 0.837, observed 0.852. Calibration slope: model 1.19, market 1.08 (the de-vigged market is also
slightly under-confident on favourites). Ie the market gives favourites *more* than the model, not less.

Tonight's snapshot (`docs/live-tests/2026-10-14/system_picks.json`; anecdote only, nothing tuned on it): Villa 59 / 22 / 19,
City 66 / 19 / 15. In the history above, UEFA home favourites in the 0.50-0.60 / 0.60-0.70 bands won 62.8 % / 65.5 % of
the time (Premier League favourites 67.1 % / 78.0 %).

### 3. Candidate fixes (fit on train, selected on validation)

Definitions (`calibration_fixes.py`): temperature `p_i' ∝ p_i^(1/T)`; ratio change for UEFA matches
`d = ln(mu_h/mu_a); d' = k d + h; mu_h' = (mu_h+mu_a) e^d'/(1+e^d'), mu_a' = (mu_h+mu_a)/(1+e^d')` (total goals kept, 1X2
recomputed with the production score model); favourite recalibration `logit q' = a + b logit q`, the other two outcomes keep
their ratio; isotonic comparator. Selection rule, written into the script before it ran: eligible = point estimate of the change
in league **and** UEFA log loss ≤ +0.0003; best = lowest validation overall log loss; one-standard-error rule with the identity
("no fix") taking part, fewest parameters wins among ties.

Validation 1X2 log loss (baseline 0.98801 overall, 0.99607 league, 0.92694 UEFA); the table above in the Turkish summary has
the differences and parameters. Selection trace: best = UEFA home term (0.98697); tied within 1 SE: itself, k + h (0.98708),
Platt UEFA-only (0.98755); identity gap 0.00104 vs SE 0.00061 (not tied); chosen: **`uefa_home_h`, h = +0.1551** (1 parameter,
UEFA only). Train-only diagnostics (not used for choosing): temperature sweep (train log loss minimum near T = 0.90,
0.97061 vs 0.97204; validation minimum near T = 0.95-1.00, T = 1.1 → 0.98922, T = 1.2 → 0.99145; UEFA validation minimum
near T = 0.90); the home term fitted per period: 2022-23 0.104 (n = 407), 2023-24 0.155 (407), 2024-25 0.194 (531), 2025-26
validation 0.211 (396); per competition CL 0.123, EL 0.223, Conference 0.150. Why the owner's hypothesis cannot be a calibration
fix: the temperature fitted on train sharpens (T = 0.886) and fails on validation; the ratio change fitted on UEFA train
expands (k = 1.153) instead of shrinking and shows no validation gain; flattening makes every split worse.

### 4. Test (read once; fix frozen in `calibration_frozen.json` at selection time)

| Segment | n | 1X2 log loss before | after | diff (90 % CI) | Brier diff (90 % CI) |
|---|---|---|---|---|---|
| all | 3,402 | 0.99601 | 0.99642 | +0.00042 (−0.00026 … +0.00110) | +0.00026 (−0.00020 … +0.00073) |
| league | 3,231 | 0.99829 | 0.99829 | 0 (rows unchanged) | 0 |
| UEFA | 171 | 0.95284 | 0.96111 | +0.00827 (−0.00570 … +0.02210) | +0.00523 (−0.00445 … +0.01482) |
| UEFA, Champions League | 63 | 0.87349 | 0.86677 | −0.00671 (−0.02740 … +0.01455) | |
| UEFA, Europa League | 63 | 0.98636 | 1.00446 | +0.01810 (−0.00581 … +0.04215) | |
| UEFA, Conference League | 45 | 1.01701 | 1.03249 | +0.01548 (−0.01275 … +0.04284) | |

Train + validation refit (h = 0.1674; declared before the test, not used for choosing): all +0.00047 (−0.00025 … +0.00122),
UEFA +0.00938 (−0.00571 … +0.02430). UEFA shares on test: predicted H / D / A before 0.447 / 0.227 / 0.325, after 0.490 / 0.224
/ 0.286, actual 0.474 / 0.152 / 0.374 (the test period has unusually few UEFA draws; 26 of 171). Goal markets with the same total
goals: O/U 2.5 changes by at most 9.5e-5; BTTS by 0.017 on average (max 0.041); if mu' replaced mu everywhere, UEFA test log
loss would change by BTTS −0.0026 (−0.0076 … +0.0027) and exact score +0.0015 (−0.0163 … +0.0180).

**Deploy criterion** (written before the test: 1X2 log loss CI upper bound < 0 overall or on the targeted subset, rest not
worse): overall upper +0.00110, UEFA upper +0.02210 → **not met → do not deploy.** `calibration_candidate.json` carries the
formula, parameters, validation choices, test results and this verdict (DRAFT; no config / app file written).

Calibration of the favourite's win probability on **test, before the fix** (the production probabilities):

| Segment | Band | n | pred | obs | 90 % CI |
|---|---|---|---|---|---|
| League | 0.50-0.60 | 844 | 0.543 | 0.536 | 0.507-0.564 |
| | 0.60-0.70 | 433 | 0.644 | 0.677 | 0.639-0.713 |
| | 0.70-0.80 | 193 | 0.742 | 0.746 | 0.691-0.794 |
| | 0.80-0.90 | 53 | 0.838 | 0.830 | 0.730-0.898 |
| UEFA | 0.50-0.60 | 45 | 0.544 | 0.622 | 0.500-0.731 |
| | 0.60-0.70 | 26 | 0.640 | 0.654 | 0.493-0.786 |
| | 0.70-0.80 | 15 | 0.753 | 0.667 | 0.455-0.827 |
| | ≥ 0.80 | 7 | 0.890 | 0.857 | 0.548-0.968 |
| UEFA, Premier League favourite | 0.60-0.70 | 10 | 0.649 | 0.800 | 0.541-0.931 |

Favourites at or above a threshold, test, before → after (n, observed rate, mean predicted): all ≥ 0.70: 268 (0.761, 0.765) →
272 (0.765, 0.766); ≥ 0.80: 60 (0.833, 0.844) → 66 (0.803, 0.842); league ≥ 0.70 / ≥ 0.80 unchanged: 246 (0.764, 0.763) / 53
(0.830, 0.838); UEFA ≥ 0.70: 22 (0.727, 0.797) → 26 (0.769, 0.802); UEFA ≥ 0.80: 7 (0.857, 0.890) → 13 (0.692, 0.858). League
test matches with closing odds (2,234): market 0.99213, model 1.0057; model favourite mean 0.512, market for the same outcome
0.507, observed 0.505.

### 5. Files and reproduction

| File (under `backend/` unless noted) | Content |
|---|---|
| `scripts/training/calibration_common.py` | loading, Wilson / paired bootstrap, favourite bands, closing-odds loader |
| `scripts/training/calibration_fixes.py` | the candidate fixes, fitters, `apply_fix` |
| `scripts/training/calibration_diagnose.py` | diagnosis (train + validation) → `data/training/calibration_diagnosis.json` |
| `scripts/training/calibration_fit.py` | select stage → `data/training/calibration_frozen.json` (candidates, validation numbers, selection trace) |
| `scripts/training/calibration_evaluate.py` | test stage (single read; `--split validation --outdir <dir>` is a mechanics check only) → `data/training/calibration_test_results.json`, `data/training/calibration_candidate.json`, `data/training/calibration_evaluate_stdout.txt` |
| `scripts/training/calibration_offset.py` | round 2: as-of club offsets (no look-ahead), runtime table |
| `scripts/training/calibration_fit_d.py` | round 2 select stage → `data/training/calibration_frozen_round2.json` |
| `scripts/training/calibration_evaluate_d.py` | round 2 test stage (second test read) → `data/training/calibration_test_results_round2.json`, final `data/training/calibration_candidate.json` (round 1 kept in `calibration_candidate_round1.json` and nested under `round1`), `calibration_evaluate_d_stdout.txt` |
| `tests/test_calibration_candidate.py` | 19 tests, synthetic fixtures (labelled), fixes / fitters / offsets (no look-ahead, shrinkage) / split isolation / candidate JSON |

Commands (from `backend/`, 2 threads): `venv/Scripts/python.exe scripts/training/calibration_diagnose.py` (4 s),
`calibration_fit.py` (13 s), `calibration_evaluate.py` (a few seconds).

### 6. Caveats

- Baseline = production model with the **train-only** goal layer; the production `beta_domestic` 0.0279 and `gamma` 0.2157 were fitted
  on Jan-Jun 2026 and so overlap validation (January) and test (Feb-Jun): the baseline is slightly in-sample there.
- UEFA samples are small (171 test; 396 validation); the interval on the UEFA test change (±0.014) is wider than any effect found.
- The diagnosis looks at train + validation and is exploratory; the tables on the test split are descriptive only.
- The calibration "slope > 1" in league matches shrinks over time (train 1.19, validation 1.10, test within noise of 1); it is
  not a stable defect that a fixed layer could remove, and the closing market shows a similar (smaller) pattern.
- No form-at-home or opponent-specific signal was tested; the Villa / City anecdotes cannot be evaluated with these data.
- The evaluate stage was run twice on the same frozen choice; the second run only extended the wording of the recommendation
  and added the diagnosis summary to the candidate JSON (all test numbers byte-identical, checked).

### 7. Round 2: candidate (d), per-club European offset

Added at the coordinator's request after round 1 had read the test split once. Evidence for the idea (from all UEFA matches
2022-08..2026-10, test period included): actual minus model-expected goal difference per club: PSG +39.1 over 55 matches, Real
Madrid +27.2 (54), Bayern +26.5 (51), Dortmund +22.1 (46), Aston Villa +15.0 (40), Arsenal +14.4 (48), Liverpool +14.2 (41),
Sporting -0.5 (45), Man City -4.8 (44), Fenerbahce -8.1 (41). (These are hindsight sums; the fix may only use what was known
at kick-off.)

Candidate: `calibration_offset.py` (as of kick-off, UEFA matches only, a past match counts only if it started at least 3 h earlier).
Offset of a club = sum(w r) / (sum(w) + k) over its previous UEFA matches, r = (actual - expected) goal difference ("gd") or
(xG difference - expected goal difference) ("xgd", matches without xG skipped, never imputed), w = 1 or half-life 730 d. Fix:
`d' = d + h + gamma (offset_home - offset_away)` with total goals kept (same machinery as the home term). gamma (and h) fitted on
train UEFA rows, grid of 16 cells (metric {gd, xgd} x k {3, 6, 12, 24} x decay {none, 730 d}) judged on validation. Tuned
hyper-parameters count as parameters in the tie-break (offset 4, offset + h 5).

Validation (baseline overall 0.98801; differences after - before):

| Candidate | fitted | Overall | UEFA |
|---|---|---|---|
| offset alone, best cell (xgd, k = 24, no decay) | gamma = 0.005 | +0.00000 (-0.00001 ... +0.00001) | +0.00000 (-0.00004 ... +0.00005) |
| offset alone, all 16 cells | gamma -0.095 ... +0.093 | +0.00000 ... +0.00113 | no cell below 0 |
| offset + h, best cell (gd, k = 3, half-life 730 d) | gamma = 0.0094, h = 0.1553 | -0.00106 (-0.00205 ... -0.00000) | -0.00909 (-0.01765 ... -0.00024) |
| h alone (round 1) | h = 0.1551 | -0.00104 (-0.00203 ... +0.00001) | -0.00892 (-0.01748 ... -0.00003) |

Persistence (train + validation, descriptive): OLS slope of the next residual on z (a slope of about 1 would mean the
offset predicts the next match): gd, k = 6: train 0.012 (SE 0.107), validation 0.114 (SE 0.192); gd with decay 0.019 / 0.087; xgd,
k = 6: train 0.165 (SE 0.102), validation -0.148 (SE 0.205). Past over-performance does not carry into the next match.
Offsets as of 2026-10-14 (gd, k = 6, no decay): PSG +0.64 (55 matches), Bayern +0.47 (51), Real Madrid +0.45 (54), Dortmund +0.43,
Aston Villa +0.33 (40), Liverpool +0.30, Arsenal +0.27, Sporting -0.01, Man City -0.10 (44), Fenerbahce -0.17 (41); the full table of the
offset + h representative is in `calibration_test_results_round2.json` (`offsets_as_of_2026_10_14`; not put in the candidate
JSON because (d) was not chosen).

Selection (same pre-declared rule, round-1 candidates + the two (d) representatives): best = offset + h (0.98695); tied within 1 SE:
k + h (2 params), Platt UEFA-only (2), offset + h (5); h alone is NOT tied this time (gap 2e-5 against an SE of 2e-5, because
offset + h is h plus a near-zero term, so the paired differences are almost identical): the rule picks **k + h** (k = 1.1035, h =
0.1466). That is a quirk of the 1-SE rule with near-duplicate candidates, not a finding; it was followed as declared.

Test, second read (3,402 matches, 171 UEFA; list frozen in `calibration_frozen_round2.json` before the read; 1X2 log loss
after - before, 90 % paired bootstrap CI):

| Candidate (params from train) | Overall | League | UEFA |
|---|---|---|---|
| offset alone (xgd, k = 24; gamma = 0.0047) | -0.00000 (-0.00000 ... +0.00000) | 0 | -0.00002 (-0.00009 ... +0.00006) |
| offset + h (gd, k = 3, half-life 730 d; gamma = 0.0094, h = 0.1553) | +0.00041 (-0.00026 ... +0.00110) | 0 | +0.00817 (-0.00591 ... +0.02199) |
| **k + h (chosen by the rule; k = 1.1035, h = 0.1466)** | +0.00051 (-0.00022 ... +0.00128) | 0 | +0.01006 (-0.00535 ... +0.02476) |
| h alone (round 1) | +0.00042 (-0.00026 ... +0.00110) | 0 | +0.00827 (-0.00570 ... +0.02210) |

None meets the deploy criterion; the offset alone is a no-op because its fitted coefficient is about 0.

Illustration for tonight (production snapshot probabilities of `snapshots_pre/`, home / draw / away; ratio-based candidates are
applied as snapshot + (fix(mu) - recomputed(mu)); not used for any choice). Man City - PSG (mu 2.212 / 0.958; offsets City -0.10, PSG
+0.30 in the offset cell, -0.26 / +0.75 in the offset + h cell): production 65.6 / 19.3 / 15.1; T = 0.886 (all) 69.4; T split / UEFA-only 70.0;
Platt all 69.8, Platt UEFA 69.1; ratio k alone 69.1; home h 69.8; k + h 71.8; offset 65.6; offset + h 69.6. Aston Villa - Fenerbahce (mu 1.996 /
1.037; offsets Villa -0.09 / Fenerbahce -0.12 in the offset cell, +0.47 / -0.19 in the offset + h cell): production 59.4 / 21.5 / 19.1; T all
62.7; T split / UEFA-only 63.3; Platt all 62.8, Platt UEFA 63.2; k alone 62.4; h 64.0; k + h 65.7; offset 59.4; offset + h 64.2. Every candidate that
validation favoured raises the home favourite; the offset is neutral. (Recomputed baselines with the train-only goal layer differ from
the snapshots by at most 0.002.)

Caveats of round 2: the test split has now been read twice (round 1: home term; round 2: the three listed candidates); the verdicts are
unchanged either way. The (d) idea comes from a hindsight table that includes the test period; the design was declared before any (d)
number was computed and the select stage reads no test row. `calibration_fit.py` was refactored (`select_candidate`) and re-run after
round 1: its frozen content is identical (first freeze 2026-10-14T19:05:20Z, rewritten at 19:16Z with the same choice and numbers).

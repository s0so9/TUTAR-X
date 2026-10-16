# Props modeli (sarı kart, korner, şut, isabetli şut) - 2026-10-14

Durum: ADAY model, canlıya alınmadı. Dosya: `backend/data/training/props_model_candidate.json` (sürüm `props_v1`). Bu sayfa önce Türkçe özet, sonra İngilizce ayrıntıdır. Tüm sayılar `props_model_report.json` dosyasından otomatik üretildi (`backend/scripts/training/props_make_report.py`).

## Özet (Türkçe)

**Ne yapıldı.** 5 sayı istatistiği için (sarı kart, korner, toplam şut, isabetli şut, faul) negatif-binom sayma modeli kuruldu: her takımın hücum ve savunma (rakibe verdiği) etkisi, lig seviyesi, ev sahibi avantajı, kart/faul için hakem etkisi; zamanla azalan ağırlık ve ridge büzülmesi (az maçı olan takım lig ortalamasına çekilir). Test döneminde (2026-02-01 .. 2026-10-12, 3,402 maç) model her 14 günde yeniden eğitildi ve her tahmin yalnızca maç öncesi veriyle yapıldı. Hiçbir eksik veri sıfır sayılmadı, dışarıda bırakıldı. Ayar (yarı ömür, büzülme, hangi etkiler) sadece doğrulama döneminde seçildi, test bir kez okundu.

**Hangi marketler tahmin edilebilir.** Ölçü: log loss (düşük iyi), en iyi basit yönteme göre (son-5, son-10, 365 gün ortalaması, lig ortalaması; hangisi o markette en iyiyse) fark ve %90 güven aralığı. Fark negatifse model daha iyi.

| Market | Model | Son-5 ort. | Model - son-5 [%90 GA] | En iyi basit yöntem | Model - en iyi basit [%90 GA] | Sonuç |
|---|---|---|---|---|---|---|
| Toplam sarı kart | 0.5825 | 0.6118 | -0.0292 [-0.0360, -0.0222] | 365 gün ort. 0.5869 | -0.0044 [-0.0073, -0.0015] | zayıf (küçük ama anlamlı) |
| Takım sarı kart | 0.5553 | 0.5813 | -0.0260 [-0.0303, -0.0215] | 365 gün ort. 0.5625 | -0.0072 [-0.0091, -0.0052] | zayıf (küçük ama anlamlı) |
| Toplam korner | 0.6313 | 0.6503 | -0.0190 [-0.0240, -0.0138] | 365 gün ort. 0.6360 | -0.0046 [-0.0066, -0.0027] | zayıf (küçük ama anlamlı) |
| Takım korner | 0.5751 | 0.6143 | -0.0392 [-0.0441, -0.0341] | 365 gün ort. 0.5948 | -0.0197 [-0.0228, -0.0165] | orta |
| Takım şut | 0.5185 | 0.5626 | -0.0442 [-0.0499, -0.0387] | 365 gün ort. 0.5521 | -0.0337 [-0.0380, -0.0295] | güçlü |
| Toplam şut | 0.5321 | 0.5493 | -0.0171 [-0.0221, -0.0120] | son-10 0.5423 | -0.0101 [-0.0138, -0.0061] | orta |
| Takım isabetli şut | 0.5739 | 0.6156 | -0.0417 [-0.0472, -0.0363] | 365 gün ort. 0.5961 | -0.0222 [-0.0260, -0.0186] | güçlü |
| Toplam isabetli şut | 0.6145 | 0.6346 | -0.0202 [-0.0256, -0.0147] | 365 gün ort. 0.6185 | -0.0040 [-0.0060, -0.0020] | zayıf (küçük ama anlamlı) |

- **Güçlü (en iyi basit yöntemden >= 0.02 log loss daha iyi):** Takım şut, Takım isabetli şut. **Daha zayıf kazanç:** Toplam sarı kart, Takım sarı kart, Toplam korner, Takım korner, Toplam şut, Toplam isabetli şut.
- **Son-5 sezgisine karşı:** 8 marketin 8 tanesinde model son-5 ortalamasından anlamlı biçimde iyi (güven aralığı sıfırı içermiyor); kazanç 0.017 ile 0.044 log loss arasında. Son-5 en kötü basit yöntemlerden biri: 5 maç gürültülü, rakibi hesaba katmıyor.
- **"Barcelona çok şut atar ama rakibe bağlı":** takım şutunda model, son-5 ortalamasının (0.5626) ve lig ortalamasının (0.5728) belirgin üstünde (0.5185). Beklenen şut sayısı hatası (MAE, takım başına): model 3.74, son-5 4.08, lig ort. 4.17. Rakip etkisi "baskınlık" terimiyle giriyor: güçlü hücumlu takım hem kendi şutunu artırıyor hem rakibinin şutunu azaltıyor (ayrı "savunma" terimi şut/korner/isabetli şut için doğrulamada kazanç eşiğini (0.0003 log loss) geçmediği için seçilmedi; kart ve faulde seçildi).
- **Hakem (kartlar):** hakem etkisi ekleyince log loss toplam kartta -0.0056 [-0.0077, -0.0037], takım kartında -0.0026 [-0.0037, -0.0017] iyileşiyor: küçük ama gerçek. Takım etkileri ise toplam kartta -0.0051 [-0.0086, -0.0015] (takım etkisiz modele göre).

**Banko benzeri oranlar (model olasılığı >= 0.80 ve >= 0.85 olan tahminlerin tutma oranı, test dönemi).** Her satır bir (maç, çizgi, taraf) çağrısıdır; aynı maçtan birden çok çizgi sayılabilir, bu yüzden "maç sayısı" ayrıca verildi. Bu oranlar bahis kârı değildir (bu marketler için yerel oran verisi yok).

| Market | Eşik | Çağrı (n) | Tutan | Tutma oranı | Ort. model güveni | Farklı maç | Son-5 yöntemi (tutan/n) |
|---|---|---|---|---|---|---|---|
| Toplam sarı kart | >= 0.80 | 2942 | 2513 | 85.4% | 85.7% | 2578 | 2872/3562 (80.6%) |
| Toplam sarı kart | >= 0.85 | 1483 | 1321 | 89.1% | 88.9% | 1387 | 1685/2026 (83.2%) |
| Takım sarı kart | >= 0.80 | 6170 | 5319 | 86.2% | 86.5% | 3213 | 5183/6193 (83.7%) |
| Takım sarı kart | >= 0.85 | 3669 | 3250 | 88.6% | 89.1% | 2523 | 3677/4301 (85.5%) |
| Toplam korner | >= 0.80 | 240 | 191 | 79.6% | 81.5% | 240 | 790/1050 (75.2%) |
| Toplam korner | >= 0.85 | 2 | 1 | 50.0% | 85.6% | 2 | 233/308 (75.6%) |
| Takım korner | >= 0.80 | 7732 | 6658 | 86.1% | 86.1% | 3192 | 5280/6531 (80.8%) |
| Takım korner | >= 0.85 | 4205 | 3742 | 89.0% | 89.2% | 2303 | 2617/3121 (83.9%) |
| Takım şut | >= 0.80 | 12149 | 10817 | 89.0% | 89.0% | 3222 | 7949/9190 (86.5%) |
| Takım şut | >= 0.85 | 8655 | 7915 | 91.5% | 91.6% | 3166 | 5136/5772 (89.0%) |
| Toplam şut | >= 0.80 | 3920 | 3498 | 89.2% | 87.3% | 2446 | 2295/2528 (90.8%) |
| Toplam şut | >= 0.85 | 2503 | 2302 | 92.0% | 90.1% | 1772 | 1186/1271 (93.3%) |
| Takım isabetli şut | >= 0.80 | 6375 | 5510 | 86.4% | 86.8% | 2971 | 3918/4796 (81.7%) |
| Takım isabetli şut | >= 0.85 | 3744 | 3343 | 89.3% | 89.8% | 2160 | 1884/2227 (84.6%) |
| Toplam isabetli şut | >= 0.80 | 1043 | 912 | 87.4% | 84.1% | 899 | 1067/1324 (80.6%) |
| Toplam isabetli şut | >= 0.85 | 343 | 318 | 92.7% | 87.9% | 312 | 419/497 (84.3%) |

Tüm marketler birlikte: model >= 0.80: 35418/40571 = 87.3% (son-5 yöntemi 83.5%); >= 0.85: 22192/24604 = 90.2% (son-5 yöntemi 86.2%).

**Uyarılar.**
- Yüksek güvenli çağrıların çoğu uçtaki çizgilerde (ör. takım şutu Üst 7.5, toplam kart Alt 5.5, takım korner Alt 6.5): bu çizgiler zaten çoğu maçta aynı tarafa düşüyor. Bu yüzden ham tutma oranı beceri kanıtı değil; asıl kanıt log loss farkı ve kalibrasyon (güven ile tutma oranının uyumu). Taban oranlar aşağıda (İngilizce bölüm, per-line tablo).
- **Toplam korner** en az tahmin edilebilir market: model >= 0.80 sadece 240 çağrı, >= 0.85 sadece 2 çağrı üretiyor; banko benzeri çağrı çıkacak kadar güven oluşmuyor.
- Avrupa kupaları: test döneminde yalnızca 166 maç; güven aralıkları geniş. Model - son-5 farkının aralığı sıfırı içeren marketler: Toplam sarı kart, Toplam korner, Toplam şut (diğerlerinde Avrupa'da da model daha iyi).
- **Aşırı güven uyarısı** (>= 0.80 çağrılarında ortalama güven, tutma oranından 2 puandan fazla yüksek): total_shots_high (ek çizgiler): güven 87.4%, tutma 83.8% (n=3882). Bu marketlerin uç çizgilerinde olasılığı biraz düşük okumak gerekir.
- **Seviye kayması (test dönemi):** gözlenen Üst oranı ile modelin ortalama Üst olasılığı arasındaki fark (çizgi ortalaması, + = gerçekte model beklentisinden daha çok Üst): Toplam sarı kart (-2.2 puan), Toplam korner (+2.6 puan), Takım şut (+2.8 puan), Toplam şut (+3.5 puan), Toplam isabetli şut (+3.0 puan). Yani test döneminde şut/korner sayıları modelin öğrendiği seviyenin biraz üstünde, kart sayıları biraz altında kaldı; dağıtım (deployment) modeli tüm maçlarla ve zaman ağırlığıyla yeniden eğitildiği için bu kaymayı kısmen yakalar, ama yeni sezon verisi geldikçe yeniden eğitim gerekir.
- Sarı kart sayısının dağılımı Poisson'a çok yakın çıktı (aşırı yayılım yok, boyut parametresi üst sınırda); kart tahminleri hakem ve takım eğilimine bağlı ama farklar küçük.
- Sadece sayılar kullanıldı: kadro, sakatlık, hakem atama bilgisi (maç öncesi hakem açıklanmadıysa etki 0 alınır), maç önemi yok.
- Veri notu: 20,012 maç; 836 maçta kart/faul bloğu FotMob'da yok (dışarıda). Sarı kartı 0-0 olan 637 maç (%3.3) FotMob'un gönderdiği haliyle tutuldu; bazı liglerde oran yüksek (Eredivisie %7.2, Championship %6.3), bunların bir kısmı gerçekte eksik veri olabilir ve doğrulanamadı.

---

## Details (English)

### 1. Data and coverage

One row per match (`backend/data/training/props_match_stats.csv.gz`, built by `props_build_dataset.py` from `fotmob_match_details*.jsonl` + the referee name in the raw bodies `content.matchFacts.infoBox.Referee.text`). Input 20,048 rows; dropped awarded 36; kept 20,012 (2022-07-22 .. 2026-10-12). A stat is used only when FotMob sent it for both teams; a missing stat is excluded and counted, never 0. Referee read: ok 18,900, no referee 1,112 (unreadable raw files: 0). Czech 1. Liga `total_shots` before 2025-07-01 is excluded (different definition: 821 matches).

| Stat | Matches with stat | Missing | Both sides 0 |
|---|---|---|---|
| corners | 20004 | 8 | 1 |
| yellow_cards | 19176 | 836 | 637 |
| total_shots | 20004 | 8 | 3 |
| shots_on_target | 20004 | 8 | 9 |
| fouls | 19176 | 836 | 0 |

Referee name present: 18,900 of 20,012 matches.

Coverage per competition (matches with the stat present):

| id | competition | matches | referee | corners | yellow | shots | SoT | fouls |
|---|---|---|---|---|---|---|---|---|
| 87 | LaLiga | 1598 | 1598 | 1598 | 1597 | 1598 | 1598 | 1597 |
| 55 | Serie A | 1581 | 1581 | 1581 | 1581 | 1581 | 1581 | 1581 |
| 47 | Premier League | 1580 | 1580 | 1580 | 1580 | 1580 | 1580 | 1580 |
| 71 | Super Lig | 1400 | 1374 | 1400 | 1400 | 1400 | 1400 | 1400 |
| 53 | Ligue 1 | 1351 | 1351 | 1351 | 1351 | 1351 | 1351 | 1351 |
| 40 | Belgian Pro League | 1337 | 1294 | 1337 | 1336 | 1337 | 1337 | 1336 |
| 57 | Eredivisie | 1311 | 1311 | 1311 | 1311 | 1311 | 1311 | 1311 |
| 61 | Liga Portugal | 1295 | 1293 | 1295 | 1295 | 1295 | 1295 | 1295 |
| 54 | Bundesliga | 1268 | 1268 | 1268 | 1268 | 1268 | 1268 | 1268 |
| 48 | Championship | 1219 | 1204 | 1219 | 1219 | 1219 | 1219 | 1219 |
| 122 | Czech 1. Liga | 1183 | 317 | 1175 | 355 | 1175 | 1175 | 355 |
| 73 | Europa League | 678 | 671 | 678 | 678 | 678 | 678 | 678 |
| 42 | Champions League | 646 | 646 | 646 | 646 | 646 | 646 | 646 |
| 10216 | Conference League | 588 | 571 | 588 | 587 | 588 | 588 | 587 |
| 59 | Eliteserien | 561 | 561 | 561 | 561 | 561 | 561 | 561 |
| 69 | Swiss Super League | 516 | 513 | 516 | 516 | 516 | 516 | 516 |
| 135 | Greek Super League | 513 | 410 | 513 | 508 | 513 | 513 | 508 |
| 64 | Scottish Premiership | 504 | 501 | 504 | 504 | 504 | 504 | 504 |
| 46 | Superligaen | 445 | 445 | 445 | 445 | 445 | 445 | 445 |
| 38 | Austrian Bundesliga | 438 | 411 | 438 | 438 | 438 | 438 | 438 |

Splits (valid matches per stat): train 2022-08-01..2025-06-30, validation 2025-07-01..2026-01-31, test 2026-02-01..2026-10-12 (read once after freezing `props_frozen.json`).

| Stat | Train | Validation | Test |
|---|---|---|---|
| corners | 13180 | 3396 | 3402 |
| yellow_cards | 12360 | 3396 | 3402 |
| total_shots | 12367 | 3396 | 3402 |
| shots_on_target | 13180 | 3396 | 3402 |
| fouls | 12360 | 3396 | 3402 |

### 2. Model

For a stat, one observation per team side: `ln mu_home = b0 + h + L[comp] + A[home] + D[away] (+ R[referee])`, `ln mu_away = b0 + L[comp] + A[away] + D[home] (+ R[referee])`; count ~ NegativeBinomial(mean mu, size r), r fitted per stat. Optional "dominance" block S: attack = A + S, concede = D - S (a team that dominates takes more and concedes less, one parameter per team). Weights `0.5 ** (age / half_life)`, ridge on A, D, S, R (teams / referees with few matches shrink to 0 = competition mean), walk-forward refits every 14 days (a fit uses only matches that kicked off >= 3 h before the fit date). Dispersion r (and, for total shots, a separate size for the total) is the out-of-sample maximum-likelihood value on the validation walk-forward predictions; for the deployment fit it is estimated on validation + test walk-forward predictions. Fitted by L-BFGS-B with the analytic gradient.

Choices made on validation only (small grids; `score` = mean log loss of the main lines on the validation primary set):

| Stat | Half-life d | ridge team | concede | dominance | referee | ridge ref | comp. level | val. score | configs tried | NB size r (val) | own total size |
|---|---|---|---|---|---|---|---|---|---|---|---|
| yellow_cards | 480.0 | 30.0 | yes | no | yes | 80.0 | one per comp. | 0.5635 | 50 | 4999.82 | no |
| corners | 240.0 | 90.0 | no | yes | no | - | one per comp. | 0.6048 | 56 | 11.17 | no |
| total_shots | 120.0 | 30.0 | no | yes | no | - | one per comp. | 0.5466 | 46 | 18.32 | yes |
| shots_on_target | 240.0 | 30.0 | no | yes | no | - | one per comp. | 0.5990 | 46 | 28.22 | no |
| fouls | 120.0 | 30.0 | yes | no | yes | 320.0 | season random walk | 0.5639 | 52 | 235.68 | no |

Deployment parameters (all matches up to the last kick-off, 2026-10-12T19:15:00Z):

| Stat | r | r total | intercept | home adv. | competitions | teams | referees | matches fitted |
|---|---|---|---|---|---|---|---|---|
| yellow_cards | 4999.808742 | - | 0.7088 | -0.1486 | 20 | 439 | 744 | 19176 |
| corners | 11.128494 | - | 1.4659 | 0.2026 | 20 | 440 | 0 | 20004 |
| total_shots | 18.445365 | 90.752926 | 2.4667 | 0.1972 | 20 | 439 | 0 | 19183 |
| shots_on_target | 29.611195 | - | 1.3720 | 0.1901 | 20 | 440 | 0 | 20004 |
| fouls | 177.791219 | - | 2.4935 | -0.0390 | 20 | 439 | 744 | 19176 |

### 3. Test results (2026-02-01..2026-10-12)

Primary set: test matches where both teams have >= 5 matches with the stat in the previous 365 days and the competition has >= 30 matches in the previous 365 days (the set on which last-5 / last-10 / 365-day-average / competition-average baselines are defined); all methods are scored on exactly these matches. Paired bootstrap over matches, 2000 resamples, seed 7, 90 % interval. All methods are scored on exactly the same matches and the same lines. Baselines use a negative-binomial with a size fitted on validation, means floored at 0.05 (floored rows: 0). (a) last-5 = mean(team's last-5 for, opponent's last-5 against), (b) last-10, 365-day average of the same form, (c) competition average (home and away separately).

#### 3.1 Log loss of the over/under lines (mean over the lines of a market)

| Market | n | Model | Last-5 | Last-10 | 365-day avg | Comp. avg | Model w/o team effects |
|---|---|---|---|---|---|---|---|
| total_yellow_cards | 3222 | 0.5825 | 0.6118 | 0.5949 | 0.5869 | 0.5922 | 0.5876 |
| team_yellow_cards | 3222 | 0.5553 | 0.5813 | 0.5676 | 0.5625 | 0.5645 | 0.5621 |
| total_corners | 3222 | 0.6313 | 0.6503 | 0.6395 | 0.6360 | 0.6393 | 0.6381 |
| team_corners | 3222 | 0.5751 | 0.6143 | 0.6004 | 0.5948 | 0.6034 | 0.6021 |
| team_shots | 3222 | 0.5185 | 0.5626 | 0.5529 | 0.5521 | 0.5728 | 0.5718 |
| total_shots | 3222 | 0.5321 | 0.5493 | 0.5423 | 0.5484 | 0.5639 | 0.5484 |
| team_shots_on_target | 3222 | 0.5739 | 0.6156 | 0.6022 | 0.5961 | 0.6137 | 0.6131 |
| total_shots_on_target | 3222 | 0.6145 | 0.6346 | 0.6230 | 0.6185 | 0.6270 | 0.6271 |

Model minus baseline (negative = model better), mean [90 % CI]:

| Market | vs last-5 | vs last-10 | vs 365-day avg | vs comp. avg |
|---|---|---|---|---|
| total_yellow_cards | -0.0292 [-0.0360, -0.0222] | -0.0123 [-0.0173, -0.0072] | -0.0044 [-0.0073, -0.0015] | -0.0097 [-0.0137, -0.0057] |
| team_yellow_cards | -0.0260 [-0.0303, -0.0215] | -0.0123 [-0.0154, -0.0091] | -0.0072 [-0.0091, -0.0052] | -0.0092 [-0.0116, -0.0067] |
| total_corners | -0.0190 [-0.0240, -0.0138] | -0.0082 [-0.0115, -0.0049] | -0.0046 [-0.0066, -0.0027] | -0.0080 [-0.0101, -0.0059] |
| team_corners | -0.0392 [-0.0441, -0.0341] | -0.0253 [-0.0290, -0.0214] | -0.0197 [-0.0228, -0.0165] | -0.0283 [-0.0324, -0.0241] |
| team_shots | -0.0442 [-0.0499, -0.0387] | -0.0344 [-0.0390, -0.0297] | -0.0337 [-0.0380, -0.0295] | -0.0544 [-0.0601, -0.0485] |
| total_shots | -0.0171 [-0.0221, -0.0120] | -0.0101 [-0.0138, -0.0061] | -0.0163 [-0.0197, -0.0128] | -0.0318 [-0.0368, -0.0265] |
| team_shots_on_target | -0.0417 [-0.0472, -0.0363] | -0.0283 [-0.0328, -0.0240] | -0.0222 [-0.0260, -0.0186] | -0.0398 [-0.0450, -0.0348] |
| total_shots_on_target | -0.0202 [-0.0256, -0.0147] | -0.0085 [-0.0123, -0.0046] | -0.0040 [-0.0060, -0.0020] | -0.0126 [-0.0163, -0.0088] |

#### 3.2 Per line (model vs baselines; `extra` lines are outside the exported set and show the tails)

| Market | Line | Observed P(over) | Mean model P(over) | LL model | LL last-5 | LL 365-day | LL comp. |
|---|---|---|---|---|---|---|---|
| total_yellow_cards | 2.5 | 0.7107 | 0.7358 | 0.5857 | 0.6082 | 0.5865 | 0.5930 |
| total_yellow_cards | 3.5 | 0.5258 | 0.5430 | 0.6683 | 0.6998 | 0.6734 | 0.6799 |
| total_yellow_cards | 4.5 | 0.3327 | 0.3582 | 0.6085 | 0.6433 | 0.6154 | 0.6206 |
| total_yellow_cards | 5.5 | 0.1921 | 0.2128 | 0.4675 | 0.4957 | 0.4724 | 0.4753 |
| team_yellow_cards | 0.5 | 0.8434 | 0.8486 | 0.4216 | 0.4374 | 0.4256 | 0.4284 |
| team_yellow_cards | 1.5 | 0.5660 | 0.5739 | 0.6629 | 0.6944 | 0.6709 | 0.6722 |
| team_yellow_cards | 2.5 | 0.2935 | 0.3143 | 0.5814 | 0.6122 | 0.5911 | 0.5928 |
| team_yellow_cards_high (extra) | 3.5 | 0.1215 | 0.1441 | 0.3553 | 0.3740 | 0.3589 | 0.3619 |
| total_yellow_cards_low (extra) | 1.5 | 0.8634 | 0.8908 | 0.3948 | 0.4047 | 0.3949 | 0.3974 |
| total_yellow_cards_low (extra) | 6.5 | 0.0981 | 0.1150 | 0.3019 | 0.3210 | 0.3059 | 0.3086 |
| total_corners | 7.5 | 0.7427 | 0.7050 | 0.5623 | 0.5810 | 0.5681 | 0.5696 |
| total_corners | 8.5 | 0.6347 | 0.6002 | 0.6461 | 0.6641 | 0.6513 | 0.6541 |
| total_corners | 9.5 | 0.5202 | 0.4933 | 0.6787 | 0.6985 | 0.6835 | 0.6878 |
| total_corners | 10.5 | 0.4122 | 0.3917 | 0.6629 | 0.6825 | 0.6675 | 0.6712 |
| total_corners | 11.5 | 0.3110 | 0.3008 | 0.6066 | 0.6253 | 0.6093 | 0.6136 |
| team_corners | 2.5 | 0.7980 | 0.7923 | 0.4703 | 0.5021 | 0.4877 | 0.4934 |
| team_corners | 3.5 | 0.6569 | 0.6468 | 0.6022 | 0.6430 | 0.6237 | 0.6310 |
| team_corners | 4.5 | 0.5124 | 0.4970 | 0.6509 | 0.6960 | 0.6720 | 0.6802 |
| team_corners | 5.5 | 0.3760 | 0.3621 | 0.6173 | 0.6602 | 0.6376 | 0.6489 |
| team_corners | 6.5 | 0.2601 | 0.2521 | 0.5347 | 0.5703 | 0.5529 | 0.5635 |
| total_corners_high (extra) | 12.5 | 0.2222 | 0.2238 | 0.5192 | 0.5381 | 0.5215 | 0.5256 |
| total_corners_high (extra) | 13.5 | 0.1524 | 0.1616 | 0.4181 | 0.4367 | 0.4197 | 0.4246 |
| team_shots | 7.5 | 0.8582 | 0.8382 | 0.3572 | 0.3898 | 0.3804 | 0.3930 |
| team_shots | 9.5 | 0.7337 | 0.7011 | 0.5075 | 0.5547 | 0.5399 | 0.5599 |
| team_shots | 11.5 | 0.5810 | 0.5474 | 0.5998 | 0.6439 | 0.6354 | 0.6592 |
| team_shots | 13.5 | 0.4328 | 0.4014 | 0.5987 | 0.6487 | 0.6369 | 0.6619 |
| team_shots | 15.5 | 0.3025 | 0.2787 | 0.5292 | 0.5760 | 0.5680 | 0.5902 |
| total_shots | 19.5 | 0.8709 | 0.8467 | 0.3610 | 0.3879 | 0.3846 | 0.4005 |
| total_shots | 21.5 | 0.7759 | 0.7446 | 0.5057 | 0.5256 | 0.5236 | 0.5393 |
| total_shots | 23.5 | 0.6617 | 0.6208 | 0.6085 | 0.6217 | 0.6223 | 0.6365 |
| total_shots | 25.5 | 0.5332 | 0.4883 | 0.6534 | 0.6620 | 0.6632 | 0.6792 |
| total_shots_high (extra) | 27.5 | 0.4100 | 0.3616 | 0.6418 | 0.6455 | 0.6465 | 0.6613 |
| total_shots_high (extra) | 29.5 | 0.3004 | 0.2520 | 0.5804 | 0.5821 | 0.5814 | 0.5948 |
| total_shots_high (extra) | 31.5 | 0.2011 | 0.1655 | 0.4689 | 0.4804 | 0.4739 | 0.4877 |
| team_shots_high (extra) | 17.5 | 0.2052 | 0.1849 | 0.4330 | 0.4769 | 0.4696 | 0.4867 |
| team_shots_high (extra) | 19.5 | 0.1314 | 0.1179 | 0.3308 | 0.3666 | 0.3598 | 0.3752 |
| team_shots_on_target | 2.5 | 0.7734 | 0.7596 | 0.4992 | 0.5290 | 0.5145 | 0.5257 |
| team_shots_on_target | 3.5 | 0.6158 | 0.5931 | 0.6122 | 0.6582 | 0.6356 | 0.6514 |
| team_shots_on_target | 4.5 | 0.4472 | 0.4288 | 0.6274 | 0.6723 | 0.6519 | 0.6725 |
| team_shots_on_target | 5.5 | 0.3091 | 0.2898 | 0.5569 | 0.6029 | 0.5825 | 0.6054 |
| total_shots_on_target | 6.5 | 0.7762 | 0.7396 | 0.5160 | 0.5387 | 0.5206 | 0.5301 |
| total_shots_on_target | 7.5 | 0.6611 | 0.6230 | 0.6192 | 0.6418 | 0.6244 | 0.6347 |
| total_shots_on_target | 8.5 | 0.5279 | 0.5007 | 0.6727 | 0.6909 | 0.6760 | 0.6828 |
| total_shots_on_target | 9.5 | 0.4029 | 0.3839 | 0.6500 | 0.6673 | 0.6530 | 0.6605 |

#### 3.3 Expected counts (MAE per team side and of the match total) and NB log likelihood

| Stat | Method | MAE team | MAE total | NB nll / team | MAE team: model minus this [90 % CI] |
|---|---|---|---|---|---|
| yellow_cards | model | 1.060 | 1.618 | 1.6363 | - |
| yellow_cards | last5 | 1.102 | 1.671 | 1.6807 | -0.0420 [-0.0511, -0.0324] |
| yellow_cards | last10 | 1.079 | 1.633 | 1.6569 | -0.0196 [-0.0266, -0.0121] |
| yellow_cards | avg365 | 1.069 | 1.625 | 1.6468 | -0.0097 [-0.0146, -0.0048] |
| yellow_cards | comp | 1.073 | 1.638 | 1.6508 | -0.0135 [-0.0191, -0.0077] |
| corners | model | 2.106 | 2.695 | 2.3442 | - |
| corners | last5 | 2.262 | 2.804 | 2.4133 | -0.1554 [-0.1763, -0.1331] |
| corners | last10 | 2.209 | 2.744 | 2.3906 | -0.1028 [-0.1194, -0.0848] |
| corners | avg365 | 2.184 | 2.717 | 2.3797 | -0.0781 [-0.0924, -0.0636] |
| corners | comp | 2.221 | 2.736 | 2.3966 | -0.1148 [-0.1331, -0.0967] |
| total_shots | model | 3.742 | 4.689 | 2.9444 | - |
| total_shots | last5 | 4.078 | 4.782 | 3.0314 | -0.3361 [-0.3828, -0.2901] |
| total_shots | last10 | 4.003 | 4.698 | 3.0139 | -0.2610 [-0.3021, -0.2204] |
| total_shots | avg365 | 4.004 | 4.719 | 3.0132 | -0.2623 [-0.3004, -0.2232] |
| total_shots | comp | 4.171 | 4.851 | 3.0517 | -0.4292 [-0.4774, -0.3778] |
| shots_on_target | model | 1.786 | 2.439 | 2.1947 | - |
| shots_on_target | last5 | 1.943 | 2.521 | 2.2686 | -0.1571 [-0.1769, -0.1369] |
| shots_on_target | last10 | 1.892 | 2.474 | 2.2468 | -0.1056 [-0.1226, -0.0891] |
| shots_on_target | avg365 | 1.869 | 2.458 | 2.2349 | -0.0828 [-0.0971, -0.0696] |
| shots_on_target | comp | 1.931 | 2.486 | 2.2662 | -0.1449 [-0.1648, -0.1255] |
| fouls | model | 2.839 | 4.190 | 2.6836 | - |
| fouls | last5 | 2.933 | 4.308 | 2.7176 | -0.0944 [-0.1179, -0.0692] |
| fouls | last10 | 2.877 | 4.239 | 2.6995 | -0.0375 [-0.0563, -0.0182] |
| fouls | avg365 | 2.897 | 4.271 | 2.7019 | -0.0584 [-0.0755, -0.0405] |
| fouls | comp | 3.056 | 4.480 | 2.7530 | -0.2171 [-0.2467, -0.1868] |

#### 3.4 League vs European (primary set; European = UCL, UEL, UECL)

| Market | Group | n | Model | Last-5 | Comp. avg | Model - last-5 | Model - comp. |
|---|---|---|---|---|---|---|---|
| total_yellow_cards | league | 3056 | 0.5814 | 0.6105 | 0.5910 | -0.0291 [-0.0361, -0.0224] | -0.0097 [-0.0140, -0.0053] |
| total_yellow_cards | european | 166 | 0.6037 | 0.6352 | 0.6142 | -0.0316 [-0.0676, +0.0026] | -0.0105 [-0.0316, +0.0094] |
| team_yellow_cards | league | 3056 | 0.5544 | 0.5796 | 0.5639 | -0.0252 [-0.0295, -0.0207] | -0.0094 [-0.0120, -0.0069] |
| team_yellow_cards | european | 166 | 0.5712 | 0.6117 | 0.5757 | -0.0406 [-0.0613, -0.0204] | -0.0045 [-0.0160, +0.0062] |
| total_corners | league | 3056 | 0.6306 | 0.6495 | 0.6385 | -0.0190 [-0.0240, -0.0140] | -0.0080 [-0.0102, -0.0057] |
| total_corners | european | 166 | 0.6445 | 0.6641 | 0.6525 | -0.0195 [-0.0419, +0.0022] | -0.0079 [-0.0175, +0.0021] |
| team_corners | league | 3056 | 0.5736 | 0.6123 | 0.6024 | -0.0387 [-0.0437, -0.0335] | -0.0287 [-0.0330, -0.0245] |
| team_corners | european | 166 | 0.6015 | 0.6509 | 0.6219 | -0.0493 [-0.0745, -0.0278] | -0.0204 [-0.0370, -0.0037] |
| team_shots | league | 3056 | 0.5175 | 0.5604 | 0.5714 | -0.0429 [-0.0485, -0.0373] | -0.0538 [-0.0595, -0.0480] |
| team_shots | european | 166 | 0.5354 | 0.6030 | 0.5999 | -0.0676 [-0.0965, -0.0400] | -0.0645 [-0.0903, -0.0359] |
| total_shots | league | 3056 | 0.5312 | 0.5491 | 0.5626 | -0.0179 [-0.0227, -0.0125] | -0.0314 [-0.0366, -0.0259] |
| total_shots | european | 166 | 0.5490 | 0.5533 | 0.5881 | -0.0043 [-0.0281, +0.0193] | -0.0391 [-0.0603, -0.0151] |
| team_shots_on_target | league | 3056 | 0.5737 | 0.6133 | 0.6126 | -0.0395 [-0.0445, -0.0342] | -0.0388 [-0.0437, -0.0338] |
| team_shots_on_target | european | 166 | 0.5775 | 0.6585 | 0.6353 | -0.0810 [-0.1095, -0.0543] | -0.0578 [-0.0772, -0.0370] |
| total_shots_on_target | league | 3056 | 0.6167 | 0.6357 | 0.6287 | -0.0190 [-0.0244, -0.0136] | -0.0120 [-0.0158, -0.0079] |
| total_shots_on_target | european | 166 | 0.5734 | 0.6159 | 0.5963 | -0.0425 [-0.0725, -0.0132] | -0.0229 [-0.0387, -0.0068] |

#### 3.5 What the referee and the team effects add (log loss, model minus variant, [90 % CI])

Referee effect (cards and fouls) and team effects (same model without attack / concede / dominance, keeping the referee):

| Market | Model minus no-referee model | Model minus no-team-effects model |
|---|---|---|
| total_yellow_cards | -0.0056 [-0.0077, -0.0037] | -0.0051 [-0.0086, -0.0015] |
| team_yellow_cards | -0.0026 [-0.0037, -0.0017] | -0.0068 [-0.0090, -0.0046] |
| team_yellow_cards_high (extra) | -0.0015 [-0.0027, -0.0003] | -0.0059 [-0.0084, -0.0034] |
| total_yellow_cards_low (extra) | -0.0024 [-0.0038, -0.0010] | -0.0030 [-0.0056, -0.0003] |
| total_fouls (extra) | -0.0036 [-0.0054, -0.0017] | -0.0322 [-0.0393, -0.0252] |
| team_fouls (extra) | -0.0020 [-0.0030, -0.0011] | -0.0397 [-0.0449, -0.0347] |

Team effects for the other stats (model minus no-team-effects model):

| Market | Model minus no-team-effects model |
|---|---|
| total_corners | -0.0067 [-0.0087, -0.0048] |
| team_corners | -0.0270 [-0.0312, -0.0229] |
| team_shots | -0.0533 [-0.0590, -0.0474] |
| total_shots | -0.0163 [-0.0211, -0.0112] |
| team_shots_on_target | -0.0391 [-0.0443, -0.0341] |
| total_shots_on_target | -0.0126 [-0.0162, -0.0089] |

#### 3.6 Calibration

Expected calibration error (10 probability bins of P(over), all lines of the market pooled; smaller is better):

| Market | ECE model | ECE last-5 |
|---|---|---|
| total_yellow_cards | 0.02213 | 0.0326 |
| team_yellow_cards | 0.0124 | 0.02247 |
| total_corners | 0.02805 | 0.03263 |
| team_corners | 0.01091 | 0.02251 |
| team_shots | 0.02828 | 0.01725 |
| total_shots | 0.03531 | 0.06464 |
| team_shots_on_target | 0.01854 | 0.02305 |
| total_shots_on_target | 0.03024 | 0.03563 |

Confidence of the predicted side (max(p, 1-p)), main markets pooled; hit = the predicted side happened:

| Band | Model n | Model hit rate | Model mean conf. | Last-5 n | Last-5 hit rate | Last-5 mean conf. |
|---|---|---|---|---|---|---|
| 0.50-0.60 | 43240 | 55.5% | 0.550 | 46134 | 55.3% | 0.550 |
| 0.60-0.70 | 42435 | 65.4% | 0.650 | 43955 | 64.2% | 0.650 |
| 0.70-0.80 | 38076 | 75.0% | 0.748 | 39059 | 73.4% | 0.748 |
| 0.80-0.85 | 15967 | 82.8% | 0.824 | 15651 | 80.0% | 0.824 |
| 0.85-0.90 | 13210 | 87.0% | 0.874 | 12251 | 84.7% | 0.874 |
| 0.90-1.00 | 11394 | 93.8% | 0.934 | 7272 | 88.8% | 0.928 |

#### 3.7 Banko-like calls per line (model >= 0.80 / >= 0.85)

`over` / `under` = number of calls on that side; hits = the called side landed. The observed base rate of the line is in 3.2.

| Market | Threshold | Line | n | Hits | Hit rate | Mean conf. | over | under |
|---|---|---|---|---|---|---|---|---|
| total_yellow_cards | >= 0.80 | 2.5 | 914 | 742 | 81.2% | 85.0% | 914 | 0 |
| total_yellow_cards | >= 0.80 | 3.5 | 58 | 44 | 75.9% | 83.4% | 58 | 0 |
| total_yellow_cards | >= 0.80 | 4.5 | 306 | 264 | 86.3% | 83.6% | 1 | 305 |
| total_yellow_cards | >= 0.80 | 5.5 | 1664 | 1463 | 87.9% | 86.5% | 0 | 1664 |
| total_yellow_cards | >= 0.85 | 2.5 | 403 | 349 | 86.6% | 88.4% | 403 | 0 |
| total_yellow_cards | >= 0.85 | 3.5 | 14 | 7 | 50.0% | 87.0% | 14 | 0 |
| total_yellow_cards | >= 0.85 | 4.5 | 82 | 73 | 89.0% | 87.3% | 0 | 82 |
| total_yellow_cards | >= 0.85 | 5.5 | 984 | 892 | 90.6% | 89.2% | 0 | 984 |
| team_yellow_cards | >= 0.80 | 0.5 | 5186 | 4484 | 86.5% | 87.0% | 5186 | 0 |
| team_yellow_cards | >= 0.80 | 1.5 | 93 | 72 | 77.4% | 83.0% | 93 | 0 |
| team_yellow_cards | >= 0.80 | 2.5 | 891 | 763 | 85.6% | 83.7% | 0 | 891 |
| team_yellow_cards | >= 0.85 | 0.5 | 3400 | 3015 | 88.7% | 89.3% | 3400 | 0 |
| team_yellow_cards | >= 0.85 | 1.5 | 20 | 15 | 75.0% | 86.5% | 20 | 0 |
| team_yellow_cards | >= 0.85 | 2.5 | 249 | 220 | 88.4% | 87.4% | 0 | 249 |
| team_yellow_cards_high (extra) | >= 0.80 | 3.5 | 5174 | 4663 | 90.1% | 88.5% | 0 | 5174 |
| team_yellow_cards_high (extra) | >= 0.85 | 3.5 | 3869 | 3563 | 92.1% | 90.4% | 0 | 3869 |
| total_yellow_cards_low (extra) | >= 0.80 | 1.5 | 3007 | 2620 | 87.1% | 90.0% | 3007 | 0 |
| total_yellow_cards_low (extra) | >= 0.80 | 6.5 | 2829 | 2598 | 91.8% | 90.6% | 0 | 2829 |
| total_yellow_cards_low (extra) | >= 0.85 | 1.5 | 2572 | 2265 | 88.1% | 91.2% | 2572 | 0 |
| total_yellow_cards_low (extra) | >= 0.85 | 6.5 | 2411 | 2242 | 93.0% | 91.9% | 0 | 2411 |
| total_corners | >= 0.80 | 7.5 | 92 | 74 | 80.4% | 81.4% | 92 | 0 |
| total_corners | >= 0.80 | 11.5 | 148 | 117 | 79.1% | 81.5% | 0 | 148 |
| total_corners | >= 0.85 | 7.5 | 1 | 0 | 0.0% | 85.2% | 1 | 0 |
| total_corners | >= 0.85 | 11.5 | 1 | 1 | 100.0% | 86.0% | 0 | 1 |
| team_corners | >= 0.80 | 2.5 | 3390 | 2975 | 87.8% | 86.5% | 3390 | 0 |
| team_corners | >= 0.80 | 3.5 | 786 | 678 | 86.3% | 84.2% | 782 | 4 |
| team_corners | >= 0.80 | 4.5 | 192 | 160 | 83.3% | 83.3% | 92 | 100 |
| team_corners | >= 0.80 | 5.5 | 824 | 682 | 82.8% | 84.9% | 2 | 822 |
| team_corners | >= 0.80 | 6.5 | 2540 | 2163 | 85.2% | 86.7% | 0 | 2540 |
| team_corners | >= 0.85 | 2.5 | 2011 | 1828 | 90.9% | 89.3% | 2011 | 0 |
| team_corners | >= 0.85 | 3.5 | 287 | 253 | 88.2% | 87.8% | 287 | 0 |
| team_corners | >= 0.85 | 4.5 | 45 | 38 | 84.4% | 87.4% | 16 | 29 |
| team_corners | >= 0.85 | 5.5 | 352 | 310 | 88.1% | 88.4% | 0 | 352 |
| team_corners | >= 0.85 | 6.5 | 1510 | 1313 | 87.0% | 89.5% | 0 | 1510 |
| total_corners_high (extra) | >= 0.80 | 12.5 | 1094 | 925 | 84.6% | 83.3% | 0 | 1094 |
| total_corners_high (extra) | >= 0.80 | 13.5 | 2632 | 2285 | 86.8% | 85.3% | 0 | 2632 |
| total_corners_high (extra) | >= 0.85 | 12.5 | 254 | 219 | 86.2% | 86.7% | 0 | 254 |
| total_corners_high (extra) | >= 0.85 | 13.5 | 1327 | 1183 | 89.1% | 88.0% | 0 | 1327 |
| team_shots | >= 0.80 | 7.5 | 4473 | 4104 | 91.8% | 90.7% | 4472 | 1 |
| team_shots | >= 0.80 | 9.5 | 2282 | 2059 | 90.2% | 88.1% | 2237 | 45 |
| team_shots | >= 0.80 | 11.5 | 1178 | 1023 | 86.8% | 86.2% | 842 | 336 |
| team_shots | >= 0.80 | 13.5 | 1480 | 1247 | 84.3% | 87.1% | 236 | 1244 |
| team_shots | >= 0.80 | 15.5 | 2736 | 2384 | 87.1% | 89.2% | 47 | 2689 |
| team_shots | >= 0.85 | 7.5 | 3639 | 3404 | 93.5% | 92.5% | 3638 | 1 |
| team_shots | >= 0.85 | 9.5 | 1522 | 1407 | 92.4% | 90.9% | 1501 | 21 |
| team_shots | >= 0.85 | 11.5 | 601 | 537 | 89.4% | 89.8% | 447 | 154 |
| team_shots | >= 0.85 | 13.5 | 892 | 778 | 87.2% | 90.2% | 108 | 784 |
| team_shots | >= 0.85 | 15.5 | 2001 | 1789 | 89.4% | 91.6% | 23 | 1978 |
| total_shots | >= 0.80 | 19.5 | 2403 | 2181 | 90.8% | 88.5% | 2403 | 0 |
| total_shots | >= 0.80 | 21.5 | 1127 | 982 | 87.1% | 85.9% | 1127 | 0 |
| total_shots | >= 0.80 | 23.5 | 293 | 255 | 87.0% | 84.6% | 292 | 1 |
| total_shots | >= 0.80 | 25.5 | 97 | 80 | 82.5% | 83.4% | 54 | 43 |
| total_shots | >= 0.85 | 19.5 | 1763 | 1639 | 93.0% | 90.6% | 1763 | 0 |
| total_shots | >= 0.85 | 21.5 | 595 | 530 | 89.1% | 89.1% | 595 | 0 |
| total_shots | >= 0.85 | 23.5 | 116 | 107 | 92.2% | 88.6% | 116 | 0 |
| total_shots | >= 0.85 | 25.5 | 29 | 26 | 89.7% | 87.0% | 20 | 9 |
| total_shots_high (extra) | >= 0.80 | 27.5 | 390 | 315 | 80.8% | 84.0% | 4 | 386 |
| total_shots_high (extra) | >= 0.80 | 29.5 | 1239 | 1008 | 81.4% | 86.2% | 0 | 1239 |
| total_shots_high (extra) | >= 0.80 | 31.5 | 2253 | 1932 | 85.8% | 88.6% | 0 | 2253 |
| total_shots_high (extra) | >= 0.85 | 27.5 | 132 | 110 | 83.3% | 87.8% | 2 | 130 |
| total_shots_high (extra) | >= 0.85 | 29.5 | 696 | 585 | 84.1% | 89.1% | 0 | 696 |
| total_shots_high (extra) | >= 0.85 | 31.5 | 1671 | 1478 | 88.4% | 90.7% | 0 | 1671 |
| team_shots_high (extra) | >= 0.80 | 17.5 | 4122 | 3678 | 89.2% | 91.3% | 10 | 4112 |
| team_shots_high (extra) | >= 0.80 | 19.5 | 5172 | 4760 | 92.0% | 93.3% | 1 | 5171 |
| team_shots_high (extra) | >= 0.85 | 17.5 | 3389 | 3087 | 91.1% | 93.1% | 3 | 3386 |
| team_shots_high (extra) | >= 0.85 | 19.5 | 4644 | 4327 | 93.2% | 94.5% | 1 | 4643 |
| team_shots_on_target | >= 0.80 | 2.5 | 2689 | 2354 | 87.5% | 87.5% | 2689 | 0 |
| team_shots_on_target | >= 0.80 | 3.5 | 771 | 687 | 89.1% | 85.5% | 731 | 40 |
| team_shots_on_target | >= 0.80 | 4.5 | 687 | 569 | 82.8% | 84.9% | 133 | 554 |
| team_shots_on_target | >= 0.80 | 5.5 | 2228 | 1900 | 85.3% | 86.9% | 26 | 2202 |
| team_shots_on_target | >= 0.85 | 2.5 | 1736 | 1567 | 90.3% | 90.3% | 1736 | 0 |
| team_shots_on_target | >= 0.85 | 3.5 | 364 | 333 | 91.5% | 89.1% | 357 | 7 |
| team_shots_on_target | >= 0.85 | 4.5 | 292 | 253 | 86.6% | 88.4% | 58 | 234 |
| team_shots_on_target | >= 0.85 | 5.5 | 1352 | 1190 | 88.0% | 89.7% | 7 | 1345 |
| total_shots_on_target | >= 0.80 | 6.5 | 837 | 738 | 88.2% | 84.4% | 837 | 0 |
| total_shots_on_target | >= 0.80 | 7.5 | 133 | 118 | 88.7% | 83.3% | 133 | 0 |
| total_shots_on_target | >= 0.80 | 8.5 | 10 | 8 | 80.0% | 82.8% | 10 | 0 |
| total_shots_on_target | >= 0.80 | 9.5 | 63 | 48 | 76.2% | 81.8% | 1 | 62 |
| total_shots_on_target | >= 0.85 | 6.5 | 308 | 288 | 93.5% | 88.0% | 308 | 0 |
| total_shots_on_target | >= 0.85 | 7.5 | 29 | 25 | 86.2% | 87.4% | 29 | 0 |
| total_shots_on_target | >= 0.85 | 8.5 | 2 | 2 | 100.0% | 86.4% | 2 | 0 |
| total_shots_on_target | >= 0.85 | 9.5 | 4 | 3 | 75.0% | 85.7% | 0 | 4 |

#### 3.8 Fouls (optional stat, not requested as a market)

Fouls are exported (`stats.fouls`) because the fit was cheap; log loss of the extra lines: total_fouls model 0.5529 vs last-5 0.5664 (-0.0135 [-0.0197, -0.0070]); team_fouls model 0.5730 vs last-5 0.5924 (-0.0193 [-0.0235, -0.0148]).

### 4. Export and runtime check

`props_model_candidate.json`: version `props_v1`, trained_through `2026-10-12T19:15:00Z`, stats yellow_cards, corners, total_shots, shots_on_target, fouls, team_recent for 440 teams (plain last-5 averages for the UI, not model inputs), the 8 market line sets, the `evaluation` block and the `formula` text:

```
For a stat S with exported block B: mu_home = exp(B.intercept + B.competitions.get(competition_id, 0) + B.home_advantage + B.teams[home].attack + B.teams[away].concede + referee_offset); mu_away = exp(B.intercept + B.competitions.get(competition_id, 0) + B.teams[away].attack + B.teams[home].concede + referee_offset); referee_offset = B.referees.get(referee, {offset: 0}).offset (only stats whose referees block is not empty; 0 for an unknown or missing referee); an unknown team contributes 0 for attack and concede. Each side is NegativeBinomial with mean mu and size B.dispersion r (variance mu + mu^2 / r), P(X > line) = 1 - P(X <= floor(line)). Team markets use one side. Total markets: if B.total_dispersion is null, the total is the exact convolution of the two NB sides (independence); otherwise the total is NB with mean mu_home + mu_away and size B.total_dispersion (this captures the home/away correlation of the counts). Team 'attack' / 'concede' already contain the dominance block (attack = A + S, concede = D - S). 'competitions' is the competition level of the CURRENT season (the model keeps a random-walk level per competition and season when level mode is on, see hyperparameters.use_level). team_recent holds plain averages of the last 5 matches (for UI display only, not model inputs).
```

Added fields beyond the agreed structure: `formula`, `stats.<stat>.total_dispersion` (null = exact convolution of the two NB sides; a number = the total is NB(mu_home + mu_away, total_dispersion); used only for `total_shots`, where the two sides' counts are negatively correlated), `stats.<stat>.hyperparameters`. `competitions` holds the level of the CURRENT season (only fouls uses the season random walk).

`props_check_runtime_formula.py` applies the JSON with the formula to 200 random test matches (deployment fit) and compares with the training code: max |dp| over 1600 (match x market) comparisons = 1.81e-08, max |dmu| = 2.68e-07 (parameters are rounded to 8 decimals in the JSON).

### 5. Limits and caveats

- Counts only; no line-ups, injuries, referee assignment for upcoming matches (unknown referee = offset 0), match importance or weather.
- The hit rates are statements about the model's probabilities against FotMob counts, not about profit: no bookmaker prices for these markets exist locally.
- Banko-like calls are dominated by tail lines whose base rate is already high; compare with the observed base rate of the line (3.2) and with the calibration table (3.6).
- Level drift in the test period: the mean model P(over) differs from the observed over-rate by more than 2 points for some markets (see the Turkish summary and 3.2). The deployment fit is refitted on all matches with time decay (half-lives 120-480 days) and partly absorbs it; refit regularly.
- European competitions: few test matches; team effects there rest on fewer matches per team.
- Yellow cards: dispersion fitted at the upper bound (Poisson-like). 0-0 card matches were kept as FotMob sent them; some leagues have a high rate that could hide missing data (not verifiable offline).
- The 365-day baselines need both teams to have >= 5 matches with the stat in that window; the evaluation is on that primary set (see `n_primary` per stat in the report); the model itself predicts every match, including teams with few matches.
- Reproduce: `props_build_dataset.py` -> `props_select.py` (validation only, writes `props_frozen.json`) -> `props_final.py` (test once, deployment fit, export) -> `props_check_runtime_formula.py` -> `props_make_report.py`. Tests: `backend/tests/test_props_model.py` (synthetic fixtures).

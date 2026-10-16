# Tam veri eğitimi (train:lean) — 14 Ekim 2026

## Özet (Türkçe)

**Karar: yeni modeli canlı tahmine BAĞLAMA.** 1X2'de üretim modelinden istatistiksel olarak ayırt edilebilir bir fark yok
ve 171 Avrupa kupası test maçında nokta tahmini daha kötü. Gol pazarlarında (2.5 Alt/Üst, KG, skor) küçük ama gerçek bir
iyileşme var. Yani istenen üç kabul ölçütünden ikisi (a, b) sağlanmadı, biri (c) sağlandı.

- **Veri.** İki detay dosyasından 20.012 maç (2022-08 → 2026-10-12). Oyuncu etkisi reytingleri 2 haftalık kesimlerle
  (2022-09-05 → 2026-10-14, 109 kesim, 15.797 oyuncu). Eğitim 2022-08-01…2025-06-30 (13.187 maç), doğrulama
  2025-07-01…2026-01-31 (3.396), test 2026-02-01…2026-10-12 (3.402 maç, 171'i Avrupa). Seçimler yalnızca doğrulamada
  yapıldı, ayarlar dondurulduktan (`match_model_full_frozen.json`) sonra test bir kez puanlandı.
- **Model (tek model).** Reyting λ'sının üstüne ceza'lı (L2) Poisson düzeltmesi, skor modeli NB × Dixon-Coles. Gruplar:
  ilk 11 vs olağan 11 (RAPM), eksik oyuncu etkisi (yalnızca listede olmak; `expected_return` hiç kullanılmadı),
  piyasa değeri, son 5 maç xG/puan, bir de UEFA maçlarına özel terimler (ayrı reyting-farkı ölçeği, ayrı ev/deplasman
  sabiti, ayrı değer katsayısı). Doğrulamada seçilen: dört grubun hepsi, L2 = 10.000, Avrupa terimleri için L2 = 300,
  lig yeniden-kalibrasyon terimleri kapalı (gol katmanı yeterli).
- **Test sonuçları** (üretim modeli = taban; fark = model − taban, eşli bootstrap, 2.000 örnek, %90 GA):

| Ölçü (test) | Taban (üretim) | Yeni model | Fark (%90 GA) |
|---|---|---|---|
| 1X2 log loss (3.402 maç) | 0,9960 | 0,9952 | −0,0009 (−0,0023 … +0,0006) |
| 1X2 Brier | 0,5944 | 0,5939 | −0,0005 (−0,0015 … +0,0005) |
| 2.5 Alt/Üst log loss | 0,6734 | 0,6682 | **−0,0052 (−0,0067 … −0,0038)** |
| KG (BTTS) log loss | 0,6835 | 0,6821 | −0,0015 (−0,0025 … −0,0004) |
| Skor log loss | 2,9579 | 2,9514 | −0,0065 (−0,0090 … −0,0040) |
| Lig maçları 1X2 (3.231) | 0,9983 | 0,9972 | −0,0011 (−0,0025 … +0,0003) |
| **Avrupa maçları 1X2 (171)** | 0,9528 | 0,9567 | **+0,0039 (−0,0086 … +0,0165)** |

- **Kabul ölçütleri.** (a) 1X2 farkının GA üst sınırı < 0: **sağlanmadı** (+0,0006). (b) Avrupa alt kümesi daha kötü
  değil: **sağlanmadı** (nokta tahmini +0,0039; GA sıfırı kapsıyor ama 171 maç çok az, ölçütü katı yorumladım).
  (c) 2.5 Alt/Üst anlamlı kötüleşmedi: **sağlandı** (anlamlı iyileşme). Taban aynı gol katmanıyla (eğitim+doğrulama)
  alınsa da sonuç aynı (1X2 −0,0010, Avrupa +0,0047, 2.5 −0,0045).
- **Favori ≥ %70 (test).** Model 294 maç, isabet %75,9 (ortalama tahmin %76,9); üretim 268 maç, isabet %76,1 (%76,5).
  %70–85 bandında kalibrasyon iyi. ≥ %85'te model fazla güvenli: 28 maçta isabet %78,6, ortalama tahmin %88,7
  (≥ %90: 8 maç, 8'i tuttu, örnek çok küçük). Avrupa'da ≥ %70: 27 maç, isabet %70,4, tahmin %80,6.
- **Piyasa (kapanış oranı).** Kapanış oranı olan 2.234 test maçında (hepsi lig; kaynaklarda Avrupa kupası kapanış
  oranı yok) 1X2 log loss: piyasa 0,9921, yeni model 1,0045, üretim 1,0057 → piyasa hâlâ anlamlı biçimde önde.
  2.5 Alt/Üst (1.965 maç): piyasa 0,6649, model 0,6697, üretim 0,6756; model üretim–piyasa açığının yaklaşık yarısını
  kapatıyor.
- **Dikkat edilecekler.**
  1. "Eksik oyuncu" grubu: iki katsayının işareti de beklenenin tersi (kendi hücum kaybı +, rakibin savunma kaybı −) ve
     doğrulamadaki katkısı yalnızca 0,0002 (skor log loss). Anlamlı bir sinyal gibi yorumlanmamalı; bağlanırsa atılmalı.
  2. Piyasa değeri eğitim maçlarının %62,6'sında yok (geçmiş sezonlarda FotMob değer göndermiyor), doğrulama/testte
     %7. Katsayı çoğunlukla son sezondan öğreniliyor. Eksik oyuncu listesi de dönemden döneme değişiyor (yok oranı
     %16,7 / %20,3 / %28,5).
  3. Tabanın β = 0,0279 ve γ = 0,2157 katsayıları üretimde Ocak–Haziran 2026'da fit edildi (doğrulamanın Ocak'ı ve
     testin Şubat–Haziran'ı ile örtüşüyor): taban hafif avantajlı, yani yeni model için sonuç muhafazakâr.
  4. Oyuncu reytinglerinde hücum, varyansın ~%99'u kutu-skoru önselinden geliyor (RAPM sapması %1); savunmada %19.
  5. Avrupa için doğrulamada kazanç vardı (1X2 −0,0091, GA −0,0170 … −0,0009; 396 maç) ama testte tutmadı: Avrupa
     etkisi kararsız. Şampiyonlar Ligi'nde iyi (63 maç −0,0050), Avrupa Ligi (+0,0102) ve Konferans (+0,0074) kötü.
- **Sonraki adım (lead karar verir).** 1X2 için yeni modelin kazancı yok; Avrupa için ≥ 1.000 maçlık veri gerekir.
  Gol pazarları için (c ölçütü geçti) ayrı bir "yalnızca gol katmanı" kararı düşünülebilir, ama bu bu çalışmanın
  ölçütlerinin parçası değildi ve ayrıca doğrulanmalı.

Yeniden çalıştırma ve dosyalar aşağıda (İngilizce).

---

## Details (English)

### 1. What was built

| Output | File (all under `backend/data/training/` unless noted) |
|---|---|
| Runtime ratings export, cutoff 2026-10-14 (15,797 players; 1,979 prior-only) | `player_impact_latest.json` (`scripts/training/export_player_impact_latest.py`) |
| Feature file, 20,012 rows (19,985 with a rating lambda), `split` column | `match_features_full.csv.gz`, `match_features_full_report.json`, `README_match_features_full.md` (+ `match_features_full_missing.json`) |
| Baseline (production model, train-only goal layer) predictions, every row | `baseline_predictions_full.csv.gz`, `baseline_predictions_full_report.json` (`baseline_predictions.py`) |
| Main model: frozen choice, report, candidate | `match_model_full_frozen.json`, `match_model_full_report.json`, `match_model_candidate_full.json` (`train_match_model_full.py`) |
| Validation / test predictions, baseline and model side by side | `match_model_predictions_validation.csv.gz`, `match_model_predictions_test.csv.gz` |
| Ratings run summary (spread, defence separation) | `player_impact_all_summary.json` (`player_impact_run_summary.py`) |
| Tests | `backend/tests/test_match_model_full_training.py` (3 tests) |

Helper scripts left by the interrupted agent were checked: `baseline_predictions.py`, `describe_match_features.py`,
`export_player_impact_latest.py`, `player_impact_run_summary.py` and the edited `build_match_features.py` all compile
and ran without change. Baseline validation numbers from `baseline_predictions.py` and from the trainer agree to 5
decimals (1X2 0.98801, score 2.90968).

### 2. Data and splits

- Inputs reused: `walkforward_lambdas_full_2022_2026.csv` (weekly cutoffs, goals + xG), `player_impact_asof_all.csv.gz`
  (2-weekly cutoffs 2022-09-05 … 2026-10-14, tuned by time-forward validation inside the training period),
  `goal_layer_train_only.json` (evaluation) and `goal_layer_trainval.json` (deployment), both details files.
- Rules applied: awarded matches dropped (36), the 19 `production_vs_fixture_status` ids excluded (none was in the
  details files; checked: 0 of 19 in the output), cancelled / abandoned matches are not in the details files,
  `unavailable[*].expected_return` removed at load (54,795 entries) and never read, results used for form / rest /
  home advantage exclude awarded and conflict ids. Czech 1. Liga history has no xG (xG-form features unknown there).
- Checks on the feature file: 20,012 unique ids; every ratings cutoff < kick-off; every lambda cutoff <= kick-off.
- Splits (kick-off, naive UTC): train 2022-08-01 … 2025-06-30, validation 2025-07-01 … 2026-01-31, test
  2026-02-01 … 2026-10-12.

| Split | Matches used | European | Not used |
|---|---|---|---|
| train | 13,187 | 1,345 | 1 without a rating lambda |
| validation | 3,396 | 396 | |
| test | 3,402 | 171 | |
| before 2022-08-01 | | | 26 (no lambda / ratings yet) |

Unknown share of key features (train / validation / test): market value 62.6 / 7.5 / 6.9 %, XI vs usual XI
5.8 / 1.4 / 1.0 %, unavailable-list impact 16.7 / 20.3 / 28.5 %, xG last 5 12.2 / 7.0 / 6.9 %, points last 5 0 %.

### 3. Model

```
s = (ln L_h + ln L_a)/2 - m_s            d = (ln L_h - ln L_a)/2
ln mu_h = ln L_h + c_h + a_s s + a_d d + [UEFA: e_h + e_s s + e_d d + e_v z_value] + sum beta_k z_k
ln mu_a = ln L_a + c_a + a_s s - a_d d + [UEFA: e_a + e_s s - e_d d - e_v z_value] + the same terms, att/def swapped
```

- `L` = walk-forward rating lambda through the goal layer (train-only layer while selecting, train+val layer for the
  deployed fit). Score probabilities: NB(dispersion) x Dixon-Coles(rho), scores 0..10, as `train_goal_model.score_matrix`.
- Terms (z = (x - mean)/sd of the fitting rows, clipped to +-4; unknown -> z = 0 plus a missing indicator, never imputed):
  value (ln starters' value ratio, signed), `xi_off_att` / `xi_def_def` (XI minus usual XI, RAPM), `unav_off_att` /
  `unav_def_def` (rating loss of listed-unavailable players x minutes share; list membership only), `xgf_att` /
  `xga_def` (last-5 xG), `ppg_att` / `ppg_def` (last-5 points).
- UEFA block (competition ids 42, 73, 10216 and qualifiers 10611 / 10613 / 10615): penalised deviations from the league
  terms: intercepts, total scale, rating-difference scale, value coefficient.
- Fit: penalised maximum likelihood of the exact score, analytic gradient (checked by a test), L-BFGS-B. The league
  recalibration terms (c, alpha) were a switch chosen on validation (off); with them off rho / NB dispersion are those of
  the goal layer.

### 4. Selection on validation (fit on train, train-only goal layer; metric: exact-score log loss, baseline 2.90968)

| Step | Result |
|---|---|
| no features, recalibration only | 2.91117 (worse than baseline) |
| no features, recalibration + UEFA block | 2.91068 |
| all groups, recalibration on, best L2 (3000) | 2.90749 |
| all groups, recalibration off, L2 300 | 2.90691 |
| UEFA block off / L2e 30 / 300 / 3000 / 30000 | 2.90781 / 2.90693 / 2.90691 / 2.90725 / 2.90771 |
| backward elimination (L2 300): without value / xi / absent / form | 2.90796 / 2.90860 / 2.90714 / 2.90806 (none removed) |
| L2 retune 1000 / 3000 / **10000** / 30000 | 2.90686 / 2.90677 / **2.90669** / 2.90704 |
| L2e retune (L2 10000): off / 30 / **300** / 3000 / 30000 | 2.90739 / 2.90674 / **2.90669** / 2.90684 / 2.90727 |

Frozen: groups = value, xi, absent, form; L2 = 10,000; L2e = 300; recalibration off; clip 4 (frozen_at 2026-10-14T16:35:34Z;
the select stage ran once, 33 s). Validation (model fit on train) vs baseline, paired 90 % CIs: 1X2 log loss
0.98801 -> 0.98569 (-0.0023, -0.0039 … -0.0008); league -0.0014; European (396) -0.0091 (-0.0170 … -0.0009);
O/U 2.5 -0.0009 (-0.0024 … +0.0004); exact score -0.0030 (-0.0055 … -0.0007). These were the selection data, so they are optimistic.

### 5. Test (3,402 matches; model fitted on train + validation with the train+val goal layer; baseline = production model with the train-only layer)

| Segment | n | Metric | Baseline | Model | Diff (90 % CI) |
|---|---|---|---|---|---|
| all | 3,402 | 1X2 log loss | 0.99601 | 0.99515 | -0.00086 (-0.00234 … +0.00058) |
| | | 1X2 Brier | 0.59442 | 0.59394 | -0.00048 (-0.00151 … +0.00048) |
| | | O/U 2.5 log loss | 0.67341 | 0.66817 | -0.00524 (-0.00668 … -0.00381) |
| | | BTTS log loss | 0.68354 | 0.68206 | -0.00147 (-0.00250 … -0.00042) |
| | | exact score | 2.95790 | 2.95139 | -0.00650 (-0.00902 … -0.00401) |
| league | 3,231 | 1X2 log loss | 0.99829 | 0.99718 | -0.00111 (-0.00247 … +0.00030) |
| | | O/U 2.5 log loss | 0.67302 | 0.66768 | -0.00534 (-0.00690 … -0.00389) |
| European | 171 | 1X2 log loss | 0.95284 | 0.95671 | +0.00387 (-0.00861 … +0.01654) |
| | | 1X2 Brier | 0.56304 | 0.56548 | +0.00244 (-0.00598 … +0.01101) |
| | | O/U 2.5 log loss | 0.68065 | 0.67725 | -0.00340 (-0.01129 … +0.00487) |
| model fav >= 0.70 | 294 | 1X2 log loss | 0.69014 | 0.68622 | -0.00392 (-0.01048 … +0.00231) |

Control with the baseline on the same train+val goal layer: 1X2 -0.00095 (-0.00244 … +0.00047), European +0.00471
(-0.00780 … +0.01733), O/U 2.5 -0.00451 (-0.00588 … -0.00316). Mean total goals: model 2.860, baseline 2.816, actual 2.896.
Per competition (1X2, baseline -> model): Champions League 0.8735 -> 0.8685 (63), Europa League 0.9864 -> 0.9966 (63),
Conference League 1.0170 -> 1.0245 (45); league differences are within +-0.01 except Eredivisie +0.0064 and Czech +0.0030
(full table in the report, `test.by_competition_1x2`).

**Favourites (1X2, test).**

| Threshold | Model n | hit rate | mean pred | Baseline n | hit rate | mean pred |
|---|---|---|---|---|---|---|
| >= 0.60 | 750 | 0.696 | 0.693 | 727 | 0.707 | 0.688 |
| >= 0.70 | 294 | 0.759 (90 % CI 0.718 … 0.799) | 0.769 | 268 | 0.761 (0.716 … 0.802) | 0.765 |
| >= 0.80 | 76 | 0.816 | 0.848 | 60 | 0.833 | 0.844 |
| >= 0.85 | 28 | 0.786 | 0.887 | 21 | 0.762 | 0.883 |
| >= 0.90 | 8 | 1.000 | 0.926 | 4 | 0.750 | 0.928 |

Favourite probability bands (model: n, predicted, actual): 0.33-0.40: 502, .383, .353; 0.40-0.50: 1,249, .448, .456;
0.50-0.60: 901, .546, .548; 0.60-0.70: 456, .645, .656; 0.70-0.80: 218, .741, .739; 0.80-0.85: 48, .825, .833;
0.85-0.90: 20, .872, .700; 0.90-1.00: 8, .926, 1.000. Baseline: 0.70-0.80: 208, .743, .740; 0.80-0.85: 39, .823, .872;
0.85-0.90: 17, .872, .765. Other markets' calibration bands are in the report (`test.calibration`, European in
`test.calibration_european`).

**Closing odds (test matches with odds; de-vigged `p_close_*`).** `football_data_matches.csv` via `db_match_id` and
`football_data_history.csv` via `fotmob_match_id`: 2,234 matches (1,965 with O/U 2.5), all league matches; none of the 171
European test matches has closing odds in these files.

| | Market | Model | Baseline | Model - market (90 % CI) | Baseline - market |
|---|---|---|---|---|---|
| 1X2 log loss | 0.99213 | 1.00449 | 1.00570 | +0.01236 (+0.00735 … +0.01747) | +0.01357 (+0.00843 … +0.01885) |
| O/U 2.5 log loss | 0.66494 | 0.66971 | 0.67556 | +0.00477 (+0.00144 … +0.00842) | +0.01062 (+0.00699 … +0.01453) |

### 6. Deploy criteria (test, vs the baseline)

| | Rule | Result | Verdict |
|---|---|---|---|
| (a) | 1X2 log loss paired 90 % CI upper bound < 0 | -0.00086, CI upper +0.00058 | **fail** |
| (b) | European subset not worse (mean diff <= 0; CI shown) | +0.00387, CI -0.00861 … +0.01654, n = 171 | **fail** (point estimate; CI covers 0) |
| (c) | O/U 2.5 not worse beyond the CI (CI lower bound <= 0) | -0.00524, CI -0.00668 … -0.00381 | pass |

All three are needed -> **do not deploy**. `deploy_criteria` in `match_model_candidate_full.json` carries the same numbers.

### 7. Candidate (`match_model_candidate_full.json`, DRAFT, nothing in `backend/config/` was written)

Contains the exact equation, the frozen configuration, per-term definitions (source column per equation, mean, sd,
coefficient per sd and per unit, clip, missing rule), missing indicators, UEFA block, score model (rho, NB dispersion),
goal layer for deployment (`goal_layer_trainval.json`, parameters inline), the ratings files (`player_impact_asof_all.csv.gz`
for matches, `player_impact_latest.json` for runtime), and three fits: `evaluated_model` (train + validation, tested),
`validation_model` (train only) and `refit_all_rows` (train + validation + test, deployment refit, not evaluated).
Evaluated coefficients per sd: value 0.0166, XI offence 0.0254, XI defence -0.0241, xG for 0.0281, xG against 0.0187,
points 0.0084 / 0.0053, unavailable offence +0.0021 and defence -0.0068 (wrong signs, see above); UEFA block: e_home +0.045,
e_away -0.078, e_total +0.001, e_diff -0.054 (UEFA rating differences shrunk by ~5 %), e_value +0.047 per sd (value effect
in UEFA matches ~0.053 per ln unit, close to the production cross-league beta 0.048).

### 8. Verification and caveats

- Commands (from `backend/`; scratch `DATABASE_URL`; ~3 min of compute in total):
  `build_match_features.py` (145 s, command in `match_features_full_report.json` inputs), `baseline_predictions.py` (3 s),
  `export_player_impact_latest.py`, `train_match_model_full.py --stage select` (33 s), `--stage final` (8 s),
  `describe_match_features.py`, `player_impact_run_summary.py`.
- Tests (scratch `DATABASE_URL`): 135 passed (collectors, football-data, rate limiter, feature / stage-A / full-run tests
  and the 3 new ones; `tests/test_match_model_runtime.py` belongs to the paused integration and was not run).
  The new tests check the stationary point of the analytic gradient, missing -> 0 + indicator and
  the clip, that changing test labels does not change the select stage, and the final stage end to end (strict JSON, files).
- The `final` stage ran three times with identical results (byte-identical prediction files, same report numbers and
  coefficients); the second run only made the closing-odds block write `n = 0` instead of NaN for the (empty) European
  subset, the third wrote repo-relative paths into the candidate JSON. The model, its configuration and its numbers did
  not change between the runs. No choice was made after seeing test numbers.
- Caveats: the baseline's beta / gamma overlap the validation / test periods (above); test European n = 171 is small
  (CI +-0.012); the `absent` group has wrong signs and a 0.0002 gain; value-ratio missingness is time-dependent;
  predicted (not confirmed) line-ups were not tested; no value-bet backtest was run (not requested).

## Bağımsız denetim (Opus, 14 Ekim 2026) — sonuç: sağlam, çekinceli

- **Sızıntı yok.** Gerçek test kesimlerinde bozma (perturbation) testleri reytingleri ve λ'ları değiştirmedi; seçim
  aşaması yeniden çalıştırılınca aynı donmuş ayar ve 28 adımlık iz çıktı; 24 rastgele test maçının 432 girdisi ham
  dosyalardan yeniden hesaplandı, 0 uyuşmazlık. Final aşaması yeniden çalıştırıldı: tahmin dosyaları bayt bayt aynı.
- **Rakamlar tekrar üretildi** (yukarıdaki tablo; 10.000 örnekli bootstrap da aynı aralıkları verdi).
- **Düzeltme:** Raporda "üretimin β/γ katsayıları testle örtüştüğü için taban şişkin, karşılaştırma ihtiyatlı" deniyordu.
  Denetim bunu doğrulamadı: β ve γ yalnızca eğitim+doğrulamada yeniden fit edilince taban test 1X2'si 0,9945–0,9956
  çıkıyor, yani yeni modelle aynı ya da daha iyi. "Canlıya alma" kararı bu yüzden daha da güçlü.
- **Öneriler:** Yeni modeli 1X2 için bağlama; `backend/config/` boş kalsın. Eksik oyuncu grubu (katsayı işaretleri ters,
  kazanç ~0,0002) her durumda çıkarılmalı. Gol pazarlarındaki küçük ama gerçek kazanç (2.5 Alt/Üst −0,005) ayrı ve
  önceden yazılmış ölçütlerle ayrıca doğrulanırsa yalnızca gol pazarları için kullanılabilir.

# Player-impact pipeline — stage A (stints → as-of xG-RAPM → XI strength)

Status 2026-10-13: built and validated on the 2025-07 → 2026-10 FotMob details (6,798 matches). **Not wired into the
live prediction pipeline** — that is the lead's decision (numbers below). Every number in this document comes from
the files named next to it; dataset field definitions are in `backend/data/training/README_player_impact.md`.

## Özet (Türkçe)

- Her maç, oyuncu değişikliği ve kırmızı kartlar arasındaki "sahada aynı 11'ler" dilimlerine (stint) bölündü:
  48.722 dilim, 6.798 maç. Maçların %97,9'u kullanılabilir (kadro tutarlı, goller skorla birebir, dakikalar FotMob ile
  ±3 dk içinde). xG toplamları FotMob'un şut haritasıyla birebir; takım istatistiğindeki xG ile maçların %71,7'sinde
  ±0,05 içinde — farkın kaynağı FotMob'un iki ayrı xG sürümü (aşağıda).
- Her hafta için (60 kesim) yalnızca o tarihten önceki maçlarla oyuncu reytingi (xG-RAPM, kutu skoru önsel dağılımlı)
  eğitildi. Zaman-ileri doğrulamada oyuncu modeli, yalnız takım düzeyindeki modele göre bir sonraki 4 haftanın dilim
  xG'sini 10 kesimin 10'unda daha iyi tahmin etti.
- Soru: "Sahaya çıkan 11'in gücü, takımın olağan 11'ine göre, reyting λ'sının ötesinde golleri açıklıyor mu?"
  **Evet.** Ayrılmış 894 maçta 1X2 log loss 0,9716 → 0,9678 (%90 GA −0,0065…−0,0012). Üretimdeki değer+form
  düzeltmesinin (0,9615) üzerine eklenince 0,9600; fark küçük (−0,0015) ve bu eğitim setiyle anlamlı değil, Eylül
  2025'ten başlayan daha uzun eğitim setiyle anlamlı (−0,0014, %90 GA −0,0027…−0,0001). Değer+RAPM, değer+formdan
  her iki kurulumda da en az onun kadar iyi → form sinyalinin yerini alabilir.

## Pipeline and commands (from `backend/`)

```
venv/Scripts/python.exe scripts/training/build_stints.py            # 18 s  -> stints.jsonl.gz, stints_validation.csv, stints_report.json
venv/Scripts/python.exe scripts/training/player_impact.py           # 220 s -> player_impact_asof.csv.gz, player_impact_meta.json
venv/Scripts/python.exe scripts/training/experiment_xi_impact.py    # 13 s  -> xi_impact_experiment.json
venv/Scripts/python.exe scripts/training/experiment_xi_impact.py \
    --lambdas data/training/walkforward_lambdas_xg_2025h2.csv --lambdas data/training/walkforward_lambdas_xg.csv \
    --out data/training/xi_impact_experiment_extended.json
venv/Scripts/python.exe -m pytest tests/test_player_impact.py tests/test_player_impact_stints.py
```

Total ≈ 4.5 minutes on the current data (16-core Windows machine). All three scripts are deterministic: two runs give
byte-identical `stints.jsonl.gz`, `stints_validation.csv` and `player_impact_asof.csv.gz` (checked with md5; the tuned
run and a run with the chosen hyper-parameters fixed produce the same ratings file). The match list always comes from
the JSONL files given with `--details` (never from listing the raw directory); unreadable/partial gzip files, missing
raw files and unparsable JSONL lines are skipped and counted in `stints_report.json`.

## 1. Stints (`scripts/training/build_stints.py`)

A stint is a period with unchanged line-ups; boundaries are kick-off, substitutions and red cards that remove an
on-pitch player. Half-time is not a boundary. Raw sources (full list in the script docstring):
`content.lineup.{homeTeam,awayTeam}.{starters,subs}`, `content.matchFacts.events.events[*]` (Substitution:
`swap[0]` = on, `swap[1]` = off — verified on all 61,505 events against the line-up `subIn/subOut` flags; Card with
`card ∈ {Red, YellowRed}`; Goal with `isHome` = benefiting side, `ownGoal`, `newScore`, `shotmapEvent.id`;
AddedTime), `content.shotmap.shots[*]` (`period`, `min`, `minAdded`, `expectedGoals`, `situation`, `isOwnGoal`),
`header.status.halfs` (half start/end timestamps), `content.stats` (team xG), `header.teams[*].score`.

**Stoppage time.** The clock counts minutes of play from kick-off with stoppage included and breaks excluded. Each
half's length = regulation + stoppage, where stoppage comes from the half's own timestamps (plausible in 99.4 % of
first halves), else the announced added time, else the latest stoppage minute seen, and is raised to the latest
stoppage minute seen in that half. Minute label `m` / `m+k` covers [r−1, r), r = m − first minute of the half + k
(46′ = first minute of the second half; 90+4 = fourth stoppage minute). Changes are placed at the start of their minute
(half-time substitutions, labelled 46′, land exactly on the break), shots and goals in the middle. A goal in the same
minute as a change is ordered with the score carried by the change event. Non-goal shots in the same minute as a
change cannot be ordered (no seconds in the source) and count after it: 5,444 shots = 2.44 % of xG. Extra time is
handled the same way (15 + stoppage per half); penalty-shootout kicks/goals are excluded.

**xG / goals.** Stint xG = Σ shotmap `expectedGoals` (own goals never count as xG; penalties excluded from npxG).
Goals come from goal events, own goals credited to the benefiting side. A match without a shotmap (Czech 1. Liga)
gets `null` xG in every stint, never 0.

**Validation** (`stints_report.json`): lineup consistent 99.96 %, goals = final score 100 %, nominal minutes within 1
of FotMob 96.16 % (within 3: 97.88 %), match length plausible 100 % (median 98.6 minutes). Σ stint xG vs the team xG
in `content.stats` within ±0.05: 71.65 % of the 6,444 matches with team xG. The failures are a source inconsistency,
not a segmentation error: FotMob sends per-shot, per-player and per-team xG and in 1,640 matches two of them agree
and the third differs (shots ≠ player-stats = team: 1,088; shots = player-stats ≠ team: 552), 103 have both, 80 are
unexplained, 4 lack a shotmap. Σ stint xG equals the shotmap total exactly. **Usable** = lineup ok + goals ok + all
minutes within 3: 6,654 matches (97.88 %), 6,315 with xG; only these enter the model.

## 2. As-of xG-RAPM (`scripts/training/player_impact.py`)

For each cutoff c (weekly Mondays from 2025-09-01, plus the day after the last match) the model is fitted only on
usable stints with kickoff < c, weights = stint minutes × 0.5^(age/365 d), look-back 730 days. One row per stint and
attacking direction (attacking side A, defending side D):

```
y = 90 · npxG_A / minutes
y ≈ μ + home + competition + 0.52·man_adv + game state (lead / trail share)
      + Σ_{p∈A} (z_p·g_off + d_off_p) − Σ_{q∈D} (z_q·g_def + d_def_q)        [+ optional team intercepts]
offence_p = z_p·g_off + d_off_p     defence_p = z_p·g_def + d_def_p     (xG/90, + = better)
```

- **Prior (Bayesian centre).** z_p = standardised box-score features as of c: npxG/90 and xA/90 (decayed, shrunk with
  450 minutes of the position average), FotMob rating (minutes-weighted, shrunk the same way), log market value (+ a
  missing flag), minutes share of the current team's last 10 matches. The prior weights g are fitted jointly
  (essentially unpenalised); the player deviations d are ridge-penalised towards 0, i.e. each rating is shrunk
  towards its box-score prior instead of towards zero. Position dummies are deliberately NOT in z: every line-up has
  one goalkeeper and ten outfield players, so position constants are not identified (a first version gave
  goalkeepers −0.69 defence). Position still sets the shrinkage targets and the replacement levels.
- **Opponent / league strength.** The defending players enter every row, so opponents are adjusted for directly.
  League level enters through the players (market value is a cross-league quality scale; European matches link the
  leagues) and competition intercepts absorb each competition's scoring level. Team intercepts were tested as an
  alternative (players then identified only from within-team line-up variation) and lost in the validation below,
  so they are off by default (`--team-lambda 1e7`). The walk-forward rating λ is not used as an offset, because the
  XI-vs-usual adjustment is applied on top of that λ later and should not be fitted relative to it.
- **Solver.** Sparse weighted ridge with per-column penalties, normal equations by Jacobi-preconditioned conjugate
  gradients (relative residual < 1e-8; ≈ 60 iterations, ≈ 1 s per cutoff, warm-started from the previous cutoff).
- **Tuning (time-forward).** For validation cutoffs v = 2026-01-05 + 28k (10 cutoffs up to 2026-09-14): fit before v,
  predict the npxG/90 of every stint in [v, v + 28 d) (unseen players get their position's replacement prior), score
  the duration-weighted squared error (WMSE). Grid: λ ∈ {4k, 8k, 16k, 32k, 64k} minutes, half-life ∈ {180, 365},
  team intercepts λ_team ∈ {1000, off}; a first run also had λ = 2000 and λ_team = 10, both clearly worse
  (λ_team = 10: best WMSE 2.496 in that run).

| Model (half-life 365) | WMSE | vs intercepts only |
|---|---|---|
| intercepts + home + competition only | 2.54513 | — |
| team intercepts (λ_team 1000), no players | 2.49340 | −2.03 % |
| player prior only (no deviations), no team intercepts | 2.47977 | −2.57 % |
| team intercepts + prior + deviations (λ 16000) | 2.47726 | −2.67 % |
| **prior + deviations (λ 16000), no team intercepts — chosen** | **2.47465** | **−2.77 %** |

The chosen model beats the team-intercept model without players in all 10 validation windows, and the prior-only
model in all 10 (per-window numbers in `player_impact_meta.json` → `validation.per_cutoff`). Stint xG is very noisy,
so the explainable share is small in absolute terms. The deviations are heavily shrunk (sd ≈ 0.01 xG/90 vs 0.115 for
offence overall): with 1.25 seasons the box-score prior carries most of the signal; more seasons should support a
smaller λ (re-tune on the history).

Latest cutoff (2026-10-13): 10,628 players; home +0.21 npxG/90, one extra player +0.52; prior weights per sd —
offence: npxG/90 0.095, xA/90 0.034, minutes share 0.011, log value 0.008; defence: rating 0.017, log value 0.012.
Top offence (≥ 900 minutes): Osimhen 0.50, Mbappé 0.49, Helmersen 0.48, Olise 0.48, Lautaro 0.47, Raphinha 0.46,
Haaland 0.46; top defence: Rice 0.10, Raya 0.09, Gabriel 0.09, Schlotterbeck 0.08.

Comparison metrics in the same file (same cutoff rule): shrunk npxG/90 + xA/90 (`xgxa90`), `minutes_share`,
shrunk minutes-weighted FotMob `rating`.

## 3. Runtime module (`backend/app/prediction/player_impact.py`, second half)

`PlayerImpactRatings.load(path, as_of=…)` takes the latest cutoff on or before `as_of` (one pass over the file,
≈ 1.4 s). `xi_strength(player_ids, positions)` sums offence/defence; a player without a rating gets the replacement
level of his position (mean prior of players with < 450 minutes, from the meta file) and is listed in
`unknown_player_ids` with the flag `replacement_level_used` — never silently treated as average. `compare_to_usual(xi,
recent_lineups, last_n=10, min_lineups=3)` returns XI − mean of the last N line-ups, both valued at the same cutoff;
fewer than 3 earlier line-ups → `available=False` with a reason, deltas `None`. The legacy `PlayerImpactEngine` above
it is unchanged. Tests: `tests/test_player_impact.py` (runtime) and `tests/test_player_impact_stints.py` (stint
builder and trainer, incl. a no-look-ahead test).

## 4. Does XI strength vs the usual XI explain goals beyond the rating λ?

`scripts/training/experiment_xi_impact.py`: walk-forward rating λ (`walkforward_lambdas_xg.csv`) through the goal
layer, as in `experiment_lineup_strength.py`; split train < 2026-07-01 ≤ test. Features: ratings of the latest cutoff
≤ kickoff (mean age 4.5 days), XI = the match's starters, usual = mean of the team's last 10 starting XIs before the
kickoff valued at the same cutoff (needs ≥ 3). `rapm_split`: log λ_home += κ(ΔO_home − ΔD_away), log λ_away +=
κ(ΔO_away − ΔD_home). Coefficients by maximum likelihood on train; 90 % CIs from 2,000 paired bootstrap resamples of
the 894 held-out matches.

The script reproduces the production experiment exactly (ratings only 0.9716, value 0.9641, form 0.9693, value+form
0.9615 with β 0.0279, γ 0.2157 on 2,462 / 894 matches); every one of these matches also has XI features.

| Held-out 1X2 log loss (894 matches) | train Jan–Jun 2026 (2,462) | Δ vs value+form (90 % CI) | train Sep 2025–Jun 2026 (4,122) | Δ vs value+form (90 % CI) |
|---|---|---|---|---|
| ratings only | 0.9716 | | 0.9716 | |
| form (production) | 0.9693 | | 0.9715 | |
| value (production) | 0.9641 | | 0.9625 | |
| **value + form (production)** | **0.9615** | — | **0.9621** | — |
| RAPM XI vs usual (κ 0.30 / 0.16) | 0.9678 | | 0.9692 | |
| RAPM prior part only | 0.9682 | | 0.9694 | |
| simple: FotMob rating XI vs usual | 0.9687 | | 0.9694 | |
| simple: npxG+xA/90 XI vs usual | 0.9697 | | 0.9702 | |
| simple: minutes share XI vs usual | 0.9712 | | 0.9710 | |
| value + RAPM | 0.9609 | −0.0006 (−0.0033 … +0.0020) | **0.9605** | −0.0016 (−0.0029 … −0.0003) |
| value + form + RAPM | **0.9600** | −0.0015 (−0.0038 … +0.0006) | 0.9607 | −0.0014 (−0.0027 … −0.0001) |

RAPM alone vs ratings only: −0.0038 (−0.0065 … −0.0012), train likelihood-ratio 14.0 (p = 0.0002); with the longer
training set −0.0024 (−0.0039 … −0.0010). Brier and over-2.5 move in the same direction (value+form+RAPM: Brier
0.5704 → 0.5694, O2.5 0.6583 → 0.6577); BTTS stays within 0.001 (0.6819 → 0.6824). 12.7 % of matches have at least
one starter without a rating (replacement level used).

**Answer.** Yes: the starting XI's RAPM strength relative to the usual XI explains goals beyond the walk-forward
rating λ, robustly (significant on held-out data with both training sets). It is better than the production form
signal on its own, and almost all of it comes from the box-score prior part of the ratings. On top of the production
value+form adjustment the extra gain is small (≈ −0.0015 log loss) and only reaches 90 % significance with the longer
training set, where form drops out (γ ≈ 0) and value + RAPM is the best variant. Recommendation for the lead: if
wired, use value + RAPM (`rapm_split`, κ ≈ 0.16–0.30) in place of form, re-fit κ after the history re-run, and keep the
replacement-level flag visible. European-cup matches alone are too few in the test period (< 30 with all features)
to evaluate separately.

## Leakage guards

1. Every fit uses stints with kickoff < cutoff; box-score features (npxG/90, xA/90, rating, minutes share, market
   value, position, team) use details rows with kickoff < cutoff only. A test (`test_no_look_ahead`) adds an extreme
   stint after the last cutoff and checks the ratings file is unchanged.
2. Hyper-parameters are chosen by time-forward validation (fit before v, score after v).
3. In the experiment a match uses ratings of the latest cutoff ≤ its kickoff date (fitted on matches before that
   date); its usual XI uses line-ups strictly before its kickoff; its own starting XI (known before kick-off) is the
   only information from the match itself. κ, β, γ are fitted on train only.
4. Unseen players get a replacement prior chosen from information before the cutoff (fringe players' mean); their
   position comes from the pre-match line-up.
5. Not a leak, but a caveat: the goal layer (`config/goal_model.json`) was fitted on all lambda rows including the test
   period, exactly as in the production experiment; it is shared by all variants.

## Re-running on the multi-season history

```
venv/Scripts/python.exe scripts/training/build_stints.py \
    --details data/training/fotmob_match_details.jsonl --details data/training/fotmob_match_details_history.jsonl \
    --out data/training/stints_all.jsonl.gz --validation-out data/training/stints_all_validation.csv \
    --report data/training/stints_all_report.json
venv/Scripts/python.exe scripts/training/player_impact.py \
    --stints data/training/stints_all.jsonl.gz \
    --details data/training/fotmob_match_details.jsonl --details data/training/fotmob_match_details_history.jsonl \
    --start 2022-11-07 --val-start 2024-01-01 --val-step-days 56 \
    --lambdas 2000,4000,8000,16000 --half-lives 365 --team-lambdas 1e7 \
    --out data/training/player_impact_asof_all.csv.gz --meta data/training/player_impact_meta_all.json
venv/Scripts/python.exe scripts/training/experiment_xi_impact.py \
    --ratings data/training/player_impact_asof_all.csv.gz --meta data/training/player_impact_meta_all.json \
    --details data/training/fotmob_match_details.jsonl --details data/training/fotmob_match_details_history.jsonl \
    --lambdas data/training/walkforward_lambdas_xg_2025h2.csv --lambdas data/training/walkforward_lambdas_xg.csv \
    --out data/training/xi_impact_experiment_all.json
```

- Both details files can be passed together (first occurrence of a match id wins; a partial last line of a file that
  is still being written is skipped and counted). The history rows carry `season`, which is copied into the stints.
- Cost scales roughly linearly with stints. Measured here: one fit ≈ 1 s per 45k stints; the full default run (280
  validation fits + 60 cutoff fits) took 220 s. With ≈ 4× the data use the reduced grid above (smaller λ
  values become plausible with more data; keep 16000 in the grid for comparison) or skip tuning with
  `--lambda … --half-life … --team-lambda …`.
- Cutoffs before the history's first season + a few months have little data; start the ratings a few months after the
  first collected match. The experiment needs walk-forward λ rows for the history period too
  (`walkforward_dataset.py --start … --out <new file>`; the DB only goes back to 2025-07, so older seasons have no λ
  rows yet).
- Check `stints_all_report.json` (usable share per competition) and that the chosen configuration in the meta file
  still beats both baselines in most validation windows.

## Known limitations / next steps

- Only ≈ 1.25 seasons: RAPM deviations are weak; the ratings are mostly the box-score prior.
- Defence is weakly identified (sd 0.024 xG/90 vs 0.115 for offence).
- Czech 1. Liga has no xG: its players are rated from the prior (rating, value, minutes share) unless they played
  European matches with xG.
- Cross-league comparisons of absolute values are approximate; within-team differences (what the XI adjustment uses)
  are the robust quantity.
- Predicted (pre-match) line-ups were not tested; the experiment used confirmed starting XIs.

---

# Stage B — match features, history lambdas, match model (2026-10-13)

Status: built and evaluated on the current data (6,798 details matches, 2025-07 → 2026-10). Everything is ready for
the multi-season re-run (commands below). **Nothing is wired into production and nothing in `backend/config/` was
written.** Dataset fields, coverage and gaps: `backend/data/training/README_match_features.md`.

## Özet (Türkçe)

- Her maç için yalnızca maç başlamadan önce bilinen bilgilerle kimlik ve etiketler dahil 93 sütunluk bir satır üretildi:
  reyting λ'sı (+ üretimdeki gol katmanı), ilk 11 piyasa değeri, üretimdeki kadro formu, ilk 11'in RAPM gücü ve
  takımın olağan 11'ine göre farkı, eksik oyuncular (sakat/cezalı sayısı ve RAPM etkisi), son 5 maç xG ve puan,
  dinlenme günü, 14 günde maç sayısı, 3 gün içinde Avrupa maçı, lige özgü ev sahibi avantajı.
- Geçmiş sezonlar için (2022-08 → 2025-06) üretimdeki reyting koduyla 55.729 walk-forward λ üretildi
  (`walkforward_from_results.py`). Aynı veride üretim koduyla farkı ortalama |Δ ln λ| 0,0002–0,0003.
- Model: λ'nın üstüne L2 cezalı Poisson/Dixon-Coles düzeltmesi (GLM) ve gradyan artırma (HGB). Seçimler yalnızca
  doğrulama setinde yapıldı; test seti (2026-07-11 → 2026-10-11, 1.129 maç) bir kez puanlandı.
- **Sonuç:** Seçilen GLM (piyasa değeri + ilk 11 RAPM farkı + son 5 maç xG/puan) 1X2 log loss'u 0,9758'den
  0,9716'ya indirdi (Δ −0,0041, %90 GA −0,0083…−0,0002); skor log loss −0,0081 (−0,0143…−0,0021). Lig maçlarında
  iyileşme var; 36 Avrupa kupası test maçında ise kötüleşme var (+0,028, GA +0,005…+0,052). HGB, taban modelden
  ayırt edilemedi.
- Doğrulamada işe yarayan gruplar: piyasa değeri, ilk 11 RAPM farkı, son 5 maç formu. Eksik oyuncu listesi,
  dinlenme/yoğunluk, lig ev avantajı ve üretimdeki kadro formu katkı vermedi (onaylanmış ilk 11 bilindiğinde).
- Kapanış oranlarına karşı (591 test maçı): piyasa 0,9764, taban 0,9947, GLM 0,9886. Fark üçte bir kapandı ama
  piyasa geçilemedi; değer bahisleri hâlâ zararda (GLM −%8,8, %90 GA −%20,0…+%2,5).

## Pipeline and commands (from `backend/`)

```
venv/Scripts/python.exe scripts/training/walkforward_from_results.py --start 2022-08-01 --end 2025-06-30 \
    --out data/training/walkforward_lambdas_results_2022_2025.csv                                  # 36 s (4 workers)
venv/Scripts/python.exe scripts/training/walkforward_from_results.py --start 2025-06-30 --end 2025-08-04 \
    --out data/training/walkforward_lambdas_results_2025_07.csv                                    # 6 s
venv/Scripts/python.exe scripts/training/walkforward_from_results.py --compare \
    --out data/training/walkforward_from_results_check.json                                        # 60 s
venv/Scripts/python.exe scripts/training/build_match_features.py                                    # 50 s -> match_features.csv.gz
OMP_NUM_THREADS=4 venv/Scripts/python.exe scripts/training/train_match_model.py                     # 113 s -> match_model_report.json, match_model_candidate.json
DATABASE_URL=sqlite:///<scratch>/scratch.db venv/Scripts/python.exe -m pytest tests/test_match_features_training.py
```

These scripts are deterministic. A second run of `build_match_features.py` gave a byte-identical CSV (md5
`f50bd0a1…`), and a second run of `train_match_model.py` gave an identical report and candidate (apart from
`built_at`, `seconds` and `note`).

## 1. Features (`build_match_features.py`)

One row per details match with the groups below (per-side columns for home and away). Exact definitions are in
the README and the script docstring.

| Group | Content |
|---|---|
| base | walk-forward rating λ (first lambdas file containing the match) → production goal layer |
| value | starters' market value per side; ln(V_home / V_away) |
| form_prod | production lineup form (re-used from stage A's `production_features`, which reproduces `experiment_lineup_strength.py`) |
| xi | stage-A RAPM: XI offence/defence (11 starters, unrated → position replacement level), usual XI (last 10 line-ups before kick-off, same cutoff, ≥ 3), XI − usual. Identical to stage A's `xi_features` (6,017 matches, max diff 5e-7) |
| absent | FotMob `unavailable` list: key sent or not (raw response), counts by type, Σ (rating − replacement level), and the same weighted by minutes share |
| form | last 5 details matches: team xG for/against (≥ 3 with xG); last 5 competitive results: points, goals |
| rest | days since the previous competitive match, matches in 14 days, European match ≤ 3 calendar days before / after |
| context | competition type; competition home advantage (365 days, shrunk) minus the global one |

**Leakage guards.** Every history-based value uses kick-off < this kick-off, without the match's own id or a
duplicate fixture of the pair within 1 day. Ratings come from the latest cutoff strictly before kick-off. From the
match itself, only its line-up (starters, usual positions, starter value) and the unavailable list are read.
`euro_after_3d` uses the schedule only.

The tests (`tests/test_match_features_training.py`, synthetic data) check:
- Every feature stays unchanged when adding later matches, later results (incl. European) or later rating cutoffs
  with different values.
- Every feature also stays unchanged when the match's own score, xG, player ratings or minutes change.
- The `euro_after` flag depends only on the date of the later fixture, not on its result.
- A cutoff equal to the kick-off is not used.

**Unavailable lists look like pre-match snapshots (checked, not proven).** Of 17,978 listed players in the current
file, none appeared in the match. The key is absent for 24 % of sides; there the counts are null (unknown), not 0.

## 2. History lambdas (`walkforward_from_results.py`)

Same columns and method as `walkforward_dataset.py` (production `GlobalPoissonRatings`, `domestic_groups` by
competition id, `XG_GOAL_WEIGHT`, lookback 400 d). Matches come from `data/history/all_results.db`, and ids are
FotMob ids. Data rules:
- `awarded = 1` rows are dropped (232); `awarded` NULL is kept.
- Reggiana's split id 959006 is mapped to 6500.
- Optional `--xg-details` fills team xG from a details JSONL (both values required).

Cutoffs run in a process pool; the output order is fixed.

- Reproduction against `walkforward_lambdas_xg.csv`: mean |Δ ln λ| 0.0022–0.0026 (95–96 % within 1 %). The original
  DB code, refitted now on the current DB, differs from that file by the same 0.0022, so the DB has changed since
  the file was built. Against a fresh fit on the current DB, the port differs by 0.0002–0.0003 (max 0.008; 95.7–99.6 %
  within 0.1 %). The training sets differ by one match, which has an invalid team id. Stored in
  `walkforward_from_results_check.json`.
- History run: 152 cutoffs 2022-08-01 → 2025-06-23, 55,729 rows. Every TARGET13 history match since 2022-08-01 has
  a lambda (3,743 / 3,742 / 3,826 per season). Another 1,822 rows cover the July 2025 gap.
- **History rows are goals-only.** The table has xG only for production rows, and the history details file was still
  being collected. Re-run with `--xg-details data/training/fotmob_match_details_history.jsonl` when it is complete.

## 3. Match model (`train_match_model.py`)

Split: train < 2026-04-01 (4,396 matches), validation 2026-04-01 … 2026-06-30 (1,135), test ≥ 2026-07-01 (1,129;
2026-07-11 … 2026-10-11, 36 European).

- (a) **baseline_production**: λ + goal layer, value β 0.048 (European) / 0.0279 (domestic), form γ 0.2157.
  Missing value or form means no shift. Production ρ −0.023 / NB 50.
- (b) **GLM**: log μ_side = log λ_side + c_side + α (log λ_side − m) + Σ β·z.
  - z is standardised on train, from the scoring side's and the conceding side's view, with one missing indicator
    per block.
  - The likelihood is NB × Dixon-Coles on the exact score, identical to `train_goal_model.score_matrix`. Its
    analytic gradient was checked to 1e-8. ρ and the NB dispersion are fitted together with the coefficients.
  - Validation chose L2 = 3000 and the recalibration terms ON (validation score 2.9431 vs 2.9494 without).
    Backward elimination then kept **value, xi, form**.
- (c) **HGB**: one stacked Poisson model (side rows + is_home), with log λ of both sides as features.
  - Monotone constraints: own log λ (+), value (+), own XI offence delta (+), opponent XI defence delta (−), own lost
    offence (−), opponent lost defence (+).
  - A 48-point grid was searched on validation. Best: lr 0.03, 4 leaves, min leaf 50, L2 10, 144 iterations (the
    iteration with the lowest validation deviance).
  - ρ and the NB dispersion were fitted on validation predictions.
- The final models were refitted on train + validation, and the test set was scored once.

**Test (1,129 matches; Δ = model − baseline, paired bootstrap 2,000, 90 % CI; lower is better)**

| Model | 1X2 LL | 1X2 Brier | O/U 2.5 LL | BTTS LL | Score LL | Δ 1X2 LL | Δ score LL |
|---|---|---|---|---|---|---|---|
| baseline_production | 0.9758 | 0.5808 | 0.6635 | 0.6833 | 3.0220 | — | — |
| baseline, goal layer refitted on train+val only | 0.9753 | 0.5807 | 0.6663 | 0.6829 | 3.0247 | −0.0004 (−0.0017…+0.0009) | +0.0027 (−0.0001…+0.0058) |
| GLM, no features (recalibration only) | 0.9864 | 0.5879 | 0.6669 | 0.6828 | 3.0396 | +0.0107 (+0.0067…+0.0145) | +0.0176 (+0.0111…+0.0241) |
| GLM, all groups | 0.9718 | 0.5783 | 0.6613 | 0.6816 | 3.0131 | −0.0039 (−0.0084…+0.0002) | −0.0089 (−0.0155…−0.0023) |
| **GLM selected (value + xi + form)** | **0.9716** | **0.5782** | 0.6621 | 0.6821 | 3.0139 | **−0.0041 (−0.0083…−0.0002)** | **−0.0081 (−0.0143…−0.0021)** |
| HGB | 0.9751 | 0.5801 | 0.6650 | 0.6811 | 3.0248 | −0.0007 (−0.0062…+0.0048) | +0.0029 (−0.0059…+0.0116) |

The selected GLM by competition type:
- League (1,093 matches): Δ 1X2 −0.0052 (−0.0094…−0.0010).
- **European (36 matches): +0.0281 (+0.0053…+0.0519)**; baseline 0.7455 → 0.7736.

The model shrinks rating differences (α = −0.30) and lets value and xG form carry part of the strength. That helps
inside leagues and hurts lopsided European ties. Calibration tables (home / draw / away / over 2.5 / BTTS deciles) are
in the report. All models under-predict goals in the test period: mean predicted total 2.91–2.96 vs 3.06 actual.

Selected GLM coefficients (train + validation fit; per sd / per unit):

| Term | Per sd | Per unit |
|---|---|---|
| value | 0.078 | 0.064 per ln-ratio unit |
| XI offence delta | 0.017 | 0.11 per xG/90 |
| opponent XI defence delta | −0.014 | −0.26 |
| xG for (last 5) | 0.039 | 0.083 |
| opponent xG against (last 5) | 0.010 | 0.022 |
| points last 5, own | 0.004 | |
| points last 5, opponent's | 0.014 (small, unexpected sign) | |

Other parameters: c_home 0.024, c_away −0.056, α −0.304, ρ −0.056, NB dispersion at the upper bound (≈ Poisson).

**Ablations (validation, fitted on train; exact-score log loss; Δ vs the GLM without features unless stated)**

| Group | Alone | Removed from all groups (vs all groups) |
|---|---|---|
| value | −0.0032 (−0.0071…+0.0009) | +0.0038 (−0.0003…+0.0078) |
| xi (XI vs usual) | **−0.0018 (−0.0029…−0.0006)** | **+0.0022 (+0.0009…+0.0034)** |
| form (xG / points last 5) | **−0.0047 (−0.0076…−0.0021)** | **+0.0045 (+0.0019…+0.0073)** |
| form_prod (production lineup form) | +0.0006 (+0.0001…+0.0011) | −0.0001 (−0.0008…+0.0005) |
| absent (unavailable lists) | +0.0013 (−0.0007…+0.0036) | −0.0006 (−0.0026…+0.0015) |
| rest / congestion | +0.0015 (+0.0005…+0.0025) | −0.0007 (−0.0013…−0.0003) |
| context (comp type, league home adv.) | +0.0003 (−0.0005…+0.0010) | −0.0002 (−0.0008…+0.0004) |

All groups together vs no features: −0.0076 (−0.0130…−0.0022).

The HGB ablations agree on form (+0.0035 when removed). They give a small gain for absent (+0.0011) and xi
(+0.0009). Removing rest, context or form_prod improves the HGB slightly.

With a confirmed XI, the absentee lists add nothing measurable. They may matter for predicted line-ups, which were
not tested. Per-league home advantage does not matter beyond the global one here.

**Against the closing market (591 test matches with closing odds; 496 with O/U 2.5)**

| | Market | Baseline | GLM selected | GLM all | HGB |
|---|---|---|---|---|---|
| 1X2 log loss | 0.9764 | 0.9947 | 0.9886 | 0.9883 | 0.9893 |
| O/U 2.5 log loss | 0.6612 | 0.6723 | 0.6698 | 0.6677 | 0.6704 |

The models close about a third of the 1X2 gap to the market.

Flat-stake value bets at closing odds (EV ≥ 3 %, conflict guard of `benchmark_vs_market.py`):
- Baseline: 547 bets, ROI −16.5 % (−26.5…−6.9).
- GLM selected: 549 bets, −8.8 % (−20.0…+2.5).
- HGB: 609 bets, −5.9 % (−16.9…+5.2).

No model shows an edge over the closing market.

**Run history (also in the report's `note`).** A development run (small HGB grid, 300 bootstrap resamples, same
splits) printed test numbers before the final run. After it, two changes were made, both based on validation numbers:
- The GLM recalibration terms became a switch chosen on validation, because recalibration alone was worse than the
  baseline on validation (+0.0025 1X2).
- The no-look-ahead goal-layer baseline was added.

Validation chose the same GLM as in the development run, so its test numbers did not change. The HGB numbers changed
only through the planned full grid (0.9738 → 0.9751).

## Re-running on the multi-season history

1. When `fotmob_match_details_history.jsonl` is complete, refit the history lambdas with xG:
   `walkforward_from_results.py --start 2022-08-01 --end 2025-06-30 --xg-details data/training/fotmob_match_details_history.jsonl --out data/training/walkforward_lambdas_results_2022_2025_xg.csv`
   (and the same for `--start 2025-06-30 --end 2025-08-04`).
2. Re-run stage A on both details files (commands above, → `player_impact_asof_all.csv.gz`, `player_impact_meta_all.json`).
3. Features:
   ```
   venv/Scripts/python.exe scripts/training/build_match_features.py \
       --details data/training/fotmob_match_details.jsonl --details data/training/fotmob_match_details_history.jsonl \
       --lambdas data/training/walkforward_lambdas_results_2022_2025_xg.csv --lambdas data/training/walkforward_lambdas_results_2025_07.csv \
       --lambdas data/training/walkforward_lambdas_xg_2025h2.csv --lambdas data/training/walkforward_lambdas_xg.csv \
       --ratings data/training/player_impact_asof_all.csv.gz --meta data/training/player_impact_meta_all.json \
       --out data/training/match_features_all.csv.gz --report data/training/match_features_all_report.json
   ```
   Checked on the partial history file (19,110 matches, 18,946 with a lambda, 122 s).
4. Model, keeping the current test window for comparability (choices again on validation only):
   `train_match_model.py --features data/training/match_features_all.csv.gz --start 2022-11-01 --train-end 2026-01-01 --val-end 2026-07-01 --out data/training/match_model_report_all.json --candidate data/training/match_model_candidate_all.json`
   (set `--start` a few months after the first rating cutoff of the history ratings).

## Recommendations / open points

- Do not wire the candidate yet. Its gain is small (−0.004 1X2 on 1,129 matches, 90 % CI just below 0), it is worse
  on European matches, and it does not beat the closing market. Re-run on the multi-season data first, then decide.
- For the re-run, add competition-type-specific terms (α and value for European matches) and choose them on
  validation. Three seasons give about 1,000 or more European matches.
- The production lineup form (`config/player_form.json`) added nothing on validation here, nor in stage A's longer
  training set. XI vs usual (RAPM) and recent xG form carry that signal.
- The production goal layer's in-sample fit flatters the baseline on O/U 2.5 (+0.0028 log loss when refitted without
  look-ahead) and slightly on the exact score. Refit it walk-forward before comparing future models.

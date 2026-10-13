# Model eğitimi — 13 Ekim 2026

Bütün sonuçlar **walk-forward** (zaman ileri) ve sızıntısızdır: her tahmin yalnızca o maçtan
önceki veriyle fit edilmiş bir modelden gelir. Metrik olarak log loss kullanıldı (düşük daha iyi).
Script'ler `backend/scripts/training/`, veri `backend/data/training/` ve `backend/data/external/`
altında (ikisi de git'e girmez); üretim parametreleri `backend/config/` altında.

## Veri

| Kaynak | İçerik | Toplayan |
|---|---|---|
| Veritabanı (FotMob) | 86.025 bitmiş maç, 2025-07 → 2026-10 | önceki adım |
| FotMob maç detayları | Takım xG'si, ilk 11, oyuncu dakika / puan / xG / xA / piyasa değeri, eksikler — büyük 5 lig + CL/UEL/UECL + 12 lig daha | agent 1 (`collect_fotmob_details.py`) |
| football-data.co.uk | 10.611 maç, kapanış oranları (Pinnacle / piyasa ortalaması), DB maçlarıyla eşlenmiş | agent 2 (`collect_football_data.py`) |
| ClubElo | Bugünkü tüm kulüpler + 29 kulübün haftalık geçmişi (API erişilemedi) | agent 2 (`collect_clubelo.py`) |

## Eğitilen ve devreye alınanlar

### 1. Gol katmanı (`config/goal_model.json`, `app/prediction/goal_model.py`)
Teşhis: reyting λ'ları toplam golü fazla uç veriyordu (az gol beklenen maçlarda gerçek daha
yüksek, çok gol beklenende daha düşük). Toplam gol log uzayında ortalamaya büzülür, ev/deplasman
farkı korunur; Dixon-Coles rho ve NB dağılımı yeniden fit edildi.

Ayrılmış test (2026-07-01 sonrası, 18.329 maç):

| | 1X2 | 2.5 Üst | 3.5 Üst | KG | Skor |
|---|---|---|---|---|---|
| Önceki canlı ensemble | 0.9928 | 0.6702 | 0.6238 | 0.6852 | 3.0311 |
| **Gol katmanı** | **0.9924** | **0.6651** | **0.6191** | **0.6806** | **3.0238** |

Parametreler (tüm veriyle): a = 0.676, b = 0.034, rho = −0.023, NB r = 50. Ayrıca Form modeli
reyting varken devre dışı (formu ikinci kez sayıyordu).

### 2. xG'li reytingler (`team_ratings.XG_GOAL_WEIGHT = 0.5`)
Takım gücü, xG bilinen maçlarda `0.5·gol + 0.5·xG` hedefiyle fit edilir. 1.442 maçlık walk-forward:

| Hedef | 1X2 | 2.5 Üst | KG | Skor |
|---|---|---|---|---|
| Yalnızca gol | 0.9912 | 0.6704 | 0.6795 | 2.9570 |
| **%50 gol + %50 xG** | **0.9895** | **0.6684** | **0.6779** | **2.9485** |

xG 6.444 maç için `matches.home_xg/away_xg` sütunlarına yazıldı (`backfill_match_xg.py`; tam FotMob
verisiyle 4.296'dan 6.444'e çıktı). Yukarıdaki walk-forward tablo 4.296 maçlık xG ile üretildi.

### 3. Kadro gücü (`config/player_form.json`, `app/prediction/lineup_form.py`)
Sahaya çıkan 11'in oyuncu bazlı geçmiş FotMob puanı, takımın olağan 11'ine göre (sakatlık,
rotasyon, ceza etkisi) + ilk 11 piyasa değeri. Tam FotMob verisiyle (6.798 maç; eğitim 2.462,
ayrılmış test 894 maç, 2026-07-01 sonrası):

| | 1X2 | Brier | 2.5 Üst | Skor |
|---|---|---|---|---|
| Yalnızca reyting | 0.9716 | 0.5770 | 0.6596 | 3.0392 |
| + piyasa değeri | 0.9641 | 0.5721 | 0.6587 | 3.0284 |
| + oyuncu formu | 0.9693 | 0.5754 | 0.6594 | 3.0357 |
| **+ değer + form** | **0.9615** | **0.5704** | **0.6583** | **3.0247** |

Katsayılar: form γ = 0.216; piyasa değeri β = 0.028 (lig içi), 0.048 (Avrupa kupaları).
Oyuncu tablosu: 8.349 oyuncu, 348 takımın olağan 11'i. (İlk kısmi veriyle — 651 test maçı — γ 0.125,
β 0.020, 0.9706 → 0.9623 bulunmuştu; yön aynı, etki tam veriyle biraz daha büyük.)

## Piyasaya karşı (en önemli sonuç)

Kapanış oranlarıyla 5.748 maç (kadro düzeltmeleri hariç model):

| | Model | Kapanış piyasası |
|---|---|---|
| 1X2 log loss | 1.0246 | **1.0048** |
| 2.5 Alt/Üst log loss | 0.6806 | **0.6749** |
| "Değer" bahisleri (EV ≥ %3), 4.834 bahis | ROI **−%9.4** (%90 GA −%12.7 … −%5.9) | |
| "Değer" bahisleri (EV ≥ %8), 3.056 bahis | ROI **−%11.0** | |

Model + piyasa logaritmik havuzlaması (ayrılmış 3.046 maç): model ağırlığı 0.025, karışım
1.0087 vs piyasa 1.0084 → **model kapanış piyasasına bilgi eklemiyor.**

Sonuç: Sistemin "değer" etiketleri şu an kanıtlanmış bir avantaja dayanmıyor. Kadro düzeltmeleri
farkın yaklaşık yarısını kapatabilir (1X2'de ~0.008), ama piyasayı geçtiği gösterilmedi.
Öneri: değer etiketlerini "kanıtlanmamış" olarak işaretlemek ya da seçimleri piyasa-ağırlıklı
olasılıkla yapmak; açılış oranlarından kapanışa hareketi (CLV) ölçmek.

## Kullanılmayanlar

- ClubElo: tarihsel anlık görüntüler alınamadı, doğrulanamadı → modele eklenmedi (bu akşamki
  9 maçta ClubElo, modelimize ve piyasaya yakın; ör. Viking–Bayern 9/15/76).
- Ensemble ağırlık öğrenimi: çalışan modeller aynı λ'yı paylaştığı için anlamsız; ileride ya tek
  model ya gerçekten farklı modeller.

## Yeniden çalıştırma

```
cd backend
venv/Scripts/python.exe scripts/data_collection/collect_fotmob_details.py   # yeni maçlar
venv/Scripts/python.exe scripts/training/backfill_match_xg.py
venv/Scripts/python.exe scripts/training/walkforward_dataset.py --out data/training/walkforward_lambdas_xg.csv
venv/Scripts/python.exe scripts/training/fit_goal_layer.py --data data/training/walkforward_lambdas_xg.csv
venv/Scripts/python.exe scripts/training/experiment_lineup_strength.py --lambdas data/training/walkforward_lambdas_xg.csv
venv/Scripts/python.exe scripts/training/build_player_form.py
venv/Scripts/python.exe scripts/training/benchmark_vs_market.py
```

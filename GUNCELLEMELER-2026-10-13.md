# TUTAR X — Güncelleme notları (13 Ekim 2026)

Kısaca: tahmin motoru baştan eğitildi ve hataları düzeltildi, arayüz sadeleşti, canlı veri düzeldi,
4 sezonluk oyuncu/maç verisi toplandı, oyuncu bazlı model eğitim hattı kuruldu. Akşamki Şampiyonlar
Ligi maçları canlı test olarak kullanıldı. Tam veriyle son eğitim yarın bitecek.

Detaylı belgeler: `docs/PROGRESS.md`, `docs/training/`, `docs/live-layer.md`, `docs/CHECKPOINT-2026-10-13.md`.

---

## 1. Düzeltilen hatalar (eski koddan)

- xG formülü ters çalışıyordu → düzeltildi.
- H2H, eşikler ve kalibrasyon hataları düzeltildi; bozuk kalibratör kapatıldı.
- Form modeli, takım reytingi zaten formu içerdiği için formu ikinci kez sayıyordu → reyting varken kapalı.
- Canlı maçlar "planlandı" durumunda takılı kalıyordu → durum ve dakika artık FotMob'dan doğru okunuyor,
  maç saatine 4 saat kala veri önbelleksiz yenileniyor, devre arası doğru gösteriliyor.
- Windows'ta API'nin bağlantı kabul etmeyi bırakması (WinError 64) → `backend/scripts/run_api.py` ile çözüldü.

## 2. Yeni tahmin motoru (canlıda)

| Parça | Ne yapıyor | Dosya |
|---|---|---|
| Takım reytingleri | Bütün liglerdeki maçlardan hücum/savunma gücü (son 400 gün, yakın maçlar daha ağır, %50 gol + %50 xG) | `app/prediction/team_ratings.py` |
| Gol katmanı | Toplam gol beklentisini düzeltir (az/çok gollü maçlarda aşırılığı törpüler) | `config/goal_model.json` |
| Kadro gücü | Sahaya çıkan 11'in piyasa değeri + oyuncuların geçmiş FotMob puanları (sakatlık/rotasyon etkisi) | `config/player_form.json`, `app/prediction/lineup_form.py` |
| Model–piyasa koruması | Model piyasadan 8 puandan fazla ayrışırsa "değer" yerine uyarı | `app/services/odds_service.py` |

Ölçülen sonuçlar (sızıntısız, zaman-ileri test; düşük daha iyi):

| | Önce | Sonra |
|---|---|---|
| 1X2 log loss (651→894 maç kadro testi) | 0.9716 | **0.9615** |
| 2.5 Üst log loss (18.329 maç) | 0.6702 | **0.6651** |
| Skor log loss (18.329 maç) | 3.0311 | **3.0238** |

**Dürüst not:** Kapanış oranlarıyla karşılaştırmada model hâlâ piyasadan biraz zayıf
(5.748 maç: model 1.0246, piyasa 1.0048). "Değer" etiketli bahisler geçmişte −%9.4 getirdi;
arayüzde bu artık açıkça yazıyor.

## 3. Arayüz

- Yeni maç sayfası: ortada pazar "rayı" (1X2, çifte şans, 1.5/2.5/3.5, KG), tıklayınca detay, model vs piyasa.
- Yazı tipi Inter; gereksiz çerçeveler, parlamalar, emojiler kaldırıldı; yüzdeler her yerde "%58" biçiminde.
- Kombine: tek ortak panel, model ihtimali önce, oran kaynağı ("Kullanıcı girişli oran (doğrulanmadı)") her satırda.
- Mobil düzeltmeler (taşma, boş kaydırma, menü), form puanı hesabı düzeltildi (12/15).
- /live sadeleşti, eski canlı detay sayfası maç sayfasına yönleniyor.
- Frontend: 22 test dosyası, 208 test geçiyor.

## 4. Toplanan veri (yeni, `backend/data/` — git'e girmez, ~1.7 GB)

| Veri | Miktar |
|---|---|
| FotMob maç detayları (ilk 11, oyuncu puan/dakika/xG/xA, şut haritası, sakat/cezalı listesi) | 20.048 maç (2022/23 → bugün; 10 büyük lig + ŞL/AL/KL + 7 ek lig) |
| Maç sonuçları (reyting geçmişi) | 168.579 maç, 115 turnuva, 2021 → bugün |
| 2026/27 kadrolar + oyuncu profilleri (yaş, mevki, piyasa değeri geçmişi, sakatlık, son maçlar, kariyer) | 231 kulüp, 6.818 oyuncu |
| Kapanış oranları (football-data.co.uk) | 25.201 + 10.611 maç |

10 büyük lig = UEFA sıralaması: İngiltere, İspanya, İtalya, Almanya, Fransa, Hollanda, Portekiz,
Belçika, **Türkiye**, Çekya. Her veri seti ayrı bir denetimden geçti; eksik değerler uydurulmadı (null).
Toplayıcılar FotMob'a ortak bir hız sınırıyla (≤5 istek/sn) gidiyor: `scripts/data_collection/fotmob_rate.py`.

## 5. Hazır ama henüz açılmamış

- **Canlı katman** (sakatlık/ceza geçmişi, ilk 11, son 5 maç formu): veritabanı tabloları, 15 dakikalık
  yenileme, `/api/v1/matches/{id}/team-news` ve `/api/v1/teams/{id}/squad`. Kurulum adımları: `docs/live-layer.md` §7.
- **Oyuncu bazlı eğitim hattı**: oyuncunun sahadayken takımın xG'sine hücum/savunma katkısı (xG-RAPM),
  maç özellikleri (ilk 11 vs olağan 11, son 5 maç xG, dinlenme), model karşılaştırması.
  Mevcut veride üretim modelinden biraz iyi; 4 sezonluk tam eğitim yarın bitecek (`docs/CHECKPOINT-2026-10-13.md`).

## 6. Bu akşamın canlı testi (Şampiyonlar Ligi, 13 Ekim)

Tahminler maç öncesi donduruldu (v0 eski motor → v5 resmi kadrolu); piyasa, Claude ve kullanıcı seçimleriyle
birlikte puanlandı: `docs/live-tests/2026-10-13-ucl.md`, sonuçlar `docs/live-tests/2026-10-13/results.md`.

## 7. Sıradaki

1. Tam veri eğitimini bitir + bağımsız denetim → daha iyiyse canlıya al.
2. Canlı katmanı aç; maç sayfasına "Kadro & eksikler" (eksiğin son 5 maç katkısı).
3. "Banko" bölümü: model ve piyasanın birlikte ≥ %88–90 gördüğü seçimler + geçmiş isabetleri
   (15.018 maçta favori %80–90 iken %87 kazandı, %96 kaybetmedi).

## Çalıştırma

```
cd backend
python -m venv venv && venv\Scripts\pip install -r requirements.txt   # ilk kurulum
venv\Scripts\python.exe scripts\run_api.py --port 8003

cd frontend
npm install
npm run dev        # http://localhost:5173 (API'ye 127.0.0.1:8003 üzerinden bağlanır)
```

Zip notu: `backend/venv` (~320 MB) ve `frontend/node_modules` (~190 MB) gerekmez, kurulumla oluşur.
`backend/data/` (~1.7 GB) eğitim verisidir; eğitimi o da çalıştıracaksa ekle, sadece uygulamayı açacaksa gerekmez.
Veritabanı `backend/football_intelligence.db` (~83 MB) uygulama için gerekli.

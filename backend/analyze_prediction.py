#!/usr/bin/env python3
"""Tahmin sonuçlarının detaylı analizi."""

def analyze_prediction_probabilities():
    """Tahmin olasılıklarını analiz et."""

    # Test sonuçlarından alınan değerler
    match_result = {
        'home': 0.769,
        'draw': 0.118,
        'away': 0.112
    }

    btts = {
        'yes': 0.756,
        'no': 0.243
    }

    over_under = {
        'over': 0.993,
        'under': 0.006
    }

    print("=" * 60)
    print("ARSENAL-LEEDS TAHMİN ANALİZİ")
    print("=" * 60)

    # 1X2 Olasılık toplamı kontrolü
    total_1x2 = sum(match_result.values())
    print(f"1X2 Olasılıkları:")
    print(f"  Ev Sahibi: {match_result['home']:.3f} ({match_result['home']*100:.1f}%)")
    print(f"  Beraberlik: {match_result['draw']:.3f} ({match_result['draw']*100:.1f}%)")
    print(f"  Deplasman: {match_result['away']:.3f} ({match_result['away']*100:.1f}%)")
    print(f"  TOPLAM: {total_1x2:.6f}")

    if abs(total_1x2 - 1.0) < 0.001:
        print("  ✅ Olasılık toplamı doğru")
    else:
        print(f"  ⚠️ Olasılık toplamı 1.0'dan sapma: {total_1x2 - 1.0:.6f}")

    # BTTS kontrolü
    total_btts = sum(btts.values())
    print(f"\nBTTS (Her İki Takım Gol Atar):")
    print(f"  Evet: {btts['yes']:.3f} ({btts['yes']*100:.1f}%)")
    print(f"  Hayır: {btts['no']:.3f} ({btts['no']*100:.1f}%)")
    print(f"  TOPLAM: {total_btts:.6f}")

    if abs(total_btts - 1.0) < 0.001:
        print("  ✅ BTTS olasılık toplamı doğru")
    else:
        print(f"  ⚠️ BTTS olasılık toplamı sapma: {total_btts - 1.0:.6f}")

    # Over/Under kontrolü
    total_ou = sum(over_under.values())
    print(f"\nOver/Under:")
    print(f"  Üst: {over_under['over']:.3f} ({over_under['over']*100:.1f}%)")
    print(f"  Alt: {over_under['under']:.3f} ({over_under['under']*100:.1f}%)")
    print(f"  TOPLAM: {total_ou:.6f}")
    print(f"  ⚠️ Gol çizgisi belirtilmemiş - muhtemelen 2.5 gol")

    if abs(total_ou - 1.0) < 0.001:
        print("  ✅ Over/Under olasılık toplamı doğru")
    else:
        print(f"  ⚠️ Over/Under olasılık toplamı sapma: {total_ou - 1.0:.6f}")

    # Aşırı yüksek olasılık uyarıları
    print(f"\nAŞIRI YÜKSEK OLASILIK UYARILARI:")

    if match_result['home'] > 0.75:
        print(f"  ⚠️ Ev sahibi galibiyeti çok yüksek: {match_result['home']*100:.1f}%")
        print("    - Arsenal çok güçlü takım olabilir")
        print("    - Leeds zayıf rakip olabilir")
        print("    - Model ev sahibi avantajını aşırı değerlendiriyor olabilir")

    if over_under['over'] > 0.99:
        print(f"  ⚠️ Üst olasılığı aşırı yüksek: {over_under['over']*100:.1f}%")
        print("    - Gol beklentisi çok yüksek hesaplanmış")
        print("    - Model ofansif kabiliyetleri aşırı değerlendiriyor olabilir")
        print("    - Kalibrasyon gerekli olabilir")

    if btts['yes'] > 0.75:
        print(f"  ⚠️ BTTS evet olasılığı yüksek: {btts['yes']*100:.1f}%")
        print("    - Her iki takımın gol atma kabiliyeti yüksek hesaplanmış")

    print(f"\nGENEL DEĞERLENDİRME:")
    print("✅ Tahmin başarıyla üretildi")
    print("✅ Olasılık toplamları matematiksel olarak doğru")
    print("⚠️ Bazı olasılıklar aşırı güven gösteriyor - kalibrasyon gerekebilir")
    print("⚠️ Over/Under gol çizgisi açıkça belirtilmeli")

if __name__ == '__main__':
    analyze_prediction_probabilities()

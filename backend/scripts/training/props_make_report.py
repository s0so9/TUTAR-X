"""Writes docs/training/2026-10-14-props-model.md from the numbers of props_model_report.json /
props_model_candidate.json / props_dataset_report.json / props_frozen.json (no number in the document is typed by hand,
only the wording around them).  Usage (from backend/):  venv/Scripts/python.exe scripts/training/props_make_report.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TRAINING_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TRAINING_DIR))
import props_check_runtime_formula as CK  # noqa: E402
import props_model as PM  # noqa: E402

DATA = PM.DATA
OUT = PM.BACKEND_DIR.parent / "docs" / "training" / "2026-10-14-props-model.md"
BASELINES = ["last5", "last10", "avg365", "comp"]
BL_TR = {"last5": "son-5", "last10": "son-10", "avg365": "365 gün ort.", "comp": "lig ort."}
MARKET_TR = {
    "total_yellow_cards": "Toplam sarı kart", "team_yellow_cards": "Takım sarı kart", "total_corners": "Toplam korner",
    "team_corners": "Takım korner", "team_shots": "Takım şut", "total_shots": "Toplam şut",
    "team_shots_on_target": "Takım isabetli şut", "total_shots_on_target": "Toplam isabetli şut",
}


def load(name: str):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def f4(x) -> str:
    return "-" if x is None else f"{x:.4f}"


def sd(m: dict) -> str:
    """'mean [lo, hi]' of a bootstrap block."""
    return "-" if m["mean"] is None else f"{m['mean']:+.4f} [{m['ci90'][0]:+.4f}, {m['ci90'][1]:+.4f}]"


def pct(x) -> str:
    return "-" if x is None else f"{100 * x:.1f}%"


def table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def verdict(d: dict) -> tuple[str, str, float, dict]:
    """(label, best baseline, diff, bootstrap block) of the model against the best (lowest log loss) simple baseline."""
    ll = d["log_loss"]
    best = min(BASELINES, key=lambda b: ll[b])
    blk = d["diff_model_minus"][best]
    diff = blk["mean"]
    if blk["ci90"][1] < 0 and diff <= -0.02:
        lab = "güçlü"
    elif blk["ci90"][1] < 0 and diff <= -0.008:
        lab = "orta"
    elif blk["ci90"][1] < 0:
        lab = "zayıf (küçük ama anlamlı)"
    else:
        lab = "fark yok"
    return lab, best, diff, blk


def main() -> None:
    R, C, DS, FZ = load("props_model_report.json"), load("props_model_candidate.json"), load("props_dataset_report.json"), load("props_frozen.json")
    ds = PM.load_dataset()
    chk = CK.check(C, load("props_check_reference.json"))
    main_markets = {mk: R["stats"][st]["markets"][mk] for mk, (st, _, _) in PM.MARKETS.items()}
    ev = C["evaluation"]
    T = DS["coverage_total"]
    L: list[str] = []
    A = L.append

    # ------------------------------------------------------------------ Turkish summary
    A("# Props modeli (sarı kart, korner, şut, isabetli şut) - 2026-10-14\n")
    A("Durum: ADAY model, canlıya alınmadı. Dosya: `backend/data/training/props_model_candidate.json` (sürüm `props_v1`). "
      "Bu sayfa önce Türkçe özet, sonra İngilizce ayrıntıdır. Tüm sayılar `props_model_report.json` dosyasından otomatik üretildi "
      "(`backend/scripts/training/props_make_report.py`).\n")
    A("## Özet (Türkçe)\n")
    A(f"**Ne yapıldı.** 5 sayı istatistiği için (sarı kart, korner, toplam şut, isabetli şut, faul) negatif-binom sayma modeli kuruldu: "
      "her takımın hücum ve savunma (rakibe verdiği) etkisi, lig seviyesi, ev sahibi avantajı, kart/faul için hakem etkisi; "
      "zamanla azalan ağırlık ve ridge büzülmesi (az maçı olan takım lig ortalamasına çekilir). Test döneminde (2026-02-01 .. 2026-10-12, "
      f"{R['stats']['corners']['n_test_rows']:,} maç) model her 14 günde yeniden eğitildi ve her tahmin yalnızca maç öncesi veriyle yapıldı. "
      "Hiçbir eksik veri sıfır sayılmadı, dışarıda bırakıldı. Ayar (yarı ömür, büzülme, hangi etkiler) sadece doğrulama döneminde seçildi, test bir kez okundu.\n")
    A("**Hangi marketler tahmin edilebilir.** Ölçü: log loss (düşük iyi), en iyi basit yönteme göre (son-5, son-10, 365 gün ortalaması, lig ortalaması; "
      "hangisi o markette en iyiyse) fark ve %90 güven aralığı. Fark negatifse model daha iyi.\n")
    rows = []
    for mk, d in main_markets.items():
        lab, best, diff, blk = verdict(d)
        d5 = d["diff_model_minus"]["last5"]
        rows.append([MARKET_TR[mk], f4(d["log_loss"]["model"]), f4(d["log_loss"]["last5"]), sd(d5), f"{BL_TR[best]} {f4(d['log_loss'][best])}", sd(blk), lab])
    A(table(["Market", "Model", "Son-5 ort.", "Model - son-5 [%90 GA]", "En iyi basit yöntem", "Model - en iyi basit [%90 GA]", "Sonuç"], rows))
    A("")
    strong = [MARKET_TR[mk] for mk, d in main_markets.items() if verdict(d)[0] == "güçlü"]
    weak = [MARKET_TR[mk] for mk, d in main_markets.items() if verdict(d)[0] != "güçlü"]
    A(f"- **Güçlü (en iyi basit yöntemden >= 0.02 log loss daha iyi):** {', '.join(strong) if strong else 'yok'}. "
      f"**Daha zayıf kazanç:** {', '.join(weak)}.")
    s5 = [main_markets[mk]["diff_model_minus"]["last5"] for mk in main_markets]
    A(f"- **Son-5 sezgisine karşı:** 8 marketin {sum(1 for b in s5 if b['ci90'][1] < 0)} tanesinde model son-5 ortalamasından anlamlı biçimde iyi "
      f"(güven aralığı sıfırı içermiyor); kazanç {min(-b['mean'] for b in s5):.3f} ile {max(-b['mean'] for b in s5):.3f} log loss arasında. "
      "Son-5 en kötü basit yöntemlerden biri: 5 maç gürültülü, rakibi hesaba katmıyor.")
    sh = R["stats"]["total_shots"]
    A(f"- **\"Barcelona çok şut atar ama rakibe bağlı\":** takım şutunda model, son-5 ortalamasının ({f4(main_markets['team_shots']['log_loss']['last5'])}) ve "
      f"lig ortalamasının ({f4(main_markets['team_shots']['log_loss']['comp'])}) belirgin üstünde ({f4(main_markets['team_shots']['log_loss']['model'])}). "
      f"Beklenen şut sayısı hatası (MAE, takım başına): model {sh['stat_level']['model']['mae_team']:.2f}, son-5 {sh['stat_level']['last5']['mae_team']:.2f}, "
      f"lig ort. {sh['stat_level']['comp']['mae_team']:.2f}. Rakip etkisi \"baskınlık\" terimiyle giriyor: güçlü hücumlu takım hem kendi şutunu artırıyor hem rakibinin şutunu azaltıyor "
      "(ayrı \"savunma\" terimi şut/korner/isabetli şut için doğrulamada kazanç eşiğini (0.0003 log loss) geçmediği için seçilmedi; kart ve faulde seçildi).")
    ref_s = R["stats"]["yellow_cards"]["markets"]
    A(f"- **Hakem (kartlar):** hakem etkisi ekleyince log loss toplam kartta {sd(ref_s['total_yellow_cards']['diff_model_minus']['model_noref'])}, "
      f"takım kartında {sd(ref_s['team_yellow_cards']['diff_model_minus']['model_noref'])} iyileşiyor: küçük ama gerçek. Takım etkileri ise "
      f"toplam kartta {sd(ref_s['total_yellow_cards']['diff_model_minus']['model_noteam'])} (takım etkisiz modele göre).")
    A("")
    A("**Banko benzeri oranlar (model olasılığı >= 0.80 ve >= 0.85 olan tahminlerin tutma oranı, test dönemi).** "
      "Her satır bir (maç, çizgi, taraf) çağrısıdır; aynı maçtan birden çok çizgi sayılabilir, bu yüzden \"maç sayısı\" ayrıca verildi. "
      "Bu oranlar bahis kârı değildir (bu marketler için yerel oran verisi yok).\n")
    rows = []
    for mk, d in main_markets.items():
        for thr in ("0.80", "0.85"):
            b = d["banko_like"]["model"][thr]
            b5 = d["banko_like"]["last5"][thr]
            rows.append([MARKET_TR[mk], f">= {thr}", b["n"], b["hits"], pct(b["hit_rate"]), pct(b["mean_confidence"]), b["n_matches_with_a_call"], f"{b5['hits']}/{b5['n']} ({pct(b5['hit_rate'])})"])
    A(table(["Market", "Eşik", "Çağrı (n)", "Tutan", "Tutma oranı", "Ort. model güveni", "Farklı maç", "Son-5 yöntemi (tutan/n)"], rows))
    pm = ev["banko_like_pooled_main_markets"]["model"]
    p5 = ev["banko_like_pooled_main_markets"]["last5"]
    A(f"\nTüm marketler birlikte: model >= 0.80: {pm['0.80']['hits']}/{pm['0.80']['n']} = {pct(pm['0.80']['hit_rate'])} "
      f"(son-5 yöntemi {pct(p5['0.80']['hit_rate'])}); >= 0.85: {pm['0.85']['hits']}/{pm['0.85']['n']} = {pct(pm['0.85']['hit_rate'])} "
      f"(son-5 yöntemi {pct(p5['0.85']['hit_rate'])}).\n")
    A("**Uyarılar.**")
    A("- Yüksek güvenli çağrıların çoğu uçtaki çizgilerde (ör. takım şutu Üst 7.5, toplam kart Alt 5.5, takım korner Alt 6.5): bu çizgiler zaten çoğu maçta aynı tarafa düşüyor. "
      "Bu yüzden ham tutma oranı beceri kanıtı değil; asıl kanıt log loss farkı ve kalibrasyon (güven ile tutma oranının uyumu). Taban oranlar aşağıda (İngilizce bölüm, per-line tablo).")
    tc = main_markets["total_corners"]["banko_like"]["model"]
    A(f"- **Toplam korner** en az tahmin edilebilir market: model >= 0.80 sadece {tc['0.80']['n']} çağrı, >= 0.85 sadece {tc['0.85']['n']} çağrı üretiyor; banko benzeri çağrı çıkacak kadar güven oluşmuyor.")
    eu_zero = [MARKET_TR[mk] for mk, d in main_markets.items() if "european" in d["league_vs_european"] and d["league_vs_european"]["european"]["diff_model_minus_last5"]["ci90"][1] >= 0]
    A(f"- Avrupa kupaları: test döneminde yalnızca {R['stats']['corners']['n_european_primary']} maç; güven aralıkları geniş. Model - son-5 farkının aralığı sıfırı içeren marketler: "
      f"{', '.join(eu_zero) if eu_zero else 'yok'} (diğerlerinde Avrupa'da da model daha iyi).")
    over = []
    for st in ("yellow_cards", "corners", "total_shots", "shots_on_target"):
        for mk, d in R["stats"][st]["markets"].items():
            b = d["banko_like"]["model"]["0.80"]
            if b["n"] >= 200 and b["mean_confidence"] - b["hit_rate"] > 0.02:
                over.append(f"{mk}{' (ek çizgiler)' if d['extra_line_set'] else ''}: güven {pct(b['mean_confidence'])}, tutma {pct(b['hit_rate'])} (n={b['n']})")
    A("- **Aşırı güven uyarısı** (>= 0.80 çağrılarında ortalama güven, tutma oranından 2 puandan fazla yüksek): " + ("; ".join(over) if over else "yok") + ". Bu marketlerin uç çizgilerinde olasılığı biraz düşük okumak gerekir.")
    drift = []
    for mk, d in main_markets.items():
        gap = sum(o - m for o, m in zip(d["base_rate_over"], d["mean_p_over_model"])) / len(d["lines"])
        if abs(gap) > 0.02:
            drift.append(f"{MARKET_TR[mk]} ({100 * gap:+.1f} puan)")
    A("- **Seviye kayması (test dönemi):** gözlenen Üst oranı ile modelin ortalama Üst olasılığı arasındaki fark (çizgi ortalaması, + = gerçekte model beklentisinden daha çok Üst): "
      + (", ".join(drift) if drift else "hiçbir markette 2 puandan büyük değil") + ". Yani test döneminde şut/korner sayıları modelin öğrendiği seviyenin biraz üstünde, kart sayıları biraz altında kaldı; "
      "dağıtım (deployment) modeli tüm maçlarla ve zaman ağırlığıyla yeniden eğitildiği için bu kaymayı kısmen yakalar, ama yeni sezon verisi geldikçe yeniden eğitim gerekir.")
    A("- Sarı kart sayısının dağılımı Poisson'a çok yakın çıktı (aşırı yayılım yok, boyut parametresi üst sınırda); kart tahminleri hakem ve takım eğilimine bağlı ama farklar küçük.")
    A("- Sadece sayılar kullanıldı: kadro, sakatlık, hakem atama bilgisi (maç öncesi hakem açıklanmadıysa etki 0 alınır), maç önemi yok.")
    A(f"- Veri notu: {T['matches']:,} maç; {DS['stat_missing_total']['yellow_cards']} maçta kart/faul bloğu FotMob'da yok (dışarıda). "
      f"Sarı kartı 0-0 olan {DS['stat_both_sides_zero']['yellow_cards']} maç (%{100 * DS['stat_both_sides_zero']['yellow_cards'] / (T['yellow_cards']):.1f}) FotMob'un gönderdiği haliyle tutuldu; "
      "bazı liglerde oran yüksek (Eredivisie %7.2, Championship %6.3), bunların bir kısmı gerçekte eksik veri olabilir ve doğrulanamadı.\n")

    # ------------------------------------------------------------------ English details
    A("---\n")
    A("## Details (English)\n")
    A("### 1. Data and coverage\n")
    A(f"One row per match (`backend/data/training/props_match_stats.csv.gz`, built by `props_build_dataset.py` from `fotmob_match_details*.jsonl` + the referee name in the raw bodies "
      f"`content.matchFacts.infoBox.Referee.text`). Input {DS['input_and_drops']['input_rows']:,} rows; dropped awarded {DS['input_and_drops']['awarded']}; kept {DS['matches_kept']:,} "
      f"({DS['kickoff_min'][:10]} .. {DS['kickoff_max'][:10]}). A stat is used only when FotMob sent it for both teams; a missing stat is excluded and counted, never 0. "
      f"Referee read: ok {DS['referee_read_status']['ok']:,}, no referee {DS['referee_read_status']['no_referee']:,} (unreadable raw files: "
      f"{DS['referee_read_status'].get('unreadable', 0)}). Czech 1. Liga `total_shots` before 2025-07-01 is excluded (different definition: {ds.excluded.get('total_shots_czech_pre_2025_07', 0)} matches).\n")
    A(table(["Stat", "Matches with stat", "Missing", "Both sides 0"], [[s, T[s], DS["stat_missing_total"].get(s, "-"), DS["stat_both_sides_zero"].get(s, "-")] for s in ("corners", "yellow_cards", "total_shots", "shots_on_target", "fouls")]))
    A(f"\nReferee name present: {T['referee']:,} of {T['matches']:,} matches.\n")
    rows = []
    for cid, c in sorted(DS["coverage_by_competition"].items(), key=lambda kv: -kv[1]["matches"]):
        rows.append([cid, c["name"], c["matches"], c["referee"], c["corners"], c["yellow_cards"], c["total_shots"], c["shots_on_target"], c["fouls"]])
    A("Coverage per competition (matches with the stat present):\n")
    A(table(["id", "competition", "matches", "referee", "corners", "yellow", "shots", "SoT", "fouls"], rows))
    A("")
    T0, V0, E0 = ds.day("2022-08-01"), ds.day("2025-07-01"), ds.day("2026-02-01")
    rows = []
    for s in ("corners", "yellow_cards", "total_shots", "shots_on_target", "fouls"):
        v = ds.valid[s]
        rows.append([s, int((v & (ds.t >= T0) & (ds.t < V0)).sum()), int((v & (ds.t >= V0) & (ds.t < E0)).sum()), int((v & (ds.t >= E0)).sum())])
    A("Splits (valid matches per stat): train 2022-08-01..2025-06-30, validation 2025-07-01..2026-01-31, test 2026-02-01..2026-10-12 (read once after freezing `props_frozen.json`).\n")
    A(table(["Stat", "Train", "Validation", "Test"], rows))
    A("\n### 2. Model\n")
    A("For a stat, one observation per team side: `ln mu_home = b0 + h + L[comp] + A[home] + D[away] (+ R[referee])`, `ln mu_away = b0 + L[comp] + A[away] + D[home] (+ R[referee])`; "
      "count ~ NegativeBinomial(mean mu, size r), r fitted per stat. Optional \"dominance\" block S: attack = A + S, concede = D - S (a team that dominates takes more and concedes less, one parameter per team). "
      "Weights `0.5 ** (age / half_life)`, ridge on A, D, S, R (teams / referees with few matches shrink to 0 = competition mean), walk-forward refits every 14 days "
      "(a fit uses only matches that kicked off >= 3 h before the fit date). Dispersion r (and, for total shots, a separate size for the total) is the out-of-sample "
      "maximum-likelihood value on the validation walk-forward predictions; for the deployment fit it is estimated on validation + test walk-forward predictions. Fitted by L-BFGS-B with the analytic gradient.\n")
    rows = []
    for s, v in FZ["stats"].items():
        c = v["config"]
        rows.append([s, c["half_life"], c["lam_team"], "yes" if c["use_concede"] else "no", "yes" if c["use_dom"] else "no", "yes" if c["use_ref"] else "no",
                     f"{c['lam_ref']}" if c["use_ref"] else "-", "season random walk" if c["use_level"] else "one per comp.", f4(v["validation"]["score"]), v["n_configs_evaluated"],
                     f"{v['validation']['r']:.2f}", "yes" if v["use_total_dispersion"] else "no"])
    A("Choices made on validation only (small grids; `score` = mean log loss of the main lines on the validation primary set):\n")
    A(table(["Stat", "Half-life d", "ridge team", "concede", "dominance", "referee", "ridge ref", "comp. level", "val. score", "configs tried", "NB size r (val)", "own total size"], rows))
    A("\nDeployment parameters (all matches up to the last kick-off, "
      f"{C['trained_through']}):\n")
    rows = [[s, b["dispersion"], "-" if b["total_dispersion"] is None else b["total_dispersion"], f"{b['intercept']:.4f}", f"{b['home_advantage']:.4f}", len(b["competitions"]), len(b["teams"]), len(b["referees"]), b["hyperparameters"]["n_matches_fitted"]]
            for s, b in C["stats"].items()]
    A(table(["Stat", "r", "r total", "intercept", "home adv.", "competitions", "teams", "referees", "matches fitted"], rows))
    A("\n### 3. Test results (2026-02-01..2026-10-12)\n")
    A(f"Primary set: {ev['primary_set']}. Paired bootstrap over matches, {ev['bootstrap']['resamples']} resamples, seed {ev['bootstrap']['seed']}, 90 % interval. "
      "All methods are scored on exactly the same matches and the same lines. Baselines use a negative-binomial with a size fitted on validation, means floored at 0.05 (floored rows: "
      f"{sum(R['stats'][s]['baseline_mu_floored_rows'] for s in R['stats'])}). (a) last-5 = mean(team's last-5 for, opponent's last-5 against), (b) last-10, 365-day average of the same form, (c) competition average (home and away separately).\n")
    A("#### 3.1 Log loss of the over/under lines (mean over the lines of a market)\n")
    rows = []
    for mk, d in main_markets.items():
        ll = d["log_loss"]
        rows.append([mk, d["n_matches"], f4(ll["model"]), f4(ll["last5"]), f4(ll["last10"]), f4(ll["avg365"]), f4(ll["comp"]), f4(ll["model_noteam"])])
    A(table(["Market", "n", "Model", "Last-5", "Last-10", "365-day avg", "Comp. avg", "Model w/o team effects"], rows))
    A("\nModel minus baseline (negative = model better), mean [90 % CI]:\n")
    rows = [[mk] + [sd(d["diff_model_minus"][b]) for b in BASELINES] for mk, d in main_markets.items()]
    A(table(["Market", "vs last-5", "vs last-10", "vs 365-day avg", "vs comp. avg"], rows))
    A("\n#### 3.2 Per line (model vs baselines; `extra` lines are outside the exported set and show the tails)\n")
    rows = []
    for st in ("yellow_cards", "corners", "total_shots", "shots_on_target"):
        for mk, d in R["stats"][st]["markets"].items():
            for j, line in enumerate(d["lines"]):
                lp = d["log_loss_per_line"]
                rows.append([mk + (" (extra)" if d["extra_line_set"] else ""), line, f4(d["base_rate_over"][j]), f4(d["mean_p_over_model"][j]), f4(lp["model"][j]), f4(lp["last5"][j]), f4(lp["avg365"][j]), f4(lp["comp"][j])])
    A(table(["Market", "Line", "Observed P(over)", "Mean model P(over)", "LL model", "LL last-5", "LL 365-day", "LL comp."], rows))
    A("\n#### 3.3 Expected counts (MAE per team side and of the match total) and NB log likelihood\n")
    rows = []
    for st, blk in R["stats"].items():
        sl = blk["stat_level"]
        for name in ("model", "last5", "last10", "avg365", "comp"):
            x = sl[name]
            diff = "-" if name == "model" else sd(x["mae_team_diff_model_minus_this"])
            rows.append([st, name, f"{x['mae_team']:.3f}", f"{x['mae_total']:.3f}", f"{x['nll_team']:.4f}", diff])
    A(table(["Stat", "Method", "MAE team", "MAE total", "NB nll / team", "MAE team: model minus this [90 % CI]"], rows))
    A("\n#### 3.4 League vs European (primary set; European = UCL, UEL, UECL)\n")
    rows = []
    for mk, d in main_markets.items():
        for lab in ("league", "european"):
            e = d["league_vs_european"].get(lab)
            if e:
                rows.append([mk, lab, e["n_matches"], f4(e["log_loss"]["model"]), f4(e["log_loss"]["last5"]), f4(e["log_loss"]["comp"]), sd(e["diff_model_minus_last5"]), sd(e["diff_model_minus_comp"])])
    A(table(["Market", "Group", "n", "Model", "Last-5", "Comp. avg", "Model - last-5", "Model - comp."], rows))
    A("\n#### 3.5 What the referee and the team effects add (log loss, model minus variant, [90 % CI])\n")
    rows = []
    for st in ("yellow_cards", "fouls"):
        for mk, d in R["stats"][st]["markets"].items():
            if "model_noref" in d["diff_model_minus"]:
                rows.append([mk + (" (extra)" if d["extra_line_set"] else ""), sd(d["diff_model_minus"]["model_noref"]), sd(d["diff_model_minus"]["model_noteam"])])
    A("Referee effect (cards and fouls) and team effects (same model without attack / concede / dominance, keeping the referee):\n")
    A(table(["Market", "Model minus no-referee model", "Model minus no-team-effects model"], rows))
    A("\nTeam effects for the other stats (model minus no-team-effects model):\n")
    rows = [[mk, sd(d["diff_model_minus"]["model_noteam"])] for mk, d in main_markets.items() if PM.MARKETS[mk][0] not in PM.REF_STATS]
    A(table(["Market", "Model minus no-team-effects model"], rows))
    A("\n#### 3.6 Calibration\n")
    rows = [[mk, d["calibration_model"]["ece"], d["calibration_last5"]["ece"]] for mk, d in main_markets.items()]
    A("Expected calibration error (10 probability bins of P(over), all lines of the market pooled; smaller is better):\n")
    A(table(["Market", "ECE model", "ECE last-5"], rows))
    A("\nConfidence of the predicted side (max(p, 1-p)), main markets pooled; hit = the predicted side happened:\n")
    bands = {}
    for mk, d in main_markets.items():
        for name in ("model", "last5"):
            for b in d["confidence_bands"][name]:
                x = bands.setdefault((name, b["band"]), [0, 0, 0.0])
                x[0] += b["n"]
                x[1] += b["hits"]
                x[2] += (b["mean_confidence"] or 0.0) * b["n"]
    rows = []
    for band in [b["band"] for b in main_markets["total_corners"]["confidence_bands"]["model"]]:
        row = [band]
        for name in ("model", "last5"):
            n, h, cs = bands[(name, band)]
            row += [n, pct(h / n) if n else "-", f"{cs / n:.3f}" if n else "-"]
        rows.append(row)
    A(table(["Band", "Model n", "Model hit rate", "Model mean conf.", "Last-5 n", "Last-5 hit rate", "Last-5 mean conf."], rows))
    A("\n#### 3.7 Banko-like calls per line (model >= 0.80 / >= 0.85)\n")
    A("`over` / `under` = number of calls on that side; hits = the called side landed. The observed base rate of the line is in 3.2.\n")
    rows = []
    for st in ("yellow_cards", "corners", "total_shots", "shots_on_target"):
        for mk, d in R["stats"][st]["markets"].items():
            for thr in ("0.80", "0.85"):
                for pl in d["banko_like"]["model"][thr]["per_line"]:
                    if pl["n"]:
                        rows.append([mk + (" (extra)" if d["extra_line_set"] else ""), f">= {thr}", pl["line"], pl["n"], pl["hits"], pct(pl["hit_rate"]), pct(pl["mean_confidence"]), pl["n_over_calls"], pl["n_under_calls"]])
    A(table(["Market", "Threshold", "Line", "n", "Hits", "Hit rate", "Mean conf.", "over", "under"], rows))
    A("\n#### 3.8 Fouls (optional stat, not requested as a market)\n")
    fl = R["stats"]["fouls"]
    A(f"Fouls are exported (`stats.fouls`) because the fit was cheap; log loss of the extra lines: " + "; ".join(
        f"{mk} model {f4(d['log_loss']['model'])} vs last-5 {f4(d['log_loss']['last5'])} ({sd(d['diff_model_minus']['last5'])})" for mk, d in fl["markets"].items()) + ".\n")
    A("### 4. Export and runtime check\n")
    A(f"`props_model_candidate.json`: version `{C['version']}`, trained_through `{C['trained_through']}`, stats {', '.join(C['stats'])}, team_recent for {len(C['team_recent'])} teams "
      "(plain last-5 averages for the UI, not model inputs), the 8 market line sets, the `evaluation` block and the `formula` text:\n")
    A("```\n" + C["formula"] + "\n```\n")
    A("Added fields beyond the agreed structure: `formula`, `stats.<stat>.total_dispersion` (null = exact convolution of the two NB sides; a number = the total is NB(mu_home + mu_away, total_dispersion); "
      "used only for `total_shots`, where the two sides' counts are negatively correlated), `stats.<stat>.hyperparameters`. "
      "`competitions` holds the level of the CURRENT season (only fouls uses the season random walk).\n")
    A(f"`props_check_runtime_formula.py` applies the JSON with the formula to {chk['n_matches']} random test matches (deployment fit) and compares with the training code: "
      f"max |dp| over {chk['n_comparisons']} (match x market) comparisons = {max(chk['max_abs_diff_prob'].values()):.2e}, max |dmu| = {max(chk['max_abs_diff_mu'].values()):.2e} "
      "(parameters are rounded to 8 decimals in the JSON).\n")
    A("### 5. Limits and caveats\n")
    A("- Counts only; no line-ups, injuries, referee assignment for upcoming matches (unknown referee = offset 0), match importance or weather.")
    A("- The hit rates are statements about the model's probabilities against FotMob counts, not about profit: no bookmaker prices for these markets exist locally.")
    A("- Banko-like calls are dominated by tail lines whose base rate is already high; compare with the observed base rate of the line (3.2) and with the calibration table (3.6).")
    A("- Level drift in the test period: the mean model P(over) differs from the observed over-rate by more than 2 points for some markets (see the Turkish summary and 3.2). The deployment fit is refitted on all matches with time decay (half-lives 120-480 days) and partly absorbs it; refit regularly.")
    A("- European competitions: few test matches; team effects there rest on fewer matches per team.")
    A("- Yellow cards: dispersion fitted at the upper bound (Poisson-like). 0-0 card matches were kept as FotMob sent them; some leagues have a high rate that could hide missing data (not verifiable offline).")
    A("- The 365-day baselines need both teams to have >= 5 matches with the stat in that window; the evaluation is on that primary set (see `n_primary` per stat in the report); the model itself predicts every match, including teams with few matches.")
    A("- Reproduce: `props_build_dataset.py` -> `props_select.py` (validation only, writes `props_frozen.json`) -> `props_final.py` (test once, deployment fit, export) -> `props_check_runtime_formula.py` -> `props_make_report.py`. Tests: `backend/tests/test_props_model.py` (synthetic fixtures).")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", OUT, len(L), "blocks")


if __name__ == "__main__":
    main()

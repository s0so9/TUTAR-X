"""Score frozen pre-match predictions against final results.

Sources: model snapshots (v0..v5), the market (user-supplied odds, margin removed),
Claude's subjective estimates and the user's picks (human_predictions.json, all
recorded before kickoff).

Usage: python compare_results.py            -> uses final scores from the local API
       python compare_results.py --preview  -> no results needed; side-by-side probabilities
Outputs a Markdown report on stdout.
"""
import json
import math
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
LIST_API = "http://127.0.0.1:8003/api/v1/matches?from_date=2026-10-13&to_date=2026-10-14&competition_id=42&limit=100"
VERSIONS = [("v0 (eski motor)", "snapshots_v0"), ("v1 (reyting)", "snapshots_v1"),
            ("v2 (reyting+kadro)", "snapshots_v2"), ("v3", "snapshots_v3"), ("v4 (eğitimli)", "snapshots_v4"),
            ("v5 (resmi kadro)", "snapshots_v5")]
MARKET = "Piyasa (kullanıcı oranları)"
CLAUDE = "Claude (kişisel yorum)"
preview = "--preview" in sys.argv

market = {m["match_id"]: m for m in json.loads((HERE / "market_odds.json").read_text(encoding="utf-8"))["matches"]}
fixtures = json.loads((HERE / "cl_tonight.json").read_text(encoding="utf-8"))
human = json.loads((HERE / "human_predictions.json").read_text(encoding="utf-8"))

results = {}
if not preview:
    with urllib.request.urlopen(LIST_API, timeout=120) as r:
        results = {m["id"]: m for m in json.loads(r.read().decode("utf-8"))["matches"]}


def fair(*odds):
    inv = [1 / o for o in odds]
    s = sum(inv)
    return [x / s for x in inv]


def over(resp, line):
    for m in resp.get("market_analysis") or []:
        if m.get("market_type") == f"OVER_UNDER_{line}":
            for o in m["outcomes"]:
                if o["label"].lower().startswith("over"):
                    return o.get("calibrated_probability") or o.get("model_probability")
    return None


def load(dirname, mid):
    f = HERE / dirname / f"{mid}.json"
    if not f.exists():
        return None
    s = json.loads(f.read_text(encoding="utf-8"))
    return s["response"] if s["http_status"] == 200 else None


def pct(x):
    return "veri yok" if x is None else f"{x:.0%}"


def probs_for(mid):
    """name -> (1X2 list, over2.5, over3.5, btts) or None."""
    out = {}
    for name, d in VERSIONS:
        r = load(d, mid)
        out[name] = None if r is None else (
            [r["home_win_probability"], r["draw_probability"], r["away_win_probability"]],
            over(r, "2_5"), over(r, "3_5"), r.get("btts_probability"))
    mk = market[mid]
    out[MARKET] = (fair(mk["odds_1"], mk["odds_x"], mk["odds_2"]), fair(mk["over_2_5"], mk["under_2_5"])[0],
                   human["market_over_3_5_fair"].get(mid), fair(mk["btts_yes"], mk["btts_no"])[0])
    c = human["claude_estimates"].get(mid)
    out[CLAUDE] = None if c is None else ([c["home"], c["draw"], c["away"]], c["over_2_5"], c["over_3_5"], c["btts_yes"])
    return out


names = [v[0] for v in VERSIONS] + [MARKET, CLAUDE]
metrics = {n: {"n": 0, "ll": 0.0, "br": 0.0, "hit": 0, "o25": [0, 0.0], "o35": [0, 0.0], "kg": [0, 0.0]} for n in names}
last = VERSIONS[-1][0]

print("## 1X2 (Ev / Beraberlik / Deplasman)\n")
print("| Maç | Sonuç | " + " | ".join(names) + " |")
print("|---|---|" + "---|" * len(names))
goal_rows = []
for fx in fixtures:
    mid = fx["id"]
    probs = probs_for(mid)
    res = results.get(mid)
    score = "—"
    if res and res.get("status") == "FINISHED":
        h, a = res["home_score"], res["away_score"]
        score = f"{h}-{a}"
        k = 0 if h > a else (1 if h == a else 2)
        for name, p in probs.items():
            if p is None:
                continue
            m = metrics[name]
            m["n"] += 1
            m["ll"] += -math.log(max(p[0][k], 1e-12))
            m["br"] += sum((p[0][i] - (i == k)) ** 2 for i in range(3))
            m["hit"] += int(max(range(3), key=lambda i: p[0][i]) == k)
            for key, val, outcome in (("o25", p[1], h + a > 2.5), ("o35", p[2], h + a > 3.5), ("kg", p[3], h > 0 and a > 0)):
                if val is not None:
                    m[key][0] += 1
                    m[key][1] += (val - outcome) ** 2
    label = f"{fx['home_team']['name']} - {fx['away_team']['name']}"
    cells = ["veri yok" if probs[n] is None else "/".join(f"{x:.0%}" for x in probs[n][0]) for n in names]
    print(f"| {label} | {score} | " + " | ".join(cells) + " |")
    latest = next((n for n, _ in reversed(VERSIONS) if probs[n] is not None), last)
    v, mk, c = probs[latest], probs[MARKET], probs[CLAUDE]
    goal_rows.append(
        f"| {label} | {score} | {pct(v and v[1])} / {pct(mk[1])} / {pct(c and c[1])} | "
        f"{pct(v and v[2])} / {pct(mk[2])} / {pct(c and c[2])} | {pct(v and v[3])} / {pct(mk[3])} / {pct(c and c[3])} |")

print("\n## Gol pazarları (son model sürümü / piyasa / Claude)\n")
print("| Maç | Sonuç | 2.5 Üst | 3.5 Üst | KG Var |")
print("|---|---|---|---|---|")
print("\n".join(goal_rows))

if any(m["n"] for m in metrics.values()):
    print("\n## Puanlama (düşük daha iyi)\n")
    print("| Kaynak | Maç | 1X2 isabet | 1X2 log loss | 1X2 Brier | 2.5 Üst Brier | 3.5 Üst Brier | KG Brier |")
    print("|---|---|---|---|---|---|---|---|")
    for name, m in metrics.items():
        if not m["n"]:
            continue
        b = lambda key: f"{m[key][1] / m[key][0]:.3f}" if m[key][0] else "veri yok"
        print(f"| {name} | {m['n']} | {m['hit']}/{m['n']} | {m['ll'] / m['n']:.3f} | {m['br'] / m['n']:.3f} "
              f"| {b('o25')} | {b('o35')} | {b('kg')} |")

    print("\n## Kullanıcının seçimleri\n")
    for mid, pick in human["user_picks"].items():
        res = results.get(mid)
        if not res or res.get("status") != "FINISHED":
            print(f"- {pick['label']}: maç bitmedi")
            continue
        h, a = res["home_score"], res["away_score"]
        actual = "HOME_WIN" if h > a else ("DRAW" if h == a else "AWAY_WIN")
        print(f"- {pick['label']}: {h}-{a} → {'TUTTU' if actual == pick['pick'] else 'TUTMADI'}")

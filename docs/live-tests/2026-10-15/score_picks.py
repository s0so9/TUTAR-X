"""Score the pre-match picks of 2026-10-15 (system vs Claude) against final results.

Scope: Europa League (FotMob competition id 73) and Conference League (10216).

Usage (from this folder): ../../../backend/venv/Scripts/python.exe -I score_picks.py
Reads system_picks.json and claude_picks.json (both recorded before kick-off),
fetches final scores from the local API (one list call per competition, because the
list endpoint takes a single competition_id) and prints a Markdown table, the totals
and the hit rate per Banko tier. Unplayed / unfinished matches are listed as "bitmedi"
and left out of the totals; a "yok" pick (null) is never counted.
"""
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
COMPETITIONS = {"73": "Europa League", "10216": "Conference League"}
LIST = "http://127.0.0.1:8003/api/v1/matches?from_date=2026-10-15&to_date=2026-10-16&competition_id={cid}&limit=200"
TIERS = ("Çok güçlü", "Banko", "Güçlü")

LABELS = {
    "HOME_WIN": "MS 1", "DRAW": "MS X", "AWAY_WIN": "MS 2",
    "HOME_OR_DRAW": "1X", "HOME_OR_AWAY": "12", "DRAW_OR_AWAY": "X2",
    "BTTS_YES": "KG Var", "BTTS_NO": "KG Yok",
}


def label(key) -> str:
    if not key:
        return "yok"
    if key in LABELS:
        return LABELS[key]
    side, a, b = key.split("_")
    return f"{a}.{b} {'Üst' if side == 'OVER' else 'Alt'}"


def landed(key: str, h: int, a: int) -> bool:
    if key == "HOME_WIN":
        return h > a
    if key == "DRAW":
        return h == a
    if key == "AWAY_WIN":
        return h < a
    if key == "HOME_OR_DRAW":
        return h >= a
    if key == "DRAW_OR_AWAY":
        return h <= a
    if key == "HOME_OR_AWAY":
        return h != a
    if key == "BTTS_YES":
        return h > 0 and a > 0
    if key == "BTTS_NO":
        return h == 0 or a == 0
    side, x, y = key.split("_")
    line = float(f"{x}.{y}")
    return (h + a > line) if side == "OVER" else (h + a < line)


def fetch_results() -> dict:
    results = {}
    for cid in COMPETITIONS:
        try:
            with urllib.request.urlopen(LIST.format(cid=cid), timeout=120) as r:
                for m in json.loads(r.read().decode("utf-8"))["matches"]:
                    results[m["id"]] = m
        except Exception as exc:  # keep going: the other competition may still score
            print(f"(uyarı: {COMPETITIONS[cid]} listesi alınamadı: {exc})")
    return results


def rate(w: int, n: int) -> str:
    return f"{w}/{n} (%{100 * w / n:.0f})" if n else "0/0"


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    system = json.loads((HERE / "system_picks.json").read_text(encoding="utf-8"))["picks"]
    claude = json.loads((HERE / "claude_picks.json").read_text(encoding="utf-8"))["picks"]
    results = fetch_results()
    tally = {"Sistem banko": [0, 0], "Sistem oranlı": [0, 0], "Claude banko": [0, 0], "Claude oranlı": [0, 0]}
    tiers = {who: {t: [0, 0] for t in TIERS} for who in ("Sistem", "Claude")}
    unfinished = 0
    order = sorted(system.items(), key=lambda kv: (kv[1].get("kickoff_utc", ""), kv[1]["label"]))
    print("| Saat (UTC) | Maç | Skor | Sistem banko | Sistem oranlı | Claude banko | Claude oranlı |")
    print("|---|---|---|---|---|---|---|")
    for mid, s in order:
        c = claude.get(mid, {})
        m = results.get(mid)
        ko = s.get("kickoff_utc", "")[11:16]
        if not m or m.get("status") != "FINISHED" or m.get("home_score") is None or m.get("away_score") is None:
            unfinished += 1
            status = m.get("status") if m else "listede yok"
            print(f"| {ko} | {s['label']} | bitmedi ({status}) | {label(s.get('banko'))} | {label(s.get('oranli'))} "
                  f"| {label(c.get('banko'))} | {label(c.get('oranli'))} |")
            continue
        h, a = m["home_score"], m["away_score"]
        cells = []
        for name, key, tier_owner, tier in (
            ("Sistem banko", s.get("banko"), "Sistem", s.get("banko_tier")),
            ("Sistem oranlı", s.get("oranli"), None, None),
            ("Claude banko", c.get("banko"), "Claude", c.get("banko_tier")),
            ("Claude oranlı", c.get("oranli"), None, None),
        ):
            if not key:
                cells.append("yok")
                continue
            ok = landed(key, h, a)
            tally[name][0] += int(ok)
            tally[name][1] += 1
            if tier_owner and tier in TIERS:
                tiers[tier_owner][tier][0] += int(ok)
                tiers[tier_owner][tier][1] += 1
            cells.append(f"{label(key)} {'✅' if ok else '❌'}")
        print(f"| {ko} | {s['label']} | {h}-{a} | " + " | ".join(cells) + " |")
    print()
    print(f"Bitmemiş / sonucu olmayan maç: {unfinished}/{len(system)}")
    for name, (w, n) in tally.items():
        print(f"- {name}: {rate(w, n)}")
    print()
    print("Kademeye göre Banko isabeti (araştırma test beklentisi: Çok güçlü ~%93, Banko ~%88, Güçlü %75-85):")
    for who, by_tier in tiers.items():
        print(f"- {who}: " + ", ".join(f"{t} {rate(w, n)}" for t, (w, n) in by_tier.items()))
    banko85 = [sum(x) for x in zip(*(tiers["Sistem"][t] for t in ("Çok güçlü", "Banko")))]
    print(f"- Sistem p >= 0,85 (Çok güçlü + Banko): {rate(*banko85)}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()

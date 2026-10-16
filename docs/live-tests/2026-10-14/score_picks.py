"""Score the pre-match picks of 2026-10-14 (system vs Claude) against final results.

Usage (from this folder): ../../../backend/venv/Scripts/python.exe score_picks.py
Reads system_picks.json and claude_picks_v2.json (both recorded before kick-off),
fetches final scores from the local API and prints a Markdown table.
"""
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
LIST = "http://127.0.0.1:8003/api/v1/matches?from_date=2026-10-14&to_date=2026-10-15&competition_id=42&limit=100"

LABELS = {
    "HOME_WIN": "MS 1", "DRAW": "MS X", "AWAY_WIN": "MS 2",
    "HOME_OR_DRAW": "1X", "HOME_OR_AWAY": "12", "DRAW_OR_AWAY": "X2",
    "BTTS_YES": "KG Var", "BTTS_NO": "KG Yok",
}


def label(key: str) -> str:
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


def main() -> None:
    system = json.loads((HERE / "system_picks.json").read_text(encoding="utf-8"))["picks"]
    claude = json.loads((HERE / "claude_picks_v2.json").read_text(encoding="utf-8"))["picks"]
    with urllib.request.urlopen(LIST, timeout=120) as r:
        results = {m["id"]: m for m in json.loads(r.read().decode("utf-8"))["matches"]}
    tally = {"Sistem banko": [0, 0], "Sistem oranlı": [0, 0], "Claude banko": [0, 0], "Claude oranlı": [0, 0]}
    print("| Maç | Skor | Sistem banko | Sistem oranlı | Claude banko | Claude oranlı |")
    print("|---|---|---|---|---|---|")
    for mid, s in system.items():
        c = claude.get(mid, {})
        m = results.get(mid)
        if not m or m.get("status") != "FINISHED":
            print(f"| {s['label']} | bitmedi | {label(s['banko'])} | {label(s['oranli'])} | {label(c['banko'])} | {label(c['oranli'])} |")
            continue
        h, a = m["home_score"], m["away_score"]
        cells = []
        for name, key in (("Sistem banko", s["banko"]), ("Sistem oranlı", s["oranli"]), ("Claude banko", c["banko"]), ("Claude oranlı", c["oranli"])):
            ok = landed(key, h, a)
            tally[name][0] += int(ok)
            tally[name][1] += 1
            cells.append(f"{label(key)} {'✅' if ok else '❌'}")
        print(f"| {s['label']} | {h}-{a} | " + " | ".join(cells) + " |")
    print()
    for name, (w, n) in tally.items():
        print(f"- {name}: {w}/{n}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()

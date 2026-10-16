"""Research (2026-10-15, "additional data" study): if the app ingests bookmaker odds, how should the margin be removed?

Compares de-vig methods on football-data.co.uk PRE-closing 1X2 odds (Pinnacle PSH/PSD/PSA when complete, else
market average AvgH/AvgD/AvgA), league matches mapped to FotMob ids (same acceptance rules as
calibration_common.load_closing_odds: score agrees, not awarded):
  proportional  p_i = (1/o_i) / sum_j (1/o_j)
  power         p_i = (1/o_i)^k with k solved so that sum p_i = 1
  shin          Shin (1993) insider model, iterative solution as in Strumbelj (2014, IJF 30(4) 934-943)
Scored by 1X2 log loss on every mapped match, on the test window (kick-off >= 2026-02-01) and per source.
No network; DB read-only for the id map.

Run (from backend/):  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/xdata_devig.py
Output: data/research/xdata_devig.json
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "scripts" / "training"))
import calibration_common as CC  # noqa: E402

OUT = BACKEND / "data" / "research" / "xdata_devig.json"


def prop(o):
    q = 1 / o
    return q / q.sum()


def power(o):
    q = 1 / o
    k = brentq(lambda k: (q ** k).sum() - 1, 0.5, 3.0)
    return q ** k


def shin(o):
    """Shin probabilities p_i(z) = (sqrt(z^2 + 4(1-z) q_i^2 / B) - z) / (2(1-z)), q_i = 1/o_i, B = sum q;
    the insider share z solves sum_i p_i(z) = 1 (Jullien & Salanie 1994; Strumbelj 2014)."""
    q = 1 / o
    B = q.sum()

    def p_of(z):
        return (np.sqrt(z * z + 4 * (1 - z) * q * q / B) - z) / (2 * (1 - z))
    if B <= 1.0:
        return q / B
    z = brentq(lambda z: p_of(z).sum() - 1, 0.0, 0.5)
    p = p_of(z)
    return p / p.sum()


def main() -> int:
    d = CC.load_baseline()
    res_by_id = {m: (int(h), int(a), k) for m, h, a, k in zip(d["match_id"], d["hg"], d["ag"], d["kickoff"])}
    con = sqlite3.connect(f"file:{(BACKEND / 'football_intelligence.db').as_posix()}?mode=ro", uri=True)
    try:
        id_map = {r[0]: str(r[1]) for r in con.execute("select id, provider_id from matches")}
    finally:
        con.close()
    rows = {}

    def take(pid, r):
        if pid in rows or pid not in res_by_id:
            return
        for cols, src in ((("PSH", "PSD", "PSA"), "pinnacle"), (("AvgH", "AvgD", "AvgA"), "average")):
            v = [CC.fnum(r.get(c)) for c in cols]
            if all(x is not None and x > 1 for x in v):
                rows[pid] = (np.array(v), src)
                return

    with open(BACKEND / "data" / "external" / "football_data_matches.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = id_map.get(r.get("db_match_id") or "")
            if pid and r.get("db_score_agrees") == "1":
                take(pid, r)
    with open(BACKEND / "data" / "external" / "football_data_history.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = r.get("fotmob_match_id") or ""
            if pid and r.get("score_agrees") == "1" and r.get("fotmob_awarded") != "1":
                take(pid, r)
    ids = sorted(rows)
    y = np.array([0 if res_by_id[m][0] > res_by_id[m][1] else (1 if res_by_id[m][0] == res_by_id[m][1] else 2)
                  for m in ids])
    test = np.array([res_by_id[m][2] >= "2026-02-01" for m in ids])
    src = np.array([rows[m][1] for m in ids])
    out = {"n": len(ids), "n_test": int(test.sum()), "by_source_n": {s: int((src == s).sum()) for s in set(src)}}
    L = {}
    for name, fn in (("proportional", prop), ("power", power), ("shin", shin)):
        P = np.array([fn(rows[m][0]) for m in ids])
        L[name] = CC.logloss(P, y)
        out[name] = {"all": round(float(L[name].mean()), 5), "test": round(float(L[name][test].mean()), 5),
                     "mean_p_draw": round(float(P[:, 1].mean()), 4)}
    out["actual_draw_rate"] = round(float((y == 1).mean()), 4)
    for name in ("power", "shin"):
        out[f"{name}_minus_proportional_all"] = CC.paired_boot(L[name] - L["proportional"])
        out[f"{name}_minus_proportional_test"] = CC.paired_boot(L[name][test] - L["proportional"][test])
    for s in set(src):
        m = src == s
        out[f"source_{s}"] = {k: round(float(L[k][m].mean()), 5) for k in L}
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

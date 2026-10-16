# Review check: how much does Shin / power de-vig move favourite probabilities (Pinnacle closing),
# and what is the remaining calibration gap in 0.7-0.9 after Shin?
import csv, sys, math
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import numpy as np
from sota_common import devig_prop, devig_shin
path = r"C:/Users/Mito/Downloads/FootballIntelligence-main/FootballIntelligence-main/backend/data/external/football_data_history.csv"
c = sys.argv[1]
rows = []
with open(path, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        try:
            o = [float(r[c+"H"]), float(r[c+"D"]), float(r[c+"A"])]
            hg, ag = int(r["FTHG"]), int(r["FTAG"])
        except (ValueError, KeyError):
            continue
        if min(o) <= 1:
            continue
        res = 0 if hg > ag else (1 if hg == ag else 2)
        rows.append((o, res))
P = np.array([devig_prop(o) for o, _ in rows]); S = np.array([devig_shin(o) for o, _ in rows])
Y = np.zeros_like(P); Y[np.arange(len(rows)), [r for _, r in rows]] = 1
print("n", len(rows))
for lo, hi in [(0.7, 0.8), (0.8, 0.9)]:
    m = (P >= lo) & (P < hi)
    print(f"band prop {lo}-{hi}: n={m.sum()} prop={P[m].mean():.4f} shin={S[m].mean():.4f} shift={S[m].mean()-P[m].mean():+.4f} obs={Y[m].mean():.4f}")
    ms = (S >= lo) & (S < hi)
    print(f"  band shin {lo}-{hi}: n={ms.sum()} shin_pred={S[ms].mean():.4f} obs={Y[ms].mean():.4f} gap={Y[ms].mean()-S[ms].mean():+.4f}")

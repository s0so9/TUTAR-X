"""Research helper for docs/research/2026-10-15-accuracy-roadmap.md.

How many tracked live picks are needed before a Banko hit rate can be told
apart from noise?  Pure binomial arithmetic, no football data is read.

- Wilson 90 % interval for an observed hit rate of 0.90 at several pick counts.
- Probability that a rule whose TRUE hit rate is 0.90 shows <= 0.85 (or that a
  rule whose true rate is 0.81, the current every-match Banko, shows >= 0.90)
  over n picks, i.e. how easily a short live run misleads.
- Wilson 90 % intervals for the scored live night of 2026-10-14
  (docs/live-tests/2026-10-14/results.md: banko 5/7, oranli 5/7, total 10/14).

Output: backend/data/research/roadmap_live_sample_size.json
Run (from backend/): OMP_NUM_THREADS=2 venv/Scripts/python.exe scripts/research/roadmap_live_sample_size.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from scipy.stats import binom, norm

OUT = Path(__file__).resolve().parents[2] / "data" / "research" / "roadmap_live_sample_size.json"
Z90 = float(norm.ppf(0.95))


def wilson(k: int, n: int, z: float = Z90) -> list[float]:
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(centre - half, 4), round(centre + half, 4)]


def main() -> None:
    sizes = [7, 14, 30, 50, 100, 200, 300, 500, 1000]
    rows = []
    for n in sizes:
        k90 = round(0.90 * n)
        # P(observed rate <= 0.85 | true 0.90): floor(0.85 n) or fewer hits
        p_low = float(binom.cdf(math.floor(0.85 * n + 1e-9), n, 0.90))
        # P(observed rate >= 0.90 | true 0.81): ceil(0.90 n) or more hits
        p_high = float(binom.sf(math.ceil(0.90 * n - 1e-9) - 1, n, 0.81))
        rows.append(
            {
                "n_picks": n,
                "observed_hits_at_0.90": k90,
                "wilson90_if_observed_0.90": wilson(k90, n),
                "p_true90_shows_le_0.85": round(p_low, 4),
                "p_true81_shows_ge_0.90": round(p_high, 4),
            }
        )
    live = {
        "banko_5_of_7": wilson(5, 7),
        "oranli_5_of_7": wilson(5, 7),
        "total_10_of_14": wilson(10, 14),
    }
    out = {
        "note": "Binomial arithmetic only (independent picks assumed). Wilson 90 % intervals.",
        "z90": round(Z90, 4),
        "by_sample_size": rows,
        "live_2026_10_14_wilson90": live,
    }
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()

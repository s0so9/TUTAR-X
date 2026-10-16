"""Research (2026-10-15): rank the weak pockets of err_pockets.json by recoverable error x frequency, with the same
number on the train period as a stability check. Reads data/research/err_pockets.json, writes err_rank.json.

excess_contrib = (pocket gap to the closing market - average gap) x pocket share of odds rows; summed over a partition
it is 0, so a positive value is gap that is specific to the pocket. ub_contrib = pocket gap x share (all of it, i.e. the
upper bound if the model were replaced by the market in that pocket).
Run (from backend/):  venv/Scripts/python.exe -I scripts/research/err_rank.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from err_common import RES, r5  # noqa: E402


def main() -> int:
    R = json.loads((RES / "err_pockets.json").read_text(encoding="utf-8"))
    ov_vt = R["overall"]["valtest"]
    ov_tr = R["overall"]["train"]
    rows = []
    for dim, pockets in R["dims"].items():
        if dim in ("half_year", "month"):
            continue
        for name, p in pockets.items():
            vt, tr = p["valtest"], p["train"]
            if vt.get("gap") is None:
                continue
            sh_vt = vt["n_mk"] / ov_vt["n_mk"]
            ex_vt = (vt["gap"] - ov_vt["gap"]) * sh_vt
            ex_tr = None
            if tr.get("gap") is not None:
                ex_tr = (tr["gap"] - ov_tr["gap"]) * tr["n_mk"] / ov_tr["n_mk"]
            rows.append({"dim": dim, "pocket": name, "n_vt": vt["n"], "n_mk_vt": vt["n_mk"], "share_mk_vt": r5(sh_vt),
                         "gap_vt": vt["gap"], "gap_vt_ci90": vt["gap_ci90"], "gap_tr": tr.get("gap"), "n_mk_tr": tr.get("n_mk"),
                         "ub_contrib_vt": r5(vt["gap"] * sh_vt), "excess_vt": r5(ex_vt), "excess_tr": r5(ex_tr),
                         "stable": bool(ex_tr is not None and ex_vt > 0 and ex_tr > 0),
                         "acc_vt": vt["acc"], "ll_vt": vt["ll"]})
    rows.sort(key=lambda r: -(r["excess_vt"] or 0))
    out = {"avg_gap_valtest": ov_vt["gap"], "avg_gap_train": ov_tr["gap"], "n_mk_valtest": ov_vt["n_mk"],
           "n_mk_train": ov_tr["n_mk"], "ranked": rows}
    (RES / "err_rank.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"avg gap valtest {ov_vt['gap']} train {ov_tr['gap']}")
    for r in rows[:25]:
        print(f"{r['dim']:12s} {r['pocket']:22s} n_mk={r['n_mk_vt']:5d} share={r['share_mk_vt']:.3f} gap_vt={r['gap_vt']:.4f} "
              f"ci={r['gap_vt_ci90']} gap_tr={r['gap_tr']} excess_vt={r['excess_vt']:.5f} excess_tr={r['excess_tr']} "
              f"stable={r['stable']} ub={r['ub_contrib_vt']:.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Research (2026-10-15): UEFA matches by stage (group / league phase vs knockout, first vs second leg, first-leg margin).

Stage from the FotMob raw infoBox round name (err_match_info.csv: '1/16', '1/8', '1/4', '1/2', 'final' = knockout;
a number = group / league phase). Second leg = the later of two knockout matches between the same pair in the same
competition within 30 days; first-leg margin taken from the first match's result (known before the second leg).
Run (from backend/):  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/err_uefa.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from err_common import RES, boot_ci, ll_rows, load_base, r5  # noqa: E402


def main() -> int:
    D = load_base(with_odds=False)
    P, y = D["P"], D["y"]
    ll = ll_rows(P, y)
    euro = np.where(D["is_euro"])[0]
    stage = {}
    for i in euro:
        rn = (D["info"][i] or {}).get("round_name", "")
        stage[i] = "group/league_phase" if rn.strip().isdigit() else ("knockout" if rn else "unknown")
    # legs
    ko = [i for i in euro if stage[i] == "knockout"]
    by_pair = {}
    for i in ko:
        key = (D["comp"][i], frozenset((D["home"][i], D["away"][i])))
        by_pair.setdefault(key, []).append(i)
    leg = {}
    margin = {}
    for key, idx in by_pair.items():
        idx = sorted(idx, key=lambda j: D["kickoff"][j])
        if len(idx) == 2 and (D["kickoff"][idx[1]] - D["kickoff"][idx[0]]).days <= 30:
            a, b = idx
            leg[a], leg[b] = "first_leg", "second_leg"
            # first-leg goal difference from the second-leg home team's perspective
            h2 = D["home"][b]
            gd1 = (D["hg"][a] - D["ag"][a]) if D["home"][a] == h2 else (D["ag"][a] - D["hg"][a])
            margin[b] = int(gd1)
        else:
            for j in idx:
                leg[j] = "single_or_final"
    rows = {}

    def summ(name, sel):
        sel = np.array(sel, dtype=int)
        if len(sel) == 0:
            return
        rows[name] = {"n": int(len(sel)), "ll": r5(ll[sel].mean()), "acc": r5((P[sel].argmax(1) == y[sel]).mean()),
                      "pred": [r5(v) for v in P[sel].mean(0)], "obs": [r5((y[sel] == k).mean()) for k in range(3)]}

    for sp in ("all", "train", "valtest"):
        def keep(i):
            return sp == "all" or (sp == "train" and D["split"][i] == "train") or (
                sp == "valtest" and D["split"][i] in ("validation", "test"))
        summ(f"{sp}|group/league_phase", [i for i in euro if stage[i] == "group/league_phase" and keep(i)])
        summ(f"{sp}|knockout", [i for i in euro if stage[i] == "knockout" and keep(i)])
        summ(f"{sp}|ko_first_leg", [i for i in ko if leg.get(i) == "first_leg" and keep(i)])
        summ(f"{sp}|ko_second_leg", [i for i in ko if leg.get(i) == "second_leg" and keep(i)])
        summ(f"{sp}|ko_2nd_leg_home_led_by_2+", [i for i in ko if leg.get(i) == "second_leg" and margin[i] >= 2 and keep(i)])
        summ(f"{sp}|ko_2nd_leg_level_or_1", [i for i in ko if leg.get(i) == "second_leg" and abs(margin[i]) <= 1 and keep(i)])
        summ(f"{sp}|ko_2nd_leg_home_trailed_by_2+", [i for i in ko if leg.get(i) == "second_leg" and margin[i] <= -2 and keep(i)])
    out = RES / "err_uefa.json"
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    for k, v in rows.items():
        print(k, json.dumps(v))
    return 0


def recal_by_stage() -> dict:
    """UEFA group / league-phase rows: 3-parameter recalibration (err_pockets.recal_fit) and a draw-only intercept,
    fitted on TRAIN group-phase rows, scored on validation and test group-phase rows (and knockout rows for contrast)."""
    from err_pockets import recal_apply, recal_fit
    from scipy.optimize import minimize_scalar
    D = load_base(with_odds=False)
    P, y = D["P"], D["y"]
    ll = ll_rows(P, y)
    st = np.array(["" if not D["is_euro"][i] else ("group" if (D["info"][i] or {}).get("round_name", "").strip().isdigit()
                                                     else "ko") for i in range(D["n"])])
    sp = D["split"]
    trg = (st == "group") & (sp == "train")
    th = recal_fit(P[trg], y[trg])

    def dshift(Pm, d):
        Q = Pm.copy()
        Q[:, 1] *= np.exp(d)
        return Q / Q.sum(1, keepdims=True)
    dd = float(minimize_scalar(lambda d: ll_rows(dshift(P[trg], d), y[trg]).mean(), bounds=(-0.6, 0.6),
                               method="bounded").x)
    out = {"theta_train_group": [r5(t) for t in th], "draw_shift_train_group": r5(dd), "n_train_group": int(trg.sum())}
    for s in ("validation", "test"):
        for stg in ("group", "ko"):
            m = (st == stg) & (sp == s)
            if m.sum() == 0:
                continue
            d1 = ll_rows(recal_apply(P[m], th), y[m]) - ll[m]
            d2 = ll_rows(dshift(P[m], dd), y[m]) - ll[m]
            out[f"{s}|{stg}"] = {"n": int(m.sum()), "recal_diff": r5(d1.mean()), "recal_ci90": [r5(v) for v in boot_ci(d1)],
                                 "draw_only_diff": r5(d2.mean()), "draw_only_ci90": [r5(v) for v in boot_ci(d2)]}
    (RES / "err_uefa_recal.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out))
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--recal":
        recal_by_stage()
    else:
        sys.exit(main())

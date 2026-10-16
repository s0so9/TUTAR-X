"""Production-model baseline predictions for every row of the full feature file (2026-10-14).

The production model, with its goal layer refitted on the training split only:
  1. walk-forward rating lambdas (lambda_home_raw / lambda_away_raw of match_features_full.csv.gz,
     from walkforward_lambdas_full_2022_2026.csv)
  2. goal layer of data/training/goal_layer_train_only.json (fit_goal_layer.fit_layer logic, rows
     2022-08-01 .. 2025-06-30 only): s' = m + a (s - m) + b on the log total, supremacy unchanged
  3. supremacy shift  x = beta * value_log_ratio + gamma * lineup_form,
     mu_home = lambda_home * e^x, mu_away = lambda_away * e^-x
     beta = 0.048 for European-cup rows (cross-league), 0.0279 otherwise (app/prediction/squad_value.py);
     gamma = 0.2157 (config/player_form.json, read only). A missing value / form term means no shift
     for that term, exactly as in production (never imputed).
  4. score matrix 0..10 x 0..10: negative binomial (dispersion of the goal layer) x Dixon-Coles rho
     of the goal layer (train_goal_model.score_matrix).

Output (one row per feature row; rows without a rating lambda or without a result keep empty
predictions / labels and a status): see BASE_COLUMNS / the README section "baseline predictions".
Report: validation metrics (1X2 log loss / Brier, O/U 1.5 / 2.5 / 3.5, BTTS, exact score), per
segment (league / European / big matches), calibration by probability band, favourite hit rate by
band (incl. >= 85 % / >= 90 %), and 90 % bootstrap CIs (2,000 resamples, seed 7). The train split is
scored for reference; the test split is NOT scored here (its metrics are computed once, by the
modeller, after the configuration is frozen).

Caveat (recorded in the report): beta_domestic 0.0279 and gamma 0.2157 were fitted in production on
2,462 matches of Jan..Jun 2026 (experiment_lineup_strength.py), i.e. on part of the validation
(Jan 2026) and test (Feb..Jun 2026) periods. The baseline is the production model as deployed, so
these coefficients are kept; its validation / test numbers are slightly in-sample for those two
coefficients. The goal layer is train-only.

No network requests. Usage (from backend/):
  venv/Scripts/python.exe scripts/training/baseline_predictions.py
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

TRAINING_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TRAINING_DIR.parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TRAINING_DIR))
import train_goal_model as T  # noqa: E402

DATA = BACKEND_DIR / "data" / "training"
MAX_GOALS = T.MAX_GOALS
G = np.arange(MAX_GOALS + 1)
GAMMA_EXPECTED = 0.2157
BOOT_N = 2000
BOOT_SEED = 7
EURO = {"42", "73", "10216", "10611", "10613", "10615"}

BASE_COLUMNS = [
    "match_id", "kickoff", "split", "competition_provider_id", "comp_type", "home_team_id", "away_team_id",
    "status", "lambda_home_raw", "lambda_away_raw", "lambda_home_layer", "lambda_away_layer",
    "value_log_ratio", "lineup_form", "beta_value", "shift_value", "shift_form", "mu_home", "mu_away",
    "p_home", "p_draw", "p_away", "p_over15", "p_over25", "p_over35", "p_btts",
    "exp_total_goals", "p_score_0_0", "top1_score", "top1_p", "top2_score", "top2_p", "top3_score", "top3_p",
    "favourite", "p_favourite",
    "home_goals", "away_goals", "result", "over15", "over25", "over35", "btts",
]


def fnum(s) -> Optional[float]:
    if s is None or s == "":
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return None if math.isnan(v) else v


def load_layer(path: Path) -> dict:
    p = json.loads(path.read_text(encoding="utf-8"))["params"]
    return {k: float(p[k]) for k in ("m", "a", "b", "rho", "nb_dispersion")}


def production_coefficients() -> dict:
    from app.prediction.lineup_form import get_lineup_form
    from app.prediction.squad_value import SQUAD_VALUE_BETA, SQUAD_VALUE_BETA_DOMESTIC
    form = get_lineup_form()
    gamma = form.gamma if form is not None else None
    if gamma is None or abs(gamma - GAMMA_EXPECTED) > 1e-9:
        raise SystemExit(f"config/player_form.json gamma {gamma} != {GAMMA_EXPECTED}")
    return {"beta_value_cross_league": SQUAD_VALUE_BETA, "beta_value_domestic": SQUAD_VALUE_BETA_DOMESTIC,
            "gamma_form": gamma}


def apply_layer(lh: np.ndarray, la: np.ndarray, p: dict) -> tuple[np.ndarray, np.ndarray]:
    s = (np.log(lh) + np.log(la)) / 2
    d = (np.log(lh) - np.log(la)) / 2
    s2 = p["m"] + p["a"] * (s - p["m"]) + p["b"]
    return np.exp(s2 + d), np.exp(s2 - d)


def predict(rows: list[dict], layer: dict, coef: dict) -> dict:
    """Arrays for the rows that have both raw lambdas (``rows`` must all have them)."""
    lh = np.array([r["lambda_home_raw"] for r in rows])
    la = np.array([r["lambda_away_raw"] for r in rows])
    l1, l2 = apply_layer(lh, la, layer)
    beta = np.array([coef["beta_value_cross_league"] if r["competition_provider_id"] in EURO
                     else coef["beta_value_domestic"] for r in rows])
    v = np.array([np.nan if r["value_log_ratio"] is None else r["value_log_ratio"] for r in rows])
    f = np.array([np.nan if r["lineup_form"] is None else r["lineup_form"] for r in rows])
    sv = np.where(np.isnan(v), 0.0, beta * np.nan_to_num(v))
    sf = np.where(np.isnan(f), 0.0, coef["gamma_form"] * np.nan_to_num(f))
    mh, ma = l1 * np.exp(sv + sf), l2 * np.exp(-(sv + sf))
    out = {"l1": l1, "l2": l2, "beta": beta, "sv": sv, "sf": sf, "mh": mh, "ma": ma, "v": v, "f": f}
    n = len(rows)
    p1x2 = np.empty((n, 3))
    o15, o25, o35, btts, p00, et = (np.empty(n) for _ in range(6))
    top = []
    chunk = 20000
    tot = G[:, None] + G[None, :]
    for i in range(0, n, chunk):
        m = T.score_matrix(mh[i:i + chunk], ma[i:i + chunk], layer["rho"], layer["nb_dispersion"])
        p1x2[i:i + chunk, 0] = np.tril(m, -1).sum(axis=(1, 2))
        p1x2[i:i + chunk, 1] = np.trace(m, axis1=1, axis2=2)
        p1x2[i:i + chunk, 2] = np.triu(m, 1).sum(axis=(1, 2))
        o15[i:i + chunk] = (m * (tot > 1.5)).sum(axis=(1, 2))
        o25[i:i + chunk] = (m * (tot > 2.5)).sum(axis=(1, 2))
        o35[i:i + chunk] = (m * (tot > 3.5)).sum(axis=(1, 2))
        btts[i:i + chunk] = m[:, 1:, 1:].sum(axis=(1, 2))
        p00[i:i + chunk] = m[:, 0, 0]
        et[i:i + chunk] = (m * tot).sum(axis=(1, 2))
        flat = m.reshape(len(m), -1)
        order = np.argsort(-flat, axis=1, kind="stable")[:, :3]
        for j in range(len(m)):
            top.append([(int(k // (MAX_GOALS + 1)), int(k % (MAX_GOALS + 1)), float(flat[j, k])) for k in order[j]])
        if "score_p" not in out:
            out["score_p"] = np.empty(n)
        hs = np.array([r["hs"] if r["hs"] is not None else 0 for r in rows[i:i + chunk]], dtype=int)
        as_ = np.array([r["as"] if r["as"] is not None else 0 for r in rows[i:i + chunk]], dtype=int)
        out["score_p"][i:i + chunk] = m[np.arange(len(m)), np.clip(hs, 0, MAX_GOALS), np.clip(as_, 0, MAX_GOALS)]
    out.update(p1x2=p1x2, o15=o15, o25=o25, o35=o35, btts=btts, p00=p00, et=et, top=top)
    return out


# ---------------------------------------------------------------------------------------- metrics
def per_match_losses(rows: list[dict], P: dict, idx: np.ndarray) -> dict:
    eps = 1e-12
    hs = np.array([rows[i]["hs"] for i in idx])
    as_ = np.array([rows[i]["as"] for i in idx])
    k = np.where(hs > as_, 0, np.where(hs == as_, 1, 2))
    p = P["p1x2"][idx]
    out = {"1x2_logloss": -np.log(np.clip(p[np.arange(len(k)), k], eps, 1)),
           "1x2_brier": ((p - np.eye(3)[k]) ** 2).sum(1)}
    for name, q, y in (("over15", P["o15"][idx], hs + as_ > 1.5), ("over25", P["o25"][idx], hs + as_ > 2.5),
                       ("over35", P["o35"][idx], hs + as_ > 3.5), ("btts", P["btts"][idx], (hs > 0) & (as_ > 0))):
        out[f"{name}_logloss"] = -np.where(y, np.log(np.clip(q, eps, 1)), np.log(np.clip(1 - q, eps, 1)))
        out[f"{name}_brier"] = (q - y) ** 2
    out["score_logloss"] = -np.log(np.clip(P["score_p"][idx], eps, 1))
    out["_k"], out["_p"], out["_hs"], out["_as"] = k, p, hs, as_
    return out


METRICS = ["1x2_logloss", "1x2_brier", "over15_logloss", "over25_logloss", "over35_logloss", "over25_brier",
           "btts_logloss", "btts_brier", "score_logloss"]


def summarize(L: dict, P: dict, idx: np.ndarray, boot: bool = True) -> dict:
    n = len(idx)
    out = {"n": int(n)}
    if n == 0:
        return out
    rng = np.random.default_rng(BOOT_SEED)
    bidx = rng.integers(0, n, size=(BOOT_N, n)) if boot and n >= 30 else None
    for k in METRICS:
        v = L[k]
        e = {"mean": round(float(v.mean()), 5)}
        if bidx is not None:
            b = v[bidx].mean(1)
            e["ci90"] = [round(float(np.quantile(b, 0.05)), 5), round(float(np.quantile(b, 0.95)), 5)]
        out[k] = e
    out["mean_pred_total"] = round(float((P["mh"][idx] + P["ma"][idx]).mean()), 4)
    out["mean_actual_total"] = round(float((L["_hs"] + L["_as"]).mean()), 4)
    for j, nm in enumerate(("home", "draw", "away")):
        out[f"pred_{nm}_rate"] = round(float(L["_p"][:, j].mean()), 4)
        out[f"actual_{nm}_rate"] = round(float((L["_k"] == j).mean()), 4)
    fav = L["_p"].argmax(1)
    out["favourite_hit_rate"] = round(float((fav == L["_k"]).mean()), 4)
    return out


BANDS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 1.0001]


def band_table(p: np.ndarray, y: np.ndarray, bands=BANDS) -> list[dict]:
    out = []
    for lo, hi in zip(bands[:-1], bands[1:]):
        sel = (p >= lo) & (p < hi)
        if sel.sum():
            out.append({"band": f"[{lo:.2f},{min(hi, 1.0):.2f})", "n": int(sel.sum()),
                        "mean_pred": round(float(p[sel].mean()), 4), "actual": round(float(y[sel].mean()), 4)})
    return out


def calibration(L: dict, P: dict, idx: np.ndarray) -> dict:
    k, p = L["_k"], L["_p"]
    tot = L["_hs"] + L["_as"]
    fav = p.argmax(1)
    pf = p.max(1)
    out = {
        "home": band_table(p[:, 0], k == 0), "draw": band_table(p[:, 1], k == 1), "away": band_table(p[:, 2], k == 2),
        "over15": band_table(P["o15"][idx], tot > 1.5), "over25": band_table(P["o25"][idx], tot > 2.5),
        "over35": band_table(P["o35"][idx], tot > 3.5),
        "btts": band_table(P["btts"][idx], (L["_hs"] > 0) & (L["_as"] > 0)),
        "favourite_1x2": band_table(pf, fav == k, [0.33, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 1.0001]),
    }
    picks = {}
    for thr in (0.7, 0.8, 0.85, 0.9):
        sel = pf >= thr
        picks[f"fav_ge_{thr:.2f}"] = {"n": int(sel.sum()),
                                      "hit_rate": round(float((fav[sel] == k[sel]).mean()), 4) if sel.any() else None,
                                      "mean_pred": round(float(pf[sel].mean()), 4) if sel.any() else None}
    # two-way markets as single picks (the side with p >= threshold)
    for name, q, y in (("over15", P["o15"][idx], tot > 1.5), ("over25", P["o25"][idx], tot > 2.5),
                       ("btts", P["btts"][idx], (L["_hs"] > 0) & (L["_as"] > 0))):
        qq = np.maximum(q, 1 - q)
        hit = np.where(q >= 0.5, y, ~y)
        for thr in (0.7, 0.8, 0.85, 0.9):
            sel = qq >= thr
            picks[f"{name}_side_ge_{thr:.2f}"] = {
                "n": int(sel.sum()), "hit_rate": round(float(hit[sel].mean()), 4) if sel.any() else None,
                "mean_pred": round(float(qq[sel].mean()), 4) if sel.any() else None}
    out["pick_hit_rates"] = picks
    return out


def fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (float, np.floating)):
        if math.isnan(v):
            return ""
        return f"{float(v):.6f}".rstrip("0").rstrip(".") if v != 0 else "0"
    return str(v)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="production-model baseline predictions (train-only goal layer)")
    ap.add_argument("--features", type=Path, default=DATA / "match_features_full.csv.gz")
    ap.add_argument("--goal-layer", type=Path, default=DATA / "goal_layer_train_only.json")
    ap.add_argument("--out", type=Path, default=DATA / "baseline_predictions_full.csv.gz")
    ap.add_argument("--report", type=Path, default=DATA / "baseline_predictions_full_report.json")
    args = ap.parse_args(argv)
    t0 = time.time()
    layer = load_layer(args.goal_layer)
    coef = production_coefficients()

    rows = []
    with gzip.open(args.features, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            hs, as_ = fnum(r["y_home_goals"]), fnum(r["y_away_goals"])
            rows.append({
                "match_id": r["match_id"], "kickoff": r["kickoff"], "split": r.get("split", ""),
                "competition_provider_id": r["competition_provider_id"], "comp_type": r["comp_type"],
                "home_team_id": r["home_team_id"], "away_team_id": r["away_team_id"],
                "lambda_home_raw": fnum(r["lambda_home_raw"]), "lambda_away_raw": fnum(r["lambda_away_raw"]),
                "value_log_ratio": fnum(r["value_log_ratio"]), "lineup_form": fnum(r["lineup_form"]),
                "hs": None if hs is None else int(hs), "as": None if as_ is None else int(as_),
            })
    have = [i for i, r in enumerate(rows) if r["lambda_home_raw"] and r["lambda_away_raw"]]
    sub = [rows[i] for i in have]
    P = predict(sub, layer, coef)
    pos = {i: j for j, i in enumerate(have)}

    # ------------------------------------------------------------------ CSV
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + f".tmp{os.getpid()}")
    with open(tmp, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with io.TextIOWrapper(gz, encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(BASE_COLUMNS)
                for i, r in enumerate(rows):
                    has_res = r["hs"] is not None and r["as"] is not None
                    lab = {"home_goals": r["hs"], "away_goals": r["as"]}
                    if has_res:
                        hs, as_ = r["hs"], r["as"]
                        lab.update(result="H" if hs > as_ else ("D" if hs == as_ else "A"),
                                   over15=int(hs + as_ > 1.5), over25=int(hs + as_ > 2.5),
                                   over35=int(hs + as_ > 3.5), btts=int(hs > 0 and as_ > 0))
                    out = {k: r.get(k) for k in ("match_id", "kickoff", "split", "competition_provider_id",
                                                  "comp_type", "home_team_id", "away_team_id", "lambda_home_raw",
                                                  "lambda_away_raw", "value_log_ratio", "lineup_form")}
                    out.update(lab)
                    j = pos.get(i)
                    if j is None:
                        out["status"] = "no_lambda" if has_res else "no_lambda_no_result"
                    else:
                        out["status"] = "ok" if has_res else "no_result"
                        p3 = P["p1x2"][j]
                        fav = int(np.argmax(p3))
                        t = P["top"][j]
                        out.update(lambda_home_layer=P["l1"][j], lambda_away_layer=P["l2"][j], beta_value=P["beta"][j],
                                   shift_value=P["sv"][j] if not np.isnan(P["v"][j]) else None,
                                   shift_form=P["sf"][j] if not np.isnan(P["f"][j]) else None,
                                   mu_home=P["mh"][j], mu_away=P["ma"][j],
                                   p_home=p3[0], p_draw=p3[1], p_away=p3[2], p_over15=P["o15"][j],
                                   p_over25=P["o25"][j], p_over35=P["o35"][j], p_btts=P["btts"][j],
                                   exp_total_goals=P["et"][j], p_score_0_0=P["p00"][j],
                                   top1_score=f"{t[0][0]}-{t[0][1]}", top1_p=t[0][2],
                                   top2_score=f"{t[1][0]}-{t[1][1]}", top2_p=t[1][2],
                                   top3_score=f"{t[2][0]}-{t[2][1]}", top3_p=t[2][2],
                                   favourite="HDA"[fav], p_favourite=p3[fav])
                    w.writerow([fmt(out.get(c)) for c in BASE_COLUMNS])
    os.replace(tmp, args.out)

    # ------------------------------------------------------------------ report (train + validation only)
    report = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {"features": str(args.features), "goal_layer": str(args.goal_layer)},
        "model": {"goal_layer": layer, **coef,
                  "shift": "mu_home = lambda_home_layer * e^x, mu_away = lambda_away_layer * e^-x, "
                           "x = beta * value_log_ratio + gamma * lineup_form (missing term = 0)",
                  "beta_choice": "cross-league beta for competition ids 42/73/10216 and their qualifications, "
                                 "domestic beta otherwise",
                  "score_model": "negative binomial (nb_dispersion) x Dixon-Coles rho, scores 0..10"},
        "caveat": "beta_domestic 0.0279 and gamma 0.2157 were fitted in production on 2,462 matches of Jan..Jun "
                  "2026 (experiment_lineup_strength.py), which overlaps the validation (Jan 2026) and test "
                  "(Feb..Jun 2026) periods; kept because the baseline is the deployed model. The goal layer is "
                  "train-only (2022-08-01..2025-06-30).",
        "rows": len(rows), "rows_with_lambda": len(have),
        "status_counts": {},
        "metrics": {},
        "test_split": "not scored here (computed once by the modeller after the configuration is frozen)",
        "bootstrap": {"resamples": BOOT_N, "seed": BOOT_SEED, "ci": "90 % percentile, per metric (not paired)"},
    }
    from collections import Counter
    report["status_counts"] = dict(Counter((r["split"] or "none") + ":" + ("ok" if (i in pos and r["hs"] is not None)
                                                                         else "excluded") for i, r in enumerate(rows)))
    scored_rows = sub
    for split_name in ("train", "validation"):
        idx_all = np.array([j for j, r in enumerate(sub) if r["split"] == split_name and r["hs"] is not None
                            and r["as"] is not None], dtype=int)
        if len(idx_all) == 0:
            continue
        L = per_match_losses(scored_rows, P, idx_all)
        euro = np.array([sub[j]["competition_provider_id"] in EURO for j in idx_all])
        pf = L["_p"].max(1)
        segs = {"all": np.ones(len(idx_all), bool), "league": ~euro, "european": euro,
                "big_match_fav_ge_0.70": pf >= 0.70}
        block = {}
        for nm, sel in segs.items():
            Ls = {k: v[sel] for k, v in L.items()}
            block[nm] = summarize(Ls, P, idx_all[sel], boot=(split_name == "validation"))
        block["calibration"] = calibration(L, P, idx_all)
        block["calibration_european"] = calibration({k: v[euro] for k, v in L.items()}, P, idx_all[euro])
        by_comp = {}
        comps = np.array([sub[j]["competition_provider_id"] for j in idx_all])
        for c in sorted(set(comps), key=lambda c: -int((comps == c).sum())):
            sel = comps == c
            by_comp[c] = summarize({k: v[sel] for k, v in L.items()}, P, idx_all[sel], boot=False)
        block["by_competition"] = by_comp
        report["metrics"][split_name] = block
    report["seconds"] = round(time.time() - t0, 1)
    tmpr = args.report.with_name(args.report.name + f".tmp{os.getpid()}")
    tmpr.write_text(json.dumps(report, indent=1), encoding="utf-8")
    os.replace(tmpr, args.report)
    v = report["metrics"].get("validation", {}).get("all", {})
    print(json.dumps({k: v.get(k) for k in ["n", *METRICS]}, indent=1))
    print(f"-> {args.out}, {args.report} ({report['seconds']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

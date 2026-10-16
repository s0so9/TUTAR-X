"""Research (2026-10-15, "additional data" study): fetch venue elevation and kick-off weather from Open-Meteo
(free, non-commercial tier; data licence CC BY 4.0, https://open-meteo.com/en/terms).

* --elevation: https://api.open-meteo.com/v1/elevation, up to 100 coordinates per request (Copernicus DEM 90 m).
* --weather:   https://archive-api.open-meteo.com/v1/archive (ERA5-based reanalysis, hourly, UTC). One request per
  stadium and 14-day window (a request of <= 14 days and <= 10 variables counts as one API call), so the whole run
  stays far below the free limits (600 / min, 5,000 / hour, 10,000 / day): one request per --sleep seconds
  (default 1.0 s), at most --max-calls requests per run, every response cached as an untouched JSON file and never
  re-fetched. HTTP 429 or any 4xx stops the run (never retried around).

Inputs: data/research/xdata_match_context.csv (xdata_extract_context.py). Outputs under data/research/:
xdata_elevation.csv (lat, lon, elevation_m) and xdata_weather_raw/<lat>_<lon>_<start>_<end>.json, then
xdata_weather_at_kickoff.csv (match_id, temperature_2m, precipitation, rain, snowfall, wind_speed_10m,
wind_gusts_10m, relative_humidity_2m at the kick-off hour and precipitation summed over kick-off hour + 1).
Reanalysis is "what actually happened" (an upper bound for a pre-match forecast). Nothing is imputed.

Run (from backend/):
  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/xdata_fetch_open_meteo.py --elevation
  OMP_NUM_THREADS=2 venv/Scripts/python.exe -I scripts/research/xdata_fetch_open_meteo.py --weather --since 2025-07-01
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
RES = BACKEND / "data" / "research"
CTX = RES / "xdata_match_context.csv"
ELEV = RES / "xdata_elevation.csv"
RAW = RES / "xdata_weather_raw"
KICK = RES / "xdata_weather_at_kickoff.csv"
UA = "TUTAR-X research (non-commercial; contact via project owner)"
HOURLY = ["temperature_2m", "precipitation", "rain", "snowfall", "wind_speed_10m", "wind_gusts_10m",
          "relative_humidity_2m"]


def key(lat: str, lon: str) -> tuple[float, float]:
    return (round(float(lat), 3), round(float(lon), 3))


def key2(lat: str, lon: str) -> tuple[float, float]:
    """Weather grid key: 0.01 deg (~1 km), far finer than the ~0.25 deg reanalysis grid."""
    return (round(float(lat), 2), round(float(lon), 2))


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def load_ctx() -> list[dict]:
    with open(CTX, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["lat"] and r["lon"] and r["kickoff"]]


def elevation(args) -> int:
    rows = load_ctx()
    coords = sorted({key(r["lat"], r["lon"]) for r in rows})
    done = {}
    if ELEV.exists():
        with open(ELEV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                done[(float(r["lat"]), float(r["lon"]))] = r["elevation_m"]
    todo = [c for c in coords if c not in done]
    calls = 0
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        url = ("https://api.open-meteo.com/v1/elevation?" + urllib.parse.urlencode(
            {"latitude": ",".join(f"{c[0]}" for c in chunk), "longitude": ",".join(f"{c[1]}" for c in chunk)}))
        d = get_json(url)
        calls += 1
        for c, e in zip(chunk, d["elevation"]):
            done[c] = "" if e is None else str(e)
        time.sleep(args.sleep)
    with open(ELEV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["lat", "lon", "elevation_m"])
        for c in sorted(done):
            w.writerow([c[0], c[1], done[c]])
    print(json.dumps({"coords": len(coords), "requests": calls, "out": str(ELEV)}))
    return 0


def windows(dates: list[dt.date], span: int = 13) -> list[tuple[dt.date, dt.date]]:
    dates = sorted(set(dates))
    out, i = [], 0
    while i < len(dates):
        st = dates[i]
        en = st
        while i < len(dates) and (dates[i] - st).days < span:
            en = dates[i]
            i += 1
        out.append((st, en))
    return out


def _hourly_index(payload: dict) -> dict:
    h = payload.get("hourly") or {}
    out = {}
    for i, t in enumerate(h.get("time") or []):
        out[t] = {v: (h.get(v) or [None] * (i + 1))[i] for v in HOURLY}
    return out


def load_cache() -> dict:
    """stadium key2 -> {hour: values}. Reads single-location files (<lat>_<lon>_<start>_<end>.json) and batched
    files (block_<start>_<end>_<n>.json: {"keys": [[lat, lon], ...], "data": [payload, ...]})."""
    cache: dict = defaultdict(dict)
    for fp in RAW.glob("*.json"):
        d = json.loads(fp.read_text(encoding="utf-8"))
        if fp.stem.startswith("block_"):
            for k, payload in zip(d["keys"], d["data"]):
                cache[(float(k[0]), float(k[1]))].update(_hourly_index(payload))
        else:
            lat, lon, _, _ = fp.stem.split("_")
            cache[(float(lat), float(lon))].update(_hourly_index(d))
    return cache


def kick_hours(kickoff: str) -> tuple[str, str]:
    k = dt.datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
    t0 = k.replace(minute=0, second=0, microsecond=0)
    if k.minute >= 30:
        t0 = t0 + dt.timedelta(hours=1)
    return t0.strftime("%Y-%m-%dT%H:%M"), (t0 + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")


def weather(args) -> int:
    """Fixed 13-day calendar blocks; one request per block and batch of <= --batch stadiums (each location of
    <= 14 days and <= 10 variables = 1 API call). Paced by weighted calls: <= --calls-per-hour (default 4,000;
    free limit 5,000 / hour, 600 / minute). Matches already covered by the cache are not re-fetched."""
    import random
    RAW.mkdir(parents=True, exist_ok=True)
    since = dt.date.fromisoformat(args.since)
    rows = [r for r in load_ctx() if dt.date.fromisoformat(r["kickoff"][:10]) >= since]
    by = defaultdict(list)
    for r in rows:
        by[key2(r["lat"], r["lon"])].append(r)
    cache = load_cache()
    epoch = dt.date(2020, 1, 1)
    need = defaultdict(set)  # block start -> stadium keys
    for c, rs in by.items():
        for r in rs:
            h0, _ = kick_hours(r["kickoff"])
            if h0 in cache.get(c, {}):
                continue
            day = dt.date.fromisoformat(h0[:10])
            b0 = epoch + dt.timedelta(days=((day - epoch).days // 13) * 13)
            need[b0].add(c)
    jobs = []
    for b0, cs in need.items():
        cs = sorted(cs)
        for i in range(0, len(cs), args.batch):
            jobs.append((b0, cs[i:i + args.batch]))
    random.Random(20261015).shuffle(jobs)
    total_locs = sum(len(j[1]) for j in jobs)
    calls = 0
    stopped = None
    per_call_s = 3600.0 / args.calls_per_hour
    for b0, cs in jobs:
        if calls + len(cs) > args.max_calls:
            stopped = "max_calls"
            break
        b1 = b0 + dt.timedelta(days=13)  # 14 calendar days incl. the day after the block for late kick-offs
        # the archive lags real time by several days: never ask for dates after today - 7 (HTTP 400 otherwise)
        last_ok = dt.date.today() - dt.timedelta(days=7)
        if b0 > last_ok:
            continue
        b1 = min(b1, last_ok)
        fp = RAW / f"block_{b0}_{b1}_{cs[0][0]}_{cs[0][1]}_{len(cs)}.json"
        if fp.exists():
            continue
        url = ("https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(
            {"latitude": ",".join(str(c[0]) for c in cs), "longitude": ",".join(str(c[1]) for c in cs),
             "start_date": str(b0), "end_date": str(b1), "hourly": ",".join(HOURLY), "timezone": "GMT"}))
        t_start = time.time()
        d, err = None, None
        for wait in (0, 10, 30, 90):  # transient connection resets only; any HTTP error stops the run
            if wait:
                time.sleep(wait)
            try:
                d = get_json(url)
                err = None
                break
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code} at {fp.name}"
                break
            except Exception as e:  # noqa: BLE001 - network error: retried with backoff, then stop
                err = f"{type(e).__name__}: {e}"
        if d is None:
            stopped = err
            break
        if isinstance(d, dict):
            d = [d]
        tmp = fp.with_suffix(".tmp")
        tmp.write_text(json.dumps({"keys": [list(c) for c in cs], "data": d}), encoding="utf-8")
        tmp.replace(fp)
        calls += len(cs)
        # pace by weighted calls, counting the request's own duration
        time.sleep(max(0.0, per_call_s * len(cs) - (time.time() - t_start)))
    cache = load_cache()
    n_out = 0
    with open(KICK, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["match_id", "kickoff", "lat", "lon"] + HOURLY + ["precip_2h"])
        for c, rs in by.items():
            hourly = cache.get(c, {})
            for r in rs:
                h0, h1 = kick_hours(r["kickoff"])
                a, b = hourly.get(h0), hourly.get(h1)
                if a is None:
                    continue
                p2 = (a["precipitation"] + b["precipitation"]) if (b and a["precipitation"] is not None
                                                                   and b["precipitation"] is not None) else None
                w.writerow([r["match_id"], r["kickoff"], c[0], c[1]] + ["" if a[v] is None else a[v] for v in HOURLY]
                           + ["" if p2 is None else round(p2, 2)])
                n_out += 1
    print(json.dumps({"matches_since": len(rows), "stadiums": len(by), "jobs": len(jobs),
                      "locations_needed": total_locs, "new_weighted_calls": calls, "kickoff_rows": n_out,
                      "stopped": stopped, "out": str(KICK)}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--elevation", action="store_true")
    ap.add_argument("--weather", action="store_true")
    ap.add_argument("--since", default="2025-07-01")
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--max-calls", type=int, default=5000)
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--calls-per-hour", type=float, default=4000.0)
    args = ap.parse_args()
    if args.elevation:
        elevation(args)
    if args.weather:
        weather(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

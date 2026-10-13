"""Cross-process politeness limiter shared by every FotMob collector.

Several collectors may run at the same time (history fixtures, match details,
squads/players). Each one calls ``acquire()`` (or ``await acquire_async()``)
before every FotMob request. A lock directory (atomic ``mkdir``) serialises
access to a small JSON state file that holds the wall-clock times of recent
requests from all processes; a request is admitted only while fewer than
``rate`` requests were made in the last second. The default global budget is
5 requests/s, overridable with the env var ``FOTMOB_GLOBAL_RATE`` or, for
already-running collectors, by writing a number to ``<state dir>/rate.txt``.

After an HTTP 429 a collector calls ``report_429(seconds)``: every process then
waits until that cool-down has passed before its next request.

State lives in ``backend/data/raw_cache/.fotmob_rate/`` (git-ignored).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

DEFAULT_RATE = 5.0
STALE_LOCK_SECONDS = 5.0
STATE_DIR = Path(__file__).resolve().parents[2] / "data" / "raw_cache" / ".fotmob_rate"


def _rate(state_dir: Path = STATE_DIR) -> float:
    """Budget in requests/s: ``<state_dir>/rate.txt`` if present (lets an operator
    change the budget of running collectors), else ``FOTMOB_GLOBAL_RATE``, else 5."""
    raw = None
    try:
        raw = (state_dir / "rate.txt").read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        raw = os.environ.get("FOTMOB_GLOBAL_RATE")
    try:
        value = float(raw) if raw else DEFAULT_RATE
    except ValueError:
        value = DEFAULT_RATE
    return max(0.2, value)


class _Lock:
    def __init__(self, state_dir: Path):
        self.path = state_dir / "lock"

    def __enter__(self):
        while True:
            try:
                os.mkdir(self.path)
                return self
            except (FileExistsError, PermissionError):
                # Windows raises PermissionError ("access denied") when the directory
                # is being removed by another process at the same moment: just retry.
                try:
                    if time.time() - self.path.stat().st_mtime > STALE_LOCK_SECONDS:
                        os.rmdir(self.path)  # holder crashed
                        continue
                except (FileNotFoundError, PermissionError, OSError):
                    pass
                time.sleep(0.005)

    def __exit__(self, *exc):
        for _ in range(200):
            try:
                os.rmdir(self.path)
                return
            except FileNotFoundError:
                return
            except PermissionError:
                time.sleep(0.005)


def _retry(fn, attempts: int = 200):
    """Windows briefly denies access to a file another process (or a scanner) has
    open; retry for up to ~1 s instead of crashing the collector."""
    for i in range(attempts):
        try:
            return fn()
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.005)


def _read(state_file: Path) -> dict:
    try:
        return _retry(lambda: json.loads(state_file.read_text(encoding="utf-8")))
    except (FileNotFoundError, ValueError):
        return {"times": [], "cooldown_until": 0.0}


def _write(state_file: Path, state: dict) -> None:
    tmp = state_file.with_suffix(".tmp")
    _retry(lambda: tmp.write_text(json.dumps(state), encoding="utf-8"))
    _retry(lambda: os.replace(tmp, state_file))


def acquire(state_dir: Path = STATE_DIR, rate: float | None = None) -> None:
    """Block until this process may send one FotMob request."""
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "state.json"
    window = 1.0
    while True:
        budget = rate if rate is not None else _rate(state_dir)
        with _Lock(state_dir):
            state = _read(state_file)
            now = time.time()
            cooldown = float(state.get("cooldown_until", 0.0))
            if now < cooldown:
                wait = cooldown - now
            else:
                times = [t for t in state.get("times", []) if now - t < window]
                if len(times) < budget:
                    times.append(now)
                    state["times"] = times
                    _write(state_file, state)
                    return
                wait = window - (now - min(times)) + 0.005
        time.sleep(min(max(wait, 0.005), 30.0))


async def acquire_async(state_dir: Path = STATE_DIR, rate: float | None = None) -> None:
    await asyncio.to_thread(acquire, state_dir, rate)


def report_429(seconds: float, state_dir: Path = STATE_DIR) -> None:
    """Make every collector pause for ``seconds`` (e.g. a Retry-After value)."""
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "state.json"
    with _Lock(state_dir):
        state = _read(state_file)
        state["cooldown_until"] = max(float(state.get("cooldown_until", 0.0)), time.time() + max(0.0, seconds))
        _write(state_file, state)

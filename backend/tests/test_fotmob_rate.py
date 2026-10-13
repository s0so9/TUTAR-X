"""Tests for the cross-process FotMob politeness limiter (scripts/data_collection/fotmob_rate.py)."""

import importlib.util
import threading
import time
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "data_collection" / "fotmob_rate.py"
_spec = importlib.util.spec_from_file_location("fotmob_rate", _SCRIPT)
fotmob_rate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fotmob_rate)


def test_global_rate_is_shared_between_callers(tmp_path):
    stamps = []
    lock = threading.Lock()

    def worker():
        for _ in range(10):
            fotmob_rate.acquire(tmp_path, rate=10)
            with lock:
                stamps.append(time.time())

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stamps.sort()
    assert len(stamps) == 30
    # never more than 10 admissions inside any 1-second window (small slack for clock jitter)
    for i in range(len(stamps) - 10):
        assert stamps[i + 10] - stamps[i] >= 0.95
    # 30 requests at 10/s need at least ~2 s
    assert stamps[-1] - stamps[0] >= 1.9


def test_report_429_pauses_everyone(tmp_path):
    fotmob_rate.report_429(0.6, tmp_path)
    start = time.time()
    fotmob_rate.acquire(tmp_path, rate=100)
    assert time.time() - start >= 0.55


def test_stale_lock_is_recovered(tmp_path):
    (tmp_path / "lock").mkdir()
    old = time.time() - 60
    import os

    os.utime(tmp_path / "lock", (old, old))
    start = time.time()
    fotmob_rate.acquire(tmp_path, rate=5)
    assert time.time() - start < 1.0


def test_rate_file_overrides_budget(tmp_path):
    (tmp_path / "rate.txt").write_text("2", encoding="utf-8")
    start = time.time()
    for _ in range(3):
        fotmob_rate.acquire(tmp_path)
    # the third request must wait for the 1-second window at 2 req/s
    assert time.time() - start >= 0.9

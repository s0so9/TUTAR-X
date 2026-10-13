"""Raw-response archive of the live layer (gzip, atomic, only when content changed).

Layout (git-ignored, README in the directory):
  <root>/<kind>/<entity id>/<UTC yyyymmddThhmmssZ>.json.gz   untouched response body
  <root>/<kind>/_manifest.jsonl  one line per stored body:
      {"id", "fetched_at", "http_status", "bytes", "relevant_sha256", "path"}
kind = match_details | teams | players | leagues.

A body is stored when the hash of its *relevant* parsed content (line-ups and
unavailable lists, squad + injuries, profile + injury, fixtures) differs from
the last one stored for the same entity in this process, so every distinct
observation can be re-parsed offline without keeping identical copies.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.services.team_news.store import content_hash

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[3]
DEFAULT_RAW_ROOT = BACKEND_DIR / "data" / "raw_cache" / "live_team_news"


def default_raw_store() -> "RawStore":
    from app.config import settings

    if not settings.team_news_keep_raw:
        return RawStore(None)
    root = Path(settings.team_news_raw_cache_dir) if settings.team_news_raw_cache_dir else DEFAULT_RAW_ROOT
    return RawStore(root)


class RawStore:
    def __init__(self, root: Optional[Path]):
        self.root = Path(root) if root else None
        self._last: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()
        self.saved = 0

    @property
    def enabled(self) -> bool:
        return self.root is not None

    def save(self, kind: str, entity_id: str, raw: bytes, fetched_at: datetime, relevant: Any) -> Optional[Path]:
        if self.root is None or not raw:
            return None
        digest = content_hash(relevant)
        key = (kind, str(entity_id))
        with self._lock:
            if self._last.get(key) == digest:
                return None
            folder = self.root / kind / str(entity_id)
            try:
                folder.mkdir(parents=True, exist_ok=True)
                stamp = fetched_at.strftime("%Y%m%dT%H%M%S%fZ")
                target = folder / f"{stamp}.json.gz"
                tmp = folder / f".{stamp}.json.gz.tmp"
                tmp.write_bytes(gzip.compress(raw, compresslevel=6))
                os.replace(tmp, target)
                line = {
                    "id": str(entity_id),
                    "fetched_at": fetched_at.isoformat(),
                    "http_status": 200,
                    "bytes": len(raw),
                    "relevant_sha256": digest,
                    "path": target.relative_to(self.root).as_posix(),
                }
                with (self.root / kind / "_manifest.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(line, ensure_ascii=False) + "\n")
            except OSError:
                logger.exception("team-news: could not store raw %s/%s", kind, entity_id)
                return None
            self._last[key] = digest
            self.saved += 1
            return target

"""Rate-limited HTTP fetcher that caches every raw response body on disk.

Each response is stored gzipped under <cache_dir>/<source>/<key>.json.gz,
exactly as received. Responses that can no longer change (completed games,
past dates) are read from the cache forever; anything else is refetched
when `refresh=True`.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from . import config

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)


class SourceDown(Exception):
    """A data source failed after retries. The brief must not publish picks."""


class Fetcher:
    def __init__(self, source: str, min_interval_s: float, cache_dir: str | Path | None = None,
                 timeout: float = 20, retries: int = 3):
        cfg = config.load()["sources"]
        self.source = source
        self.min_interval_s = min_interval_s
        self.cache_dir = Path(cache_dir or config.ROOT / cfg["cache_dir"]) / source
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept": "application/json, text/html, */*"})
        self._last = 0.0
        self.network_calls = 0

    def cache_path(self, url: str, params: dict | None, name: str | None) -> Path:
        if name is None:
            full = url + ("?" + urlencode(sorted((params or {}).items())) if params else "")
            name = hashlib.sha1(full.encode()).hexdigest()[:20]
        return self.cache_dir / f"{name}.gz"

    def get(self, url: str, params: dict | None = None, name: str | None = None,
            refresh: bool = False) -> bytes:
        path = self.cache_path(url, params, name)
        if path.exists() and not refresh:
            return gzip.decompress(path.read_bytes())
        body = self._fetch(url, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(body, compresslevel=9))
        return body

    def get_json(self, url: str, params: dict | None = None, name: str | None = None,
                 refresh: bool = False):
        return json.loads(self.get(url, params, name, refresh))

    def _fetch(self, url: str, params: dict | None) -> bytes:
        err: Exception | None = None
        for attempt in range(self.retries):
            wait = self.min_interval_s - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.network_calls += 1
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as e:
                err = e
            else:
                if r.status_code == 200 and r.content:
                    return r.content
                err = SourceDown(f"{self.source}: HTTP {r.status_code}, {len(r.content)} bytes from {r.url[:150]}")
                if r.status_code in (400, 401, 403, 404):
                    break
                if r.status_code == 429:
                    time.sleep(30)
            time.sleep(2 ** attempt)
        raise SourceDown(f"{self.source}: {err}") from err

"""Rate-conscious, allowlisted image proxy for provider cover art.

Serves small image files from the VPS, not MongoDB. No arbitrary URL input
is accepted from visitors. External redirects are deliberately forbidden.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import threading
import time
from pathlib import Path

import requests
from PIL import Image, UnidentifiedImageError

from catalog_metadata import valid_cover

LOG = logging.getLogger('Sc.cover_proxy')
CACHE_DIR = Path(__file__).resolve().parent / 'data' / 'cover_cache'
MAX_IMAGE_BYTES = 8 * 1024 * 1024
TTL_SECONDS = 86400
_LOCK = threading.Lock()
Image.MAX_IMAGE_PIXELS = 25_000_000


def cover_bytes(url: str, *, session=None) -> bytes:
    """Return a small cover thumbnail, fetching only from trusted art hosts.

    Remote caching is skipped when providers respond with 'no-store'.
    """
    if not valid_cover(url):
        raise ValueError('Unrecognized artwork URL')
    cache = CACHE_DIR / (hashlib.sha256(url.encode('utf-8')).hexdigest() + '.webp')
    with _LOCK:
        if cache.is_file() and time.time() - cache.stat().st_mtime < TTL_SECONDS:
            return cache.read_bytes()
        client = session or requests
        try:
            response = client.get(url, stream=True, allow_redirects=False,
                                  headers={'User-Agent': 'ScCatalog/1.0', 'Accept': 'image/*'},
                                  timeout=(5, 15))
            try:
                response.raise_for_status()
                if response.is_redirect:
                    raise ValueError('Cover redirects are not allowed')
                if not response.headers.get('Content-Type', '').lower().startswith('image/'):
                    raise ValueError('Cover source did not return an image')
                size = 0
                raw = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    size += len(chunk)
                    if size > MAX_IMAGE_BYTES:
                        raise ValueError('Cover exceeds the size limit')
                    raw.extend(chunk)
                if not raw:
                    raise ValueError('Empty cover image')
            finally:
                response.close()
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    image.load()
                    image.thumbnail((900, 1600), Image.Resampling.LANCZOS)
                    picture = image.convert('RGB')
                    output = io.BytesIO()
                    picture.save(output, 'WEBP', quality=86, method=4)
                    data = output.getvalue()
            except (UnidentifiedImageError, OSError, ValueError) as exc:
                raise ValueError('Could not decode provider cover') from exc
            if 'no-store' not in response.headers.get('Cache-Control', '').lower():
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                path = cache.with_suffix('.tmp')
                path.write_bytes(data)
                os.replace(path, cache)
            return data
        except (requests.RequestException, OSError):
            LOG.warning('Cover fetch unavailable for approved host', exc_info=True)
            raise

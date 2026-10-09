"""Rate-conscious, allowlisted image proxy for provider cover art.

Serves small image files from the VPS, not MongoDB. No arbitrary URL input
is accepted from visitors. External redirects are deliberately forbidden.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import threading
import time
from urllib.parse import urljoin
from pathlib import Path

import requests
from PIL import Image, UnidentifiedImageError

from .catalog_metadata import valid_cover

LOG = logging.getLogger('Sc.cover_proxy')
CACHE_DIR = Path(__file__).resolve().parent.parent / 'data' / 'cover_cache'
MAX_IMAGE_BYTES = 8 * 1024 * 1024
TTL_SECONDS = 86400
_LOCK = threading.Lock()
Image.MAX_IMAGE_PIXELS = 25_000_000

OWNER_COVERS = Path(__file__).resolve().parent.parent / 'data' / 'cover_uploads'

def owner_cover_bytes(filename: str) -> bytes:
    """Serve only converted owner-uploaded covers under the private data tree."""
    if not isinstance(filename,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,200}\.webp', filename):
        raise ValueError('Invalid custom cover')
    p = OWNER_COVERS / filename
    if not p.is_file() or p.stat().st_size > MAX_IMAGE_BYTES:
        raise FileNotFoundError('Custom cover missing')
    return p.read_bytes()



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
            request_url = url
            for redirect_count in range(3):
                response = client.get(request_url, stream=True, allow_redirects=False,
                                      headers={'User-Agent': 'ScCatalog/1.0', 'Accept': 'image/*'},
                                      timeout=(5, 15))
                if response.is_redirect:
                    new_url = urljoin(request_url, response.headers.get('Location',''))
                    response.close()
                    if not valid_cover(new_url) or redirect_count == 2:
                        raise ValueError('Cover redirect to unapproved provider host')
                    request_url = new_url
                    continue
                break
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

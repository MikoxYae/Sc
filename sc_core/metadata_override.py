"""Owner-side recovery for published titles missing provider-supplied metadata.

Usage (on VPS, with source artwork you are authorized to use):
  .venv/bin/python3 metadata_override.py --category adult_manhwa \
      --slug example-title --cover-file /root/poster.jpg \
      --synopsis-file /root/summary.txt

Never stores cover image bytes in MongoDB. It only stores a safe internal
filename; the image is converted to WebP in data/cover_uploads/.
"""
from __future__ import annotations

import argparse
import io
import os
import re
from pathlib import Path
from PIL import Image, ImageOps
from .catalog_db import CATEGORIES, collection
from .catalog_metadata import clean_description, valid_cover
from .metadata_engine import normalize

ROOT = Path(__file__).resolve().parent.parent
COVERS = ROOT / 'data' / 'cover_uploads'


def convert_cover(source: Path, filename: str) -> str:
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,200}\.webp', filename):
        raise ValueError('Invalid internal cover filename')
    if not source.is_file() or source.stat().st_size > 15 * 1024 * 1024:
        raise ValueError('Cover must be an existing image under 15 MB')
    # PIL verifies format and image dimensions; no SVG or remote URL fetching.
    with Image.open(source) as raw:
        if raw.width * raw.height > 30_000_000:
            raise ValueError('Cover exceeds safe pixel count')
        raw.load()
        image = ImageOps.exif_transpose(raw).convert('RGB')
        image.thumbnail((1200, 2000), Image.Resampling.LANCZOS)
        stream = io.BytesIO()
        image.save(stream, format='WEBP', quality=88, method=4)
    COVERS.mkdir(parents=True, exist_ok=True)
    temp = COVERS / (filename + '.tmp')
    temp.write_bytes(stream.getvalue())
    os.replace(temp, COVERS / filename)
    return filename


def update(category: str, slug: str, cover_file=None, synopsis=None, cover_url=None, col=None, search_title=None):
    if category not in CATEGORIES or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,130}', slug):
        raise ValueError('Invalid category/slug')
    if not any((cover_file, synopsis, cover_url, search_title)):
        raise ValueError('Supply at least one cover or synopsis option')
    if search_title is not None and (not isinstance(search_title, str) or not 2 <= len(search_title.strip()) <= 120):
        raise ValueError('Search title must have 2-120 characters')
    if cover_url and not valid_cover(cover_url):
        raise ValueError('Use a supported provider HTTPS cover URL, or upload a local image')
    if synopsis is not None:
        synopsis = clean_description(synopsis)
        if synopsis is None:
            raise ValueError('Synopsis must have at least 26 characters')
    if col is None:
        col = collection(category)
    if col is None:
        raise RuntimeError('MongoDB is not configured')
    query = {'slug':slug, 'published':True, 'chapters.0':{'$exists':True}}
    if not col.find_one(query, {'_id':1}):
        raise ValueError('Published title not found; no new entry created')
    changes = {}
    sources = {}
    if cover_file:
        name = category + '-' + slug + '.webp'
        convert_cover(Path(cover_file), name)
        changes['cover_local'] = name
        sources['cover_local'] = 'owner_upload'
    elif cover_url:
        changes['cover_url'] = cover_url
        changes['cover_local'] = None
        sources['cover_url'] = 'owner_supplied_provider_url'
    if synopsis:
        changes['description'] = synopsis
        sources['description'] = 'owner_curated'
    updates = {'$set': {**changes, **{f'metadata_field_sources.{key}':value for key,value in sources.items()}}}
    if search_title:
        updates['$addToSet'] = {'metadata_search_titles': search_title.strip()}
        # Allow metadata_sync to retry newly supplied search names immediately.
        updates['$unset'] = {'metadata_lookup': ''}
    col.update_one(query, updates)
    return sorted(changes) + (['metadata_search_titles'] if search_title else [])


def main():
    p = argparse.ArgumentParser(description='Owner metadata correction for existing published manga')
    p.add_argument('--category', choices=sorted(CATEGORIES), required=True)
    p.add_argument('--slug', required=True)
    p.add_argument('--cover-file', help='Locally uploaded JPG/PNG/WebP cover artwork')
    p.add_argument('--cover-url', help='Verified provider-hosted HTTPS cover URL')
    p.add_argument('--synopsis', help='Owner-supplied synopsis text')
    p.add_argument('--synopsis-file', help='UTF-8 file containing a synopsis')
    p.add_argument('--search-title', help='Owner-confirmed exact alternative name to search metadata APIs')
    a = p.parse_args()
    if a.synopsis and a.synopsis_file:
        p.error('Use --synopsis or --synopsis-file, not both')
    if a.cover_file and a.cover_url:
        p.error('Use --cover-file or --cover-url, not both')
    desc = Path(a.synopsis_file).read_text(encoding='utf-8') if a.synopsis_file else a.synopsis
    try:
        result = update(a.category, a.slug, a.cover_file, desc, a.cover_url, search_title=a.search_title)
    except (ValueError, RuntimeError, OSError) as exc:
        p.exit(1, f'Could not update metadata: {exc}\n')
    print('Updated:', ', '.join(result), '- existing Telegram files and chapters unchanged.')

if __name__ == '__main__':
    main()

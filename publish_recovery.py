"""Crash-safe pending chapter-reference journal. Never stores PDFs or credentials.

Records are created only after a file has been copied to the configured
Telegram category channel. A record is replayable once all file parts are copied.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JOURNAL = ROOT / 'data' / 'publish_pending.json'
_LOCK = threading.RLock()


def key_for(category: str, title: str, chapter: str) -> str:
    import hashlib
    return hashlib.sha256(json.dumps([category, title, str(chapter)], ensure_ascii=False).encode()).hexdigest()


def _read():
    try:
        data = json.loads(JOURNAL.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _write(data):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    tmp = JOURNAL.with_suffix('.json.tmp')
    fd = os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, JOURNAL)
        os.chmod(JOURNAL, 0o600)
    finally:
        if tmp.exists():
            tmp.unlink()


def record(category, title, chapter, pages, channel, messages, *, ready=False):
    from catalog_db import CATEGORIES
    if category not in CATEGORIES or not title or not messages or not channel:
        raise ValueError('Invalid pending publication')
    clean_messages = []
    for ref in messages:
        mid = int(ref['message_id'])
        if mid < 1:
            raise ValueError('Invalid Telegram message ID')
        clean_messages.append({'message_id': mid, 'file_id': str(ref.get('file_id', '')),
                               'filename': str(ref.get('filename', ''))[:180]})
    with _LOCK:
        entries = _read()
        entries[key_for(category, title, chapter)] = {
            'category': category, 'title': str(title), 'chapter': str(chapter),
            'pages': max(0, int(pages)), 'channel': int(channel),
            'messages': clean_messages, 'ready': bool(ready),
        }
        _write(entries)


def forget(category, title, chapter):
    with _LOCK:
        entries = _read()
        if entries.pop(key_for(category, title, chapter), None) is not None:
            _write(entries)


def pending(category=None):
    with _LOCK:
        values = list(_read().values())
    return [x for x in values if isinstance(x, dict) and (category is None or x.get('category') == category)]


def replay(category=None, *, dry_run=True):
    """Recover completed Telegram copies that were not committed to MongoDB."""
    from catalog_db import CATEGORIES, save_published_chapter
    count = 0
    failed = 0
    for entry in pending(category):
        if not entry.get('ready') or entry.get('category') not in CATEGORIES:
            print('Pending partial Telegram copy (not automatically published).', flush=True)
            continue
        if dry_run:
            print('READY: ' + entry['category'] + ' / ' + entry['title'] + ' / Ch ' + entry['chapter'], flush=True)
            count += 1
            continue
        try:
            save_published_chapter(entry['category'], entry['title'], entry['chapter'],
                                   entry['pages'], entry['channel'], entry['messages'])
            forget(entry['category'], entry['title'], entry['chapter'])
            print('RECOVERED: ' + entry['category'] + ' / ' + entry['title'] + ' / Ch ' + entry['chapter'], flush=True)
            count += 1
        except Exception as exc:
            failed += 1
            print('FAILED: ' + entry.get('category', '?') + ' / ' + type(exc).__name__, flush=True)
    return count, failed

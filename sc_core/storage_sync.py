"""Recover published chapter references from an existing category storage channel.

Never downloads PDF bytes. Default is dry-run. Example:
  .venv/bin/python3 storage_sync.py --category adult_manhwa --apply

MTProto bot channel-history access depends on Telegram permissions. If unavailable,
use the durable publish_pending.json journal for new uploads or re-upload a chapter.
"""
import argparse
import asyncio
import json
import re
from pathlib import Path

from .catalog_db import CATEGORIES, collection, save_published_chapter
from .publish_recovery import replay

ROOT = Path(__file__).resolve().parent.parent
PDF_RE = re.compile(r'^(.+?)\s*-\s*(?:chapter|ch)\s*(\d+(?:[._]\d+)?)'
                    r'(?:\s*-\s*part\s*(\d+)\s+of\s+(\d+))?\.pdf$', re.IGNORECASE)


def parse_pdf_name(name):
    if not isinstance(name, str):
        return None
    match = PDF_RE.fullmatch(name.strip())
    if not match:
        return None
    title, chapter, part, total = match.groups()
    if not title.strip() or len(title) > 180:
        return None
    n, total = int(part or 1), int(total or 1)
    if not 1 <= n <= total <= 100:
        return None
    return (title.strip(), chapter.replace('_', '.'), n, total)


def selected_channel(category):
    settings_path = ROOT / 'data' / 'settings.json'
    try:
        settings = json.loads(settings_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    channel = settings.get('storage_channels', {}).get(category)
    try:
        return int(channel) if channel else None
    except (TypeError, ValueError):
        return None


def existing(col, title, chapter):
    import re
    slug = re.sub(r'[^a-z0-9]+', '-', title.casefold()).strip('-')[:130]
    doc = col.find_one({'slug': slug, 'published': True}, {'chapters.number': 1}) or {}
    return any(str(ch.get('number')) == str(chapter) for ch in doc.get('chapters', []))


async def read_history(channel, limit):
    import config
    from pyrogram import Client
    api_id = int(getattr(config, 'API_ID', 0))
    api_hash = getattr(config, 'API_HASH', '')
    token = getattr(config, 'BOT_TOKEN', '')
    if not api_id or not api_hash or not token:
        raise RuntimeError('Configure Telegram API_ID, API_HASH and BOT_TOKEN in private config.py')
    client = Client('sc_storage_sync', api_id=api_id, api_hash=api_hash,
                    bot_token=token, in_memory=True, no_updates=True)
    async with client:
        messages = []
        async for message in client.get_chat_history(channel, limit=limit):
            doc = getattr(message, 'document', None)
            if not doc or getattr(doc, 'mime_type', '') != 'application/pdf':
                continue
            parsed = parse_pdf_name(getattr(doc, 'file_name', None))
            if parsed:
                messages.append((parsed, {'message_id': message.id,
                    'file_id': getattr(doc, 'file_id', ''), 'filename': doc.file_name}))
        return messages


def groups_from_messages(messages):
    """Use only complete, parseable chapter PDFs (never guess missing parts)."""
    groups = {}
    for (title, chapter, part, total), ref in messages:
        key = (title, chapter)
        group = groups.setdefault(key, {'total': total, 'parts': {}})
        if group['total'] != total:
            # Conflicting versions require explicit intervention.
            group['conflict'] = True
            continue
        # get_chat_history yields latest first; preserve newest message for each part.
        group['parts'].setdefault(part, ref)
    for (title, chapter), group in groups.items():
        count = group['total']
        if group.get('conflict') or set(group['parts']) != set(range(1, count + 1)):
            yield title, chapter, None
        else:
            yield title, chapter, [group['parts'][n] for n in range(1, count + 1)]


async def main():
    parser = argparse.ArgumentParser(description='Check and repair category publishing without re-downloading PDFs')
    parser.add_argument('--category', required=True, choices=sorted(CATEGORIES))
    parser.add_argument('--limit', type=int, default=100, help='Recent messages to inspect, 1..500')
    parser.add_argument('--apply', action='store_true', help='Write verified complete references to MongoDB')
    args = parser.parse_args()
    if not 1 <= args.limit <= 500:
        parser.error('--limit must be 1..500')
    channel = selected_channel(args.category)
    if not channel:
        print('NOT CONFIGURED: Bot Settings > Storage > Channel ID > ' + args.category)
        return 2
    col = collection(args.category)
    if col is None:
        print('NOT CONFIGURED: MongoDB URI missing')
        return 2
    try:
        col.database.client.admin.command('ping')
    except Exception as exc:
        print('MongoDB connection failed: ' + type(exc).__name__)
        return 2
    count, failures = replay(args.category, dry_run=not args.apply)
    if failures:
        print('Failed to recover pending records; check MongoDB permissions.')
    print('Telegram category channel configured. Inspecting stored PDF posts...')
    try:
        records = await read_history(channel, args.limit)
    except Exception as exc:
        print('Cannot inspect channel history: ' + type(exc).__name__)
        print('Check bot administrator access and Telegram API credentials. Existing PDFs remain untouched.')
        return 2
    missing = 0
    skipped = 0
    for title, chapter, refs in groups_from_messages(records):
        if refs is None:
            skipped += 1
            print('SKIPPED incomplete/conflicting PDF parts:', title[:70], 'Ch', chapter)
            continue
        if existing(col, title, chapter):
            continue
        missing += 1
        print(('RESTORING' if args.apply else 'WOULD RESTORE'), title[:75], 'Ch', chapter, 'parts:', len(refs))
        if args.apply:
            try:
                save_published_chapter(args.category, title, chapter, 0, channel, refs)
            except Exception as exc:
                print('DB WRITE FAILED: ' + type(exc).__name__)
                failures += 1
    print(f'Category: {args.category}; pending: {count}; missing: {missing}; skipped: {skipped}; errors: {failures}')
    print('PDF files were not downloaded or uploaded.')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))

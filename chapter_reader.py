"""On-demand Telegram PDF -> vertical page image cache. MongoDB stores references only."""
import asyncio
import hashlib
import json
import logging
import os
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from catalog_db import CATEGORIES, collection

LOG = logging.getLogger('Sc.reader')
CACHE = Path(os.getenv('SC_READER_CACHE', str(Path(__file__).parent / 'data' / 'reader_cache')))
CACHE.mkdir(parents=True, exist_ok=True)
WORKERS = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ScReader')
JOBS = {}
LOCK = threading.Lock()
RUNNING = set()
MAX_PAGES = int(os.getenv('SC_READER_MAX_PAGES', '600'))
MAX_BYTES = int(os.getenv('SC_READER_MAX_MB', '400')) * 1048576
TTL = int(os.getenv('SC_READER_CACHE_HOURS', '72')) * 3600
# Do not poll forever when Telegram download or PDF rendering stalls.
JOB_TIMEOUT = max(60, int(os.getenv('SC_READER_JOB_TIMEOUT', '240')))
PART_TIMEOUT = max(30, int(os.getenv('SC_READER_PART_TIMEOUT', '120')))
RETRY_DELAY = max(5, int(os.getenv('SC_READER_RETRY_DELAY', '20')))



def validate(category, slug, number):
    if category not in CATEGORIES or not slug or len(slug) > 150 or not number or len(number) > 50:
        raise ValueError('Invalid chapter identifier')
    if any(x in slug for x in ('/', '..', chr(92))):
        raise ValueError('Invalid title identifier')


def chapter_record(category, slug, number):
    validate(category, slug, number)
    col = collection(category)
    if col is None:
        raise RuntimeError('Catalog database unavailable')
    doc = col.find_one({'slug': slug, 'published': True}, {'chapters': 1})
    if not doc:
        raise FileNotFoundError('Story not found')
    for item in (doc.get('chapters') or []):
        if not isinstance(item, dict) or str(item.get('number')) != number:
            continue
        telegram = item.get('telegram')
        if not isinstance(telegram, dict):
            raise FileNotFoundError('Chapter has no Telegram storage reference')
        documents = telegram.get('documents')
        try:
            chat_id = int(telegram.get('chat_id'))
            if not isinstance(documents, list) or not documents:
                raise ValueError('No documents')
            if len(documents) > 100:
                raise ValueError('Too many documents')
            for ref in documents:
                if not isinstance(ref, dict) or int(ref.get('message_id', 0)) <= 0:
                    raise ValueError('Invalid Telegram message reference')
        except (TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError('Chapter storage references are incomplete. Re-publish this chapter.') from exc
        if chat_id == 0:
            raise RuntimeError('Chapter storage channel is not configured.')
        return {'chat_id': chat_id, 'documents': documents}
    raise FileNotFoundError('Chapter not found')


def key_for(category, slug, number):
    return hashlib.sha256(json.dumps([category, slug, number], ensure_ascii=False).encode()).hexdigest()


def _manifest(folder):
    try:
        data = json.loads((folder / 'manifest.json').read_text())
        if data.get('pages', 0) < 1:
            return None
        if all((folder / f'{n:04d}.webp').is_file() for n in range(1, data['pages'] + 1)):
            return data
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return None


async def _download_parts(telegram, target):
    """Fetch PDFs from storage channel, with bounded Telegram operations."""
    try:
        from pyrogram import Client
    except ImportError as exc:
        raise RuntimeError('Pyrofork missing. Install project requirements.') from exc
    import config
    api_id = int(getattr(config, 'API_ID', 0))
    api_hash = getattr(config, 'API_HASH', '')
    token = getattr(config, 'BOT_TOKEN', '')
    if not api_id or not api_hash or not token:
        raise RuntimeError('Telegram API_ID, API_HASH or BOT_TOKEN missing')
    client = Client('sc_reader', api_id=api_id, api_hash=api_hash,
                    bot_token=token, in_memory=True, no_updates=True)
    started = False
    try:
        await asyncio.wait_for(client.start(), timeout=40)
        started = True
        for index, ref in enumerate(telegram['documents'], 1):
            msg_id = int(ref['message_id'])
            msg = await asyncio.wait_for(client.get_messages(int(telegram['chat_id']), msg_id), timeout=30)
            if not msg or not msg.document:
                raise FileNotFoundError(f'Telegram PDF part {index} unavailable; verify channel permissions')
            if msg.document.file_size and msg.document.file_size > MAX_BYTES:
                raise RuntimeError('PDF part exceeds reader size limit')
            filename = target / f'part_{index:03d}.pdf'
            # Pyrogram can return a different output path; use the actual returned path.
            result = await asyncio.wait_for(client.download_media(msg, file_name=str(filename)), timeout=PART_TIMEOUT)
            if not result:
                raise RuntimeError(f'Telegram download returned no file for part {index}')
            downloaded = Path(result)
            if not downloaded.is_file():
                raise RuntimeError(f'Downloaded PDF part {index} is missing')
            if downloaded.resolve() != filename.resolve():
                shutil.move(str(downloaded), str(filename))
            if filename.stat().st_size > MAX_BYTES:
                raise RuntimeError('Telegram PDF part exceeds reader size limit')
            LOG.info('Reader fetched Telegram PDF part %d/%d (%d bytes)', index, len(telegram['documents']), filename.stat().st_size)
    except asyncio.TimeoutError as exc:
        raise RuntimeError('Telegram download timed out. Check storage channel and VPS network.') from exc
    finally:
        if started:
            try:
                await asyncio.wait_for(client.stop(), timeout=15)
            except Exception:
                LOG.warning('Reader Telegram client shutdown failed', exc_info=True)


def _build(key, telegram):
    import pymupdf
    target = CACHE / key
    work = Path(tempfile.mkdtemp(prefix='sc-reader-', dir=str(CACHE)))
    try:
        asyncio.run(_download_parts(telegram, work))
        count = 0
        total_bytes = 0
        for pdf_path in sorted(work.glob('part_*.pdf')):
            total_bytes += pdf_path.stat().st_size
            if total_bytes > MAX_BYTES:
                raise RuntimeError('Chapter exceeds reader size limit')
            with pymupdf.open(pdf_path) as pdf:
                if pdf.needs_pass:
                    raise RuntimeError('Encrypted PDF is not supported')
                if count + len(pdf) > MAX_PAGES:
                    raise RuntimeError('Chapter exceeds reader page limit')
                for page in pdf:
                    count += 1
                    # Downscale to a mobile-friendly width, without distorting the page.
                    scale = min(1.6, 1400 / max(page.rect.width, 1), 12000 / max(page.rect.height, 1))
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                    from PIL import Image
                    import io
                    with Image.open(io.BytesIO(pix.tobytes('png'))) as image:
                        image.save(work / f'{count:04d}.webp', 'WEBP', quality=86, method=4)
        if count == 0:
            raise RuntimeError('No pages found in chapter PDF')
        (work / 'manifest.json').write_text(json.dumps({'pages': count, 'created': time.time()}))
        for pdf_path in work.glob('part_*.pdf'):
            pdf_path.unlink()
        if target.exists():
            shutil.rmtree(target)
        work.rename(target)
    except Exception:
        LOG.exception('Reader preparation failed for cache key %.12s', key)
        raise
    finally:
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)


def _public_error(exc):
    # Do not send raw Pyrogram / filesystem exception text to browser clients.
    text = str(exc)
    approved = (
        'Telegram download timed out', 'Telegram PDF part', 'PDF part exceeds',
        'Telegram PDF part exceeds', 'Reader preparation timed out',
        'No pages found', 'Chapter exceeds', 'Encrypted PDF',
        'Pyrofork missing',
    )
    if any(text.startswith(prefix) for prefix in approved):
        return text[:140]
    return 'Unable to prepare this chapter. Check storage permissions or retry later.'


def _job(key, telegram):
    try:
        _build(key, telegram)
        with LOCK:
            JOBS[key] = {'status': 'ready', 'at': time.time()}
    except Exception as exc:
        with LOCK:
            JOBS[key] = {'status': 'error', 'error': _public_error(exc), 'at': time.time()}
    finally:
        with LOCK:
            RUNNING.discard(key)


def prepare(category, slug, number):
    telegram = chapter_record(category, slug, number)
    key = key_for(category, slug, number)
    manifest = _manifest(CACHE / key)
    if manifest:
        return {'status': 'ready', 'pages': manifest['pages']}
    with LOCK:
        job = JOBS.get(key)
        if job and job['status'] == 'processing' and time.time() - job.get('at', 0) > JOB_TIMEOUT:
            # The worker may still be alive. Do not start overlapping workers.
            JOBS[key] = {'status': 'error', 'error': 'Reader preparation timed out. Check server logs.', 'at': time.time()}
            job = JOBS[key]
        if job and job['status'] == 'error' and time.time() - job.get('at', 0) > RETRY_DELAY:
            # Only retry after worker is finished; an expired running job must not duplicate.
            if key not in RUNNING:
                job = None
        if not job:
            JOBS[key] = {'status': 'processing', 'at': time.time()}
            RUNNING.add(key)
            WORKERS.submit(_job, key, telegram)
            return {'status': 'processing'}
        return dict(job)


def page_path(category, slug, number, page):
    validate(category, slug, number)
    if not page.isdecimal() or len(page) > 4:
        raise ValueError('Invalid page number')
    folder = CACHE / key_for(category, slug, number)
    manifest = _manifest(folder)
    if not manifest or not 1 <= int(page) <= manifest['pages']:
        raise FileNotFoundError('Page not ready')
    return folder / f'{int(page):04d}.webp'


def cleanup_cache():
    if TTL <= 0:
        return
    now = time.time()
    for folder in CACHE.iterdir():
        if folder.is_dir() and len(folder.name) == 64 and now - folder.stat().st_mtime > TTL:
            shutil.rmtree(folder, ignore_errors=True)

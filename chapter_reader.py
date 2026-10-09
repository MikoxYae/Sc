"""On-demand Telegram PDF to progressively readable WebP pages.

Telegram holds documents. MongoDB holds only references. The VPS caches files
and renders pages; neither PDFs nor images are stored in MongoDB.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import requests
from catalog_db import CATEGORIES, collection

LOG = logging.getLogger('Sc.reader')
CACHE = Path(os.getenv('SC_READER_CACHE', str(Path(__file__).parent / 'data' / 'reader_cache')))
CACHE.mkdir(parents=True, exist_ok=True)
WORKERS = ThreadPoolExecutor(max_workers=max(1, min(2, int(os.getenv('SC_READER_WORKERS', '2')))),
                             thread_name_prefix='ScReader')
JOBS = {}
ACTIVE_FOLDERS = {}
LOCK = threading.RLock()
RUNNING = set()
LAST_CLEANUP = 0.0
MAX_PAGES = int(os.getenv('SC_READER_MAX_PAGES', '600'))
MAX_BYTES = int(os.getenv('SC_READER_MAX_MB', '400')) * 1048576
TTL = int(os.getenv('SC_READER_CACHE_HOURS', '72')) * 3600
# Job timestamps track last progress, not total running time.
JOB_TIMEOUT = max(120, int(os.getenv('SC_READER_JOB_TIMEOUT', '600')))
PART_TIMEOUT = max(90, int(os.getenv('SC_READER_PART_TIMEOUT', '180')))
STALL_TIMEOUT = max(45, int(os.getenv('SC_READER_STALL_TIMEOUT', '90')))
RETRY_DELAY = max(10, int(os.getenv('SC_READER_RETRY_DELAY', '25')))
BOT_API_MAX = 20 * 1024 * 1024
IMAGE_WIDTH = max(640, min(1800, int(os.getenv('SC_READER_IMAGE_WIDTH', '1200'))))
IMAGE_QUALITY = max(65, min(95, int(os.getenv('SC_READER_IMAGE_QUALITY', '83'))))


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
    for item in doc.get('chapters') or []:
        if not isinstance(item, dict) or str(item.get('number')) != number:
            continue
        telegram = item.get('telegram')
        if not isinstance(telegram, dict):
            raise FileNotFoundError('Chapter has no Telegram storage reference')
        documents = telegram.get('documents')
        try:
            chat_id = int(telegram.get('chat_id'))
            if not isinstance(documents, list) or not documents or len(documents) > 100:
                raise ValueError('No valid documents')
            for ref in documents:
                if not isinstance(ref, dict) or int(ref.get('message_id', 0)) <= 0:
                    raise ValueError('Invalid message ID')
        except (TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError('Chapter storage references are incomplete. Re-publish this chapter.') from exc
        if chat_id == 0:
            raise RuntimeError('Chapter storage channel is not configured.')
        try:
            total = max(0, min(MAX_PAGES, int(item.get('pages') or 0)))
        except (ValueError, TypeError):
            total = 0
        return {'chat_id': chat_id, 'documents': documents, 'pages_total': total}
    raise FileNotFoundError('Chapter not found')


def key_for(category, slug, number, telegram=None):
    """Use the Telegram post IDs to invalidate cache after chapter replacement."""
    identity = [category, slug, number]
    if telegram is not None:
        identity.extend([int(telegram['chat_id']),
                         [int(ref['message_id']) for ref in telegram['documents']]])
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def _manifest(folder):
    try:
        data = json.loads((folder / 'manifest.json').read_text())
        pages = data.get('pages')
        if type(pages) is not int or not 0 < pages <= MAX_PAGES:
            return None
        if (folder / '0001.webp').is_file() and (folder / f'{pages:04d}.webp').is_file():
            return data
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return None


def _status(key, **update):
    with LOCK:
        previous = JOBS.get(key)
        if not previous or previous.get('status') != 'processing':
            return
        previous.update(update)
        previous['at'] = time.monotonic()


def _existing_pdf(filename, advertised_size=0):
    if not filename.is_file():
        return False
    size = filename.stat().st_size
    if not 0 < size <= MAX_BYTES or (advertised_size and size != advertised_size):
        return False
    with filename.open('rb') as f:
        return f.read(5) == b'%PDF-'


def _download_bot_api(ref, filename, token, key, index, total):
    """Fast path for cloud Bot API downloads <20 MB; no Telegram login/session.

    Never log URLs, request bodies or tokens. Return False for unsupported files
    or transient failures so large/challenging documents use MTProto instead.
    """
    file_id = ref.get('file_id')
    if not isinstance(file_id, str) or not file_id:
        return False
    try:
        claimed = int(ref.get('file_size') or ref.get('size') or 0)
    except (TypeError, ValueError):
        claimed = 0
    if claimed >= BOT_API_MAX:
        return False
    url = f'https://api.telegram.org/bot{token}/getFile'
    try:
        with requests.Session() as session:
            data = session.post(url, json={'file_id': file_id}, timeout=(6, 12)).json()
            if not data.get('ok') or not isinstance(data.get('result'), dict):
                return False
            info = data['result']
            size = int(info.get('file_size') or 0)
            if size > BOT_API_MAX or size > MAX_BYTES:
                return False
            file_path = info.get('file_path', '')
            if not isinstance(file_path, str) or not file_path:
                return False
            downloaded = 0
            # A 20 second idle socket timeout is independent of total transfer duration.
            with session.get(f'https://api.telegram.org/file/bot{token}/{file_path}',
                             stream=True, timeout=(6, 25)) as response:
                response.raise_for_status()
                temp = filename.with_suffix('.download')
                try:
                    with temp.open('wb') as out:
                        for chunk in response.iter_content(chunk_size=256 * 1024):
                            if not chunk:
                                continue
                            downloaded += len(chunk)
                            if downloaded > MAX_BYTES:
                                raise RuntimeError('PDF part exceeds reader size limit')
                            out.write(chunk)
                            _status(key, stage='downloading', downloaded_bytes=downloaded,
                                    download_total=size, part=index, parts=total)
                    if not _existing_pdf(temp, size):
                        raise ValueError('Invalid or incomplete PDF download')
                    temp.replace(filename)
                finally:
                    temp.unlink(missing_ok=True)
            LOG.info('Reader Bot API download succeeded for part %d/%d (%.1f MB)',
                     index, total, downloaded / 1048576)
            return True
    except (requests.RequestException, ValueError, OSError, KeyError) as exc:
        LOG.info('Reader Bot API fast path unavailable for part %d (%s); using MTProto',
                 index, type(exc).__name__)
        return False


async def _mtproto_download(client, telegram, ref, filename, key, index, total):
    msg_id = int(ref['message_id'])
    msg = await asyncio.wait_for(client.get_messages(int(telegram['chat_id']), msg_id), timeout=40)
    if not msg or not getattr(msg, 'document', None):
        raise FileNotFoundError(f'Telegram PDF part {index} unavailable; verify storage permissions')
    size = int(getattr(msg.document, 'file_size', 0) or 0)
    if size > MAX_BYTES:
        raise RuntimeError('PDF part exceeds reader size limit')
    # Allow slow *progressing* transfers, but detect stalls instead of failing
    # every file at a fixed two-minute deadline.
    hard_limit = max(PART_TIMEOUT, min(1800, size / 65536 + 120))
    state = {'last': time.monotonic(), 'bytes': 0}

    def progress(current, total_size):
        if current > state['bytes']:
            state['last'] = time.monotonic()
            state['bytes'] = current
            _status(key, stage='downloading', part=index, parts=total,
                    downloaded_bytes=current, download_total=total_size)

    task = asyncio.create_task(client.download_media(msg, file_name=str(filename), progress=progress))
    began = time.monotonic()
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=3)
            if time.monotonic() - state['last'] > STALL_TIMEOUT:
                raise TimeoutError(f'Telegram transfer stalled for PDF part {index}')
            if time.monotonic() - began > hard_limit:
                raise TimeoutError(f'Telegram download was too slow for PDF part {index}')
        result = await task
        if not result:
            raise RuntimeError(f'Telegram returned no file for part {index}')
        actual = Path(result)
        if not actual.is_file():
            raise RuntimeError(f'Downloaded PDF part {index} is missing')
        if actual.resolve() != filename.resolve():
            shutil.move(str(actual), str(filename))
        if not _existing_pdf(filename, size):
            raise RuntimeError(f'Incomplete Telegram PDF part {index}')
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


async def _download_parts(telegram, target, key, on_part=None):
    import config
    api_id = int(getattr(config, 'API_ID', 0))
    api_hash = getattr(config, 'API_HASH', '')
    token = getattr(config, 'BOT_TOKEN', '')
    if not api_id or not api_hash or not token:
        raise RuntimeError('Telegram credentials are missing from config.py')

    client = None
    try:
        for index, ref in enumerate(telegram['documents'], 1):
            filename = target / f'part_{index:03d}.pdf'
            total = len(telegram['documents'])
            try:
                expected = int(ref.get('file_size') or ref.get('size') or 0)
            except (ValueError, TypeError):
                expected = 0
            if _existing_pdf(filename, expected):
                if on_part:
                    await on_part(filename)
                continue
            filename.unlink(missing_ok=True)
            _status(key, stage='connecting', part=index, parts=total,
                    downloaded_bytes=0, download_total=expected)
            if await asyncio.to_thread(_download_bot_api, ref, filename, token, key, index, total):
                if on_part:
                    await on_part(filename)
                continue
            if client is None:
                try:
                    from pyrogram import Client
                except ImportError as exc:
                    raise RuntimeError('Pyrofork missing. Install requirements.txt.') from exc
                client = Client('sc_reader', api_id=api_id, api_hash=api_hash,
                                bot_token=token, in_memory=True, no_updates=True)
                _status(key, stage='connecting')
                try:
                    await asyncio.wait_for(client.start(), timeout=60)
                except asyncio.TimeoutError as exc:
                    raise TimeoutError('Telegram MTProto connection timed out') from exc
            _status(key, stage='downloading', part=index, parts=total,
                    downloaded_bytes=0, download_total=expected)
            await _mtproto_download(client, telegram, ref, filename, key, index, total)
            LOG.info('Reader MTProto PDF fetched: part %d/%d (%.1f MB)',
                     index, total, filename.stat().st_size / 1048576)
            if on_part:
                await on_part(filename)
    finally:
        if client is not None:
            try:
                await asyncio.wait_for(client.stop(), timeout=15)
            except Exception:
                LOG.warning('Reader MTProto disconnect failed (%s)', type(client).__name__)


def _render_pdf(pdf_path, work, count, key):
    """Publish each converted page immediately for progressive web reading."""
    import pymupdf
    from PIL import Image
    with pymupdf.open(pdf_path) as pdf:
        if pdf.needs_pass:
            raise RuntimeError('Encrypted PDF is not supported')
        total_pages = len(pdf)
        if count + total_pages > MAX_PAGES:
            raise RuntimeError('Chapter exceeds reader page limit')
        for page in pdf:
            count += 1
            scale = min(1.7, IMAGE_WIDTH / max(page.rect.width, 1),
                        12000 / max(page.rect.height, 1))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            # Converting directly from RGB samples avoids a slow PNG encode + decode.
            image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            path = work / f'{count:04d}.webp'
            temporary = work / f'{count:04d}.tmp'
            try:
                image.save(temporary, 'WEBP', quality=IMAGE_QUALITY, method=2)
                temporary.replace(path)  # No partial WebP is ever served.
            finally:
                temporary.unlink(missing_ok=True)
                image.close()
            _status(key, stage='rendering', pages_ready=count)
    return count


def _build(key, telegram):
    target = CACHE / key
    work = Path(tempfile.mkdtemp(prefix=f'.work-{key[:12]}-', dir=str(CACHE)))
    with LOCK:
        ACTIVE_FOLDERS[key] = work
    try:
        count = 0
        if len(telegram['documents']) > 1:
            # Multipart: show pages from part 1 while later PDFs are still downloading.
            # A page is individually published through an atomic WebP rename.
            async def publish_part(pdf_path):
                nonlocal count
                _status(key, stage='rendering', pages_total=telegram.get('pages_total', 0),
                        pages_ready=count)
                count = await asyncio.to_thread(_render_pdf, pdf_path, work, count, key)
                pdf_path.unlink(missing_ok=True)
            asyncio.run(_download_parts(telegram, work, key, on_part=publish_part))
        else:
            # A non-linearized PDF generally requires its final xref bytes before
            # page 1 can be decoded; don't pretend to render an incomplete file.
            asyncio.run(_download_parts(telegram, work, key))
            pdfs = sorted(work.glob('part_*.pdf'))
            if len(pdfs) != len(telegram['documents']):
                raise RuntimeError('Some chapter PDF parts are missing')
            total_bytes = sum(p.stat().st_size for p in pdfs)
            if total_bytes > MAX_BYTES:
                raise RuntimeError('Chapter exceeds reader size limit')
            import pymupdf
            with pymupdf.open(pdfs[0]) as pdf:
                total_pages = len(pdf)
            if total_pages == 0 or total_pages > MAX_PAGES:
                raise RuntimeError('Chapter contains no pages or exceeds reader page limit')
            _status(key, stage='rendering', pages_total=total_pages, pages_ready=0)
            count = _render_pdf(pdfs[0], work, 0, key)
            pdfs[0].unlink(missing_ok=True)
        if count < 1 or count > MAX_PAGES:
            raise RuntimeError('Chapter contains no pages or exceeds reader page limit')
        (work / 'manifest.json').write_text(json.dumps({'pages': count, 'created': time.time()}))
        if target.exists():
            shutil.rmtree(target)
        work.rename(target)
        LOG.info('Reader ready: %d pages (%s)', count, key[:12])
    except Exception:
        LOG.exception('Reader preparation failed for cache key %.12s', key)
        raise
    finally:
        with LOCK:
            ACTIVE_FOLDERS.pop(key, None)
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)



def _seed_worker(key, work, names):
    """Build images from an upload's original files without re-downloading PDF."""
    try:
        from PIL import Image, ImageOps
        for index, src in enumerate(names, 1):
            with Image.open(src) as opened:
                image = ImageOps.exif_transpose(opened).convert('RGB')
            try:
                width, height = image.size
                scale = min(1.0, IMAGE_WIDTH / max(width, 1), 12000 / max(height, 1))
                if scale < 1:
                    image = image.resize((max(1, round(width*scale)),
                                          max(1, round(height*scale))), Image.Resampling.LANCZOS)
                final = work / f'{index:04d}.webp'
                temp = work / f'{index:04d}.tmp'
                try:
                    image.save(temp, format='WEBP', quality=IMAGE_QUALITY, method=2)
                    temp.replace(final)
                finally:
                    temp.unlink(missing_ok=True)
            finally:
                image.close()
            _status(key, stage='rendering', pages_ready=index, pages_total=len(names))
            # Original byte copy is no longer needed after an image is served.
            src.unlink(missing_ok=True)
        (work / 'manifest.json').write_text(json.dumps({'pages': len(names), 'created': time.time()}))
        target = CACHE / key
        if target.exists():
            shutil.rmtree(target)
        work.rename(target)
        with LOCK:
            JOBS[key] = {'status': 'ready', 'at': time.monotonic()}
        LOG.info('Reader pages pre-warmed from uploaded originals: %d pages (%s)', len(names), key[:12])
    except Exception as exc:
        LOG.exception('Reader upload pre-warm failed for %.12s', key)
        with LOCK:
            # Don't strand a reader on a failed optimization: the next request
            # should fall back to downloading the durable PDF from Telegram.
            JOBS.pop(key, None)
    finally:
        with LOCK:
            ACTIVE_FOLDERS.pop(key, None)
            RUNNING.discard(key)
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)


def seed_uploaded_chapter(category, title, number, channel, messages, images_dir):
    """Stage page images before upload temporary files disappear.

    Runs after publication. Existing PDFs in Telegram remain the durable source;
    cache is a disposable acceleration only, keyed by the actual post IDs.
    """
    _queue_cleanup()
    slug = re.sub(r'[^a-z0-9]+', '-', title.casefold()).strip('-')[:130]
    validate(category, slug, str(number))
    telegram = {'chat_id': int(channel), 'documents': messages}
    key = key_for(category, slug, str(number), telegram)
    originals = sorted(path for path in Path(images_dir).iterdir()
                       if path.is_file() and path.suffix.lower() in ('.jpg', '.jpeg', '.png'))
    if not originals or len(originals) > MAX_PAGES:
        return False
    if sum(path.stat().st_size for path in originals) > MAX_BYTES:
        LOG.warning('Reader pre-warm skipped: original images exceed cache limit')
        return False
    if _manifest(CACHE / key):
        return True
    with LOCK:
        if key in RUNNING:
            return False
        RUNNING.add(key)
        JOBS[key] = {'status': 'processing', 'stage': 'queued', 'pages_ready': 0,
                     'pages_total': len(originals), 'at': time.monotonic()}
    work = CACHE / f'.seed-{key[:12]}-{uuid4().hex}'
    names = []
    try:
        work.mkdir()
        # Copy before TemporaryDirectory in Miko.py is removed. No MongoDB binary storage.
        for n, source in enumerate(originals, 1):
            dest = work / f'source_{n:04d}{source.suffix.lower()}'
            shutil.copyfile(source, dest)
            names.append(dest)
        with LOCK:
            ACTIVE_FOLDERS[key] = work
        try:
            WORKERS.submit(_seed_worker, key, work, names)
        except RuntimeError:
            raise
        return True
    except Exception:
        LOG.exception('Reader original-page staging failed (non-fatal)')
        with LOCK:
            ACTIVE_FOLDERS.pop(key, None)
            RUNNING.discard(key)
            JOBS.pop(key, None)
        shutil.rmtree(work, ignore_errors=True)
        return False


def _public_error(exc):
    msg = str(exc)
    allowed = ('Telegram transfer stalled', 'Telegram download was too slow',
               'Telegram MTProto connection timed out', 'Telegram PDF part',
               'Incomplete Telegram PDF', 'PDF part exceeds',
               'Chapter exceeds', 'Chapter contains no pages',
               'Encrypted PDF', 'Pyrofork missing',
               'Telegram credentials are missing', 'Reader preparation timed out')
    if msg.startswith(allowed):
        return msg[:150]
    return 'Chapter could not be prepared. Check the storage bot permissions or VPS logs.'


def _job(key, telegram):
    try:
        _build(key, telegram)
        with LOCK:
            JOBS[key] = {'status': 'ready', 'at': time.monotonic()}
    except Exception as exc:
        with LOCK:
            JOBS[key] = {'status': 'error', 'error': _public_error(exc), 'at': time.monotonic()}
    finally:
        with LOCK:
            RUNNING.discard(key)


def prepare(category, slug, number):
    _queue_cleanup()
    telegram = chapter_record(category, slug, number)
    key = key_for(category, slug, number, telegram)
    manifest = _manifest(CACHE / key)
    if manifest:
        return {'status': 'ready', 'pages': manifest['pages']}
    with LOCK:
        job = JOBS.get(key)
        if job and job['status'] == 'processing' and (time.monotonic() - job.get('at', 0)) > JOB_TIMEOUT:
            if key not in RUNNING:
                job = None
            else:
                # Current download is still alive; do not start a second one.
                return dict(job)
        if job and job['status'] == 'error' and time.monotonic() - job['at'] > RETRY_DELAY:
            if key not in RUNNING:
                job = None
        if not job:
            job = {'status': 'processing', 'stage': 'queued', 'pages_ready': 0,
                   'pages_total': 0, 'at': time.monotonic()}
            JOBS[key] = job
            RUNNING.add(key)
            WORKERS.submit(_job, key, telegram)
        return {k: v for k, v in job.items() if k != 'at'}


def page_path(category, slug, number, page, telegram=None):
    validate(category, slug, number)
    if not page.isdecimal() or len(page) > 4:
        raise ValueError('Invalid page number')
    if telegram is None:
        telegram = chapter_record(category, slug, number)
    key = key_for(category, slug, number, telegram)
    folder = CACHE / key
    manifest = _manifest(folder)
    number = int(page)
    if manifest and 1 <= number <= manifest['pages']:
        return folder / f'{number:04d}.webp'
    with LOCK:
        job = JOBS.get(key) or {}
        active = ACTIVE_FOLDERS.get(key)
        available = int(job.get('pages_ready') or 0)
        if job.get('status') == 'processing' and active and 1 <= number <= available:
            image = active / f'{number:04d}.webp'
            if image.is_file():
                return image
    raise FileNotFoundError('Page not ready')


def cleanup_cache():
    if TTL <= 0:
        return
    now = time.time()
    with LOCK:
        in_progress = set(ACTIVE_FOLDERS.values())
    for folder in CACHE.iterdir():
        if folder.is_dir() and folder not in in_progress and now - folder.stat().st_mtime > TTL:
            if len(folder.name) == 64 or folder.name.startswith(('.work-', '.seed-')):
                shutil.rmtree(folder, ignore_errors=True)


def _queue_cleanup():
    """Do not let reader images fill the VPS disk indefinitely."""
    global LAST_CLEANUP
    with LOCK:
        now = time.monotonic()
        if now - LAST_CLEANUP < 3600:
            return
        LAST_CLEANUP = now
    try:
        WORKERS.submit(cleanup_cache)
    except RuntimeError:
        pass  # During interpreter shutdown, no further work may be submitted.

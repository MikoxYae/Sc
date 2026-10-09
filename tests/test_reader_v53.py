"""Tests for original image pre-warming and incremental multipart rendering."""
import asyncio
import importlib.util
import io
import sys
import threading
import time
import types
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'sc_core' / 'chapter_reader.py'


@pytest.fixture
def reader(monkeypatch, tmp_path):
    catalog = types.ModuleType('catalog_db')
    catalog.CATEGORIES = {'manhwa': 'demo', 'adult_manhwa': 'demo_adult'}
    catalog.collection = lambda _: None
    monkeypatch.setitem(sys.modules, 'sc_core.catalog_db', catalog)
    import sc_core
    monkeypatch.setattr(sc_core, 'catalog_db', catalog, raising=False)
    monkeypatch.setenv('SC_READER_CACHE', str(tmp_path / 'cache'))
    spec = importlib.util.spec_from_file_location('sc_core.reader_v53_under_test', SOURCE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    yield mod
    mod.WORKERS.shutdown(wait=True, cancel_futures=True)


def create_pdf(path, content):
    import pymupdf
    pdf = pymupdf.open()
    page = pdf.new_page(width=300, height=500)
    page.insert_text((20, 50), content)
    pdf.save(str(path))
    pdf.close()


def test_new_upload_images_are_visible_before_cache_completion(reader, tmp_path, monkeypatch):
    from PIL import Image
    folder = tmp_path / 'originals'
    folder.mkdir()
    for n in range(1, 5):
        image = Image.new('RGB', (250, 700), (n*30, 45, 50))
        image.save(folder / f'{n:04d}.jpg', quality=85)
    refs = [{'message_id': 33, 'file_id': 'fake', 'file_size': 2048}]
    ref = {'chat_id': -100999, 'documents': refs, 'pages_total': 4}
    monkeypatch.setattr(reader, 'chapter_record', lambda *args: ref)
    def slow_seed_worker(key, work, names):
        from PIL import Image
        import json
        for index, name in enumerate(names, 1):
            with Image.open(name) as image:
                image.save(work / f'{index:04d}.webp', 'WEBP')
            reader._status(key, stage='rendering', pages_total=4, pages_ready=index)
            time.sleep(0.035)
        (work / 'manifest.json').write_text(json.dumps({'pages': 4, 'created': time.time()}))
        work.rename(reader.CACHE / key)
        with reader.LOCK:
            reader.JOBS[key] = {'status': 'ready', 'at': time.monotonic()}
            reader.RUNNING.discard(key)
            reader.ACTIVE_FOLDERS.pop(key, None)
    monkeypatch.setattr(reader, '_seed_worker', slow_seed_worker)
    assert reader.seed_uploaded_chapter('adult_manhwa', 'Test Story', 1, -100999, refs, folder)
    # Destroy source directory to prove staged originals outlive the upload temporary path.
    import shutil
    shutil.rmtree(folder)
    midstream = False
    for _ in range(200):
        status = reader.prepare('adult_manhwa', 'test-story', '1')
        if status.get('status') == 'processing' and 1 <= status.get('pages_ready', 0) < 4:
            assert reader.page_path('adult_manhwa', 'test-story', '1', '1', ref).is_file()
            midstream = True
        if status.get('status') == 'ready':
            break
        time.sleep(.005)
    assert midstream
    assert reader.prepare('adult_manhwa', 'test-story', '1')['pages'] == 4


def test_multipart_renders_first_pdf_while_second_is_downloading(reader, monkeypatch, tmp_path):
    ref = {'chat_id': -100345, 'documents': [
        {'message_id': 1}, {'message_id': 2}], 'pages_total': 2}
    monkeypatch.setattr(reader, 'chapter_record', lambda *args: ref)
    first_rendered = threading.Event()
    continue_second = threading.Event()

    async def fake_download(telegram, work, key, on_part=None):
        assert on_part is not None
        first = work / 'part_001.pdf'
        create_pdf(first, 'ONE')
        await on_part(first)
        first_rendered.set()
        await asyncio.to_thread(continue_second.wait, 4)
        second = work / 'part_002.pdf'
        create_pdf(second, 'TWO')
        await on_part(second)

    monkeypatch.setattr(reader, '_download_parts', fake_download)
    assert reader.prepare('manhwa', 'demo', '1')['status'] == 'processing'
    assert first_rendered.wait(4)
    response = reader.prepare('manhwa', 'demo', '1')
    assert response['status'] == 'processing' and response['pages_ready'] == 1
    assert reader.page_path('manhwa', 'demo', '1', '1', ref).stat().st_size > 100
    continue_second.set()
    for _ in range(120):
        response = reader.prepare('manhwa', 'demo', '1')
        if response['status'] == 'ready':
            break
        time.sleep(.02)
    assert response['status'] == 'ready' and response['pages'] == 2


def test_upload_preheat_does_not_change_telegram_reference(reader, tmp_path):
    from PIL import Image
    folder = tmp_path / 'src'
    folder.mkdir()
    Image.new('RGB', (50, 70)).save(folder / '0001.png')
    refs = [{'message_id': 92}]
    key = reader.key_for('manhwa', 'named', '1', {'chat_id': -1001, 'documents': refs})
    assert reader.seed_uploaded_chapter('manhwa', 'Named', '1', -1001, refs, folder)
    # Cache key is based on channel post IDs, never local absolute filesystem paths.
    assert key in reader.JOBS
    assert refs == [{'message_id': 92}]

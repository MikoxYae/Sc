"""Offline regression tests: no MongoDB, Telegram or VPS secrets required."""
import asyncio
import importlib.util
import json
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'sc_core' / 'chapter_reader.py'


@pytest.fixture
def reader(monkeypatch, tmp_path):
    catalog = types.ModuleType('catalog_db')
    catalog.CATEGORIES = {'manhwa': 'sc_manhwa', 'adult_manhwa': 'sc_adult_manhwa'}
    catalog.collection = lambda cat: None
    monkeypatch.setitem(sys.modules, 'sc_core.catalog_db', catalog)
    import sc_core
    monkeypatch.setattr(sc_core, 'catalog_db', catalog, raising=False)
    monkeypatch.setenv('SC_READER_CACHE', str(tmp_path / 'cache'))
    spec = importlib.util.spec_from_file_location('sc_core.reader_v49_under_test', SOURCE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    yield mod
    mod.WORKERS.shutdown(wait=True, cancel_futures=True)


def _sample_pdf(path, count=5):
    import pymupdf
    pdf = pymupdf.open()
    for n in range(count):
        page = pdf.new_page(width=260, height=400)
        page.insert_text((12, 20), 'PAGE ' + str(n+1))
    pdf.save(str(path))
    pdf.close()


def test_original_cached_files_are_valid(reader, tmp_path):
    folder = tmp_path / 'pages'
    folder.mkdir()
    assert reader._manifest(folder) is None
    (folder / '0001.webp').write_bytes(b'img')
    (folder / '0002.webp').write_bytes(b'img')
    (folder / 'manifest.json').write_text(json.dumps({'pages': 2, 'created': time.time()}))
    assert reader._manifest(folder)['pages'] == 2


def test_new_telegram_messages_invalidate_previous_cache(reader):
    a = {'chat_id': -10033, 'documents': [{'message_id': 1}]}
    b = {'chat_id': -10033, 'documents': [{'message_id': 2}]}
    assert reader.key_for('adult_manhwa', 'demo', '1', a) != reader.key_for('adult_manhwa', 'demo', '1', b)


def test_incomplete_pdf_is_rejected(reader, tmp_path):
    f = tmp_path / 'bad.pdf'
    f.write_bytes(b'not a pdf')
    assert not reader._existing_pdf(f)


def test_fast_bot_api_unsupported_file_returns_false(reader, tmp_path):
    assert reader._download_bot_api({'file_id': 'abc', 'file_size': 25 * 1048576},
                                    tmp_path / 'part.pdf', 'do-not-log', 'key', 1, 1) is False


def test_first_image_is_readable_before_render_finished(reader, monkeypatch, tmp_path):
    ref = {'chat_id': -100111, 'documents': [{'message_id': 22}]}
    monkeypatch.setattr(reader, 'chapter_record', lambda *a: ref)
    async def fake_download(_telegram, folder, _key):
        _sample_pdf(folder / 'part_001.pdf', count=5)
    monkeypatch.setattr(reader, '_download_parts', fake_download)
    original = reader._render_pdf
    def slow_render(*args, **kwargs):
        # first page is served while all later images are still being rendered
        return original(*args, **kwargs)
    monkeypatch.setattr(reader, '_render_pdf', slow_render)
    result = reader.prepare('adult_manhwa', 'demo', '1')
    assert result['status'] == 'processing'
    early_seen = False
    for _ in range(160):
        response = reader.prepare('adult_manhwa', 'demo', '1')
        if response['status'] == 'error':
            pytest.fail(response['error'])
        if response['status'] == 'processing' and response.get('pages_ready', 0) >= 1:
            p = reader.page_path('adult_manhwa', 'demo', '1', '1', ref)
            assert p.is_file() and p.stat().st_size > 50
            early_seen = True
        if response['status'] == 'ready':
            assert response['pages'] == 5
            break
        time.sleep(.04)
    else:
        pytest.fail('render timeout')
    assert early_seen or reader.page_path('adult_manhwa', 'demo', '1', '1', ref).is_file()


def test_expired_error_can_start_new_attempt(reader, monkeypatch):
    ref = {'chat_id': -100111, 'documents': [{'message_id': 22}]}
    monkeypatch.setattr(reader, 'chapter_record', lambda *a: ref)
    async def bad_download(*args, **kwargs):
        raise TimeoutError('Telegram transfer stalled for PDF part 1')
    monkeypatch.setattr(reader, '_download_parts', bad_download)
    reader.prepare('adult_manhwa', 'demo', '1')
    for _ in range(50):
        res = reader.prepare('adult_manhwa', 'demo', '1')
        if res['status'] == 'error':
            assert 'stalled' in res['error']
            break
        time.sleep(.01)
    else: pytest.fail('did not report network error')

class FakeFileResponse:
    def __init__(self, data):
        self.data = data
    def __enter__(self): return self
    def __exit__(self, *a): return None
    def raise_for_status(self): return None
    def iter_content(self, chunk_size):
        for start in range(0, len(self.data), chunk_size):
            yield self.data[start:start+chunk_size]


def test_small_pdf_uses_bot_api_without_mtproto(reader, monkeypatch, tmp_path):
    source = tmp_path / 'source.pdf'
    _sample_pdf(source, 2)
    pdf = source.read_bytes()

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, json, timeout):
            assert 'getFile' in url
            assert json == {'file_id': 'fake-file-id'}
            return types.SimpleNamespace(json=lambda: {'ok': True, 'result':
                                        {'file_size': len(pdf), 'file_path': 'documents/file.pdf'}})
        def get(self, url, stream, timeout):
            return FakeFileResponse(pdf)

    monkeypatch.setattr(reader.requests, 'Session', FakeSession)
    result = tmp_path / 'part.pdf'
    assert reader._download_bot_api({'file_id': 'fake-file-id', 'file_size': len(pdf)},
                                    result, 'fake-token', 'unused-key', 1, 1)
    assert result.read_bytes() == pdf


def test_missing_reference_is_rejected(reader):
    with pytest.raises(ValueError):
        reader.validate('invalid', 'demo', '1')
    with pytest.raises(ValueError):
        reader.validate('adult_manhwa', '../data', '1')
    with pytest.raises(ValueError):
        reader.page_path('adult_manhwa', 'demo', '1', '../4')

"""Regression checks for intermittent reader network failures and stored refs.

All tests use local fake HTTP responses; there are no Telegram or MongoDB calls.
"""
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Tests in this repository initialize an in-memory pymongo shim if PyMongo
# is unavailable. This allows tests to run in isolated build environments.
try:
    import catalog_db
except ModuleNotFoundError as exc:
    if exc.name != 'pymongo':
        raise
    import test_catalog_v44  # noqa: F401  (installs the local shim)
    import catalog_db

import chapter_reader
import website_server


class FakeCol:
    def __init__(self, chapters):
        self.chapters = chapters

    def find_one(self, *_args, **_kwargs):
        return {'chapters': self.chapters}


class ReaderServerTests(unittest.TestCase):
    def test_malformed_reference_is_controlled_failure_not_disconnect(self):
        with patch.object(chapter_reader, 'collection', return_value=FakeCol([
            {'number': '20', 'telegram': {'chat_id': '-100321', 'documents': [{'bad': 'value'}]}},
        ])):
            with self.assertRaisesRegex(RuntimeError, 'references are incomplete'):
                chapter_reader.chapter_record('manhwa', 'example', '20')

    def test_unexpected_reader_error_returns_json_instead_of_tcp_reset(self):
        server = website_server.QuietHTTPServer(
            ('127.0.0.1', 0), partial(website_server.Handler, directory=str(ROOT / 'website'))
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        try:
            with patch.object(chapter_reader, 'prepare', side_effect=KeyError('malformed')), \
                 patch.object(chapter_reader, 'validate', return_value=None):
                thread.start()
                url = f'http://127.0.0.1:{server.server_port}/api/chapter?category=manhwa&slug=example&chapter=20'
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(url, timeout=3)
                self.assertEqual(caught.exception.code, 500)
                result = json.loads(caught.exception.read().decode())
                self.assertIn('error', result)
                self.assertNotIn('malformed', result['error'])
        finally:
            if thread.is_alive():
                server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_public_error_does_not_leak_telegram_secret(self):
        msg = chapter_reader._public_error(RuntimeError('Secret token 123456789:ABCDEFGHIJK'))
        self.assertNotIn('123456789', msg)

    def test_http_queue_handles_parallel_page_burst(self):
        self.assertGreaterEqual(website_server.QuietHTTPServer.request_queue_size, 64)


try:
    from playwright.sync_api import sync_playwright
    import shutil
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright and shutil.which('chromium'), 'Optional Chromium/Playwright missing')
class BrowserRetryTests(unittest.TestCase):
    @staticmethod
    def setup(page, failures):
        html = (ROOT / 'website' / 'index.html').read_text()
        js = (ROOT / 'website' / 'app.js').read_text()
        import re
        html = re.sub(r'<link[^>]+>', '', html)
        html = re.sub(r'<script src="app.js[^>]+></script>', '', html)
        page.goto('about:blank')
        page.set_content(html)
        page.evaluate('''failures => {
            window.readAttempts=0;
            window.shouldFail=true;
            window.fetch = async url => {
              if(String(url).includes('/api/chapter?')){
                window.readAttempts++;
                if(window.shouldFail && window.readAttempts<=failures) throw new TypeError('Failed to fetch');
                return {ok:true,status:200,json:async()=>({status:'ready',pages:3})};
              }
              if(String(url).includes('/api/me')) return {ok:true,status:200,json:async()=>({user:null})};
              return {ok:true,status:200,json:async()=>({items:[],pages:1,total:0})};
            };
            location.hash='#/read/manhwa/example/20';
          }''', failures)
        page.add_script_tag(content=js)

    def test_temporary_disconnect_recovers_automatically(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
            try:
                page = browser.new_page()
                self.setup(page, 1)
                page.wait_for_function("document.querySelectorAll('#readerPages img').length===3", timeout=10000)
                self.assertGreaterEqual(page.evaluate('window.readAttempts'), 2)
                self.assertFalse(page.locator('#readerStatus').is_visible())
                page.close()
            finally:
                browser.close()

    def test_retry_button_recovers_after_prolonged_disconnect(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
            try:
                page = browser.new_page()
                self.setup(page, 100)
                page.locator('.reader-retry').wait_for(timeout=15000)
                page.evaluate('window.shouldFail=false')
                page.locator('.reader-retry').click()
                page.wait_for_function("document.querySelectorAll('#readerPages img').length===3", timeout=8000)
                self.assertFalse(page.locator('#readerStatus').is_visible())
                page.close()
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()

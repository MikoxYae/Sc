"""Regression tests: an adult chapter is readable after 18+ confirmation."""
import http.client
import importlib.util
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sc_core import adult_access


class SignedConfirmationTests(unittest.TestCase):
    def test_confirmation_tampering_and_expiration(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(adult_access, 'KEY_FILE', Path(temp) / 'key'):
                token = adult_access.issue(now=1_850_000_000)
                self.assertTrue(adult_access.valid(token, now=1_850_000_100))
                self.assertFalse(adult_access.valid(token + 'x', now=1_850_000_100))
                self.assertFalse(adult_access.valid(token, now=1_850_000_000 + adult_access.COOKIE_SECONDS + 1))
                self.assertTrue((Path(temp) / 'key').is_file())
                self.assertEqual((Path(temp) / 'key').stat().st_mode & 0o777, 0o600)


class AdultReaderHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.key_patch = patch.object(adult_access, 'KEY_FILE', Path(cls.temp.name) / 'secret')
        cls.key_patch.start()

        fake_catalog = types.ModuleType('catalog_db')
        fake_catalog.CATEGORIES = {'adult_manhwa': 'sc_adult_manhwa', 'manhwa': 'sc_manhwa'}
        fake_catalog.collection = lambda cat: None
        fake_catalog.public_catalog = lambda *a, **k: {'items': [], 'total': 0, 'pages': 0}
        fake_catalog.public_title = lambda *a, **k: {}
        fake_catalog.PUBLIC_TITLE_PROJECTION = {}
        fake_reader = types.ModuleType('chapter_reader')
        fake_reader.validate = lambda cat, slug, num: None
        fake_reader.prepare = lambda cat, slug, num: {'status': 'ready', 'pages': 1}
        fake_reader.chapter_record = lambda cat, slug, num: {'documents': []}
        cls.image = Path(cls.temp.name) / 'page.webp'
        cls.image.write_bytes(b'RIFF-webp-test')
        fake_reader.page_path = lambda cat, slug, num, page: cls.image
        fake_auth = types.ModuleType('web_auth')
        fake_auth.identity = lambda token: None
        fake_cover = types.ModuleType('cover_proxy')
        fake_cover.valid_cover = lambda url: False
        fake_cover.cover_bytes = lambda url: b''
        fake_errors = types.ModuleType('pymongo.errors')
        fake_errors.PyMongoError = type('PyMongoError', (Exception,), {})
        fake_errors.DuplicateKeyError = type('DuplicateKeyError', (Exception,), {})
        cls.module_patch = patch.dict(sys.modules, {
            'pymongo': types.ModuleType('pymongo'),
            'pymongo.errors': fake_errors,
            'sc_core.catalog_db': fake_catalog,
            'sc_core.chapter_reader': fake_reader,
            'sc_core.web_auth': fake_auth,
            'sc_core.cover_proxy': fake_cover,
        })
        cls.module_patch.start()
        import sc_core
        cls.core_attrs = []
        for name, module in [('catalog_db',fake_catalog), ('chapter_reader',fake_reader), ('web_auth',fake_auth), ('cover_proxy',fake_cover)]:
            pp = patch.object(sc_core, name, module, create=True)
            pp.start()
            cls.core_attrs.append(pp)
        spec = importlib.util.spec_from_file_location('sc_core.website_server_v48_test', ROOT / 'sc_core' / 'website_server.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cls.server_module = mod
        cls.env_patch = patch.dict(os.environ, {'SC_TRUST_LOCAL_PROXY': '1'})
        cls.env_patch.start()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(mod.Handler, directory=str(ROOT / 'website')))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.env_patch.stop()
        for pp in reversed(cls.core_attrs): pp.stop()
        cls.module_patch.stop()
        cls.key_patch.stop()
        cls.temp.cleanup()

    def request(self, method, path, data=None, cookie=None, secure=True, origin=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Host': 'example.org'}
        if secure:
            headers['X-Forwarded-Proto'] = 'https'
        if origin is not None:
            headers['Origin'] = origin
        if cookie:
            headers['Cookie'] = cookie
        if data is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(data)
        conn.request(method, path, body=data, headers=headers)
        response = conn.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        conn.close()
        return result

    def test_confirmation_allows_manifest_and_image(self):
        url = '/api/chapter?category=adult_manhwa&slug=test-title&chapter=1'
        page = '/api/chapter/page?category=adult_manhwa&slug=test-title&chapter=1&page=1'
        status, headers, body = self.request('GET', url)
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)['code'], 'adult_confirmation_required')
        status, _, _ = self.request('GET', page)
        self.assertEqual(status, 403)

        status, headers, body = self.request('POST', '/api/age/confirm', {'over_18': True}, origin='https://example.org')
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['confirmed'])
        cookie = headers['Set-Cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Lax', cookie)
        self.assertIn('Secure', cookie)
        status, _, body = self.request('GET', url, cookie=cookie.split(';', 1)[0])
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['status'], 'ready')
        status, _, body = self.request('GET', page, cookie=cookie.split(';', 1)[0])
        self.assertEqual(status, 200)
        self.assertEqual(body, b'RIFF-webp-test')

    def test_unconfirmed_and_cross_origin_rejected(self):
        status, _, _ = self.request('POST', '/api/age/confirm', {'over_18': False})
        self.assertEqual(status, 400)
        status, _, _ = self.request('POST', '/api/age/confirm', {'over_18': True}, origin='https://evil.example')
        self.assertEqual(status, 403)
        status, _, _ = self.request('POST', '/api/age/confirm', {'over_18': True}, secure=False)
        self.assertEqual(status, 403)
        normal = '/api/chapter?category=manhwa&slug=test-title&chapter=1'
        status, _, body = self.request('GET', normal)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['status'], 'ready')


if __name__ == '__main__':
    unittest.main()

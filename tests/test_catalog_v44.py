"""v44 regression: metadata enrichment must never crash catalog JSON or expose Telegram IDs.

Runs offline without real MongoDB, Telegram access or network permissions.
"""
import json
import sys
import types
import threading
import urllib.request
from functools import partial
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    import pymongo
except ModuleNotFoundError:
    pymongo = types.ModuleType('pymongo')
    pymongo.MongoClient = object
    pymongo.DESCENDING = -1
    errors = types.ModuleType('pymongo.errors')
    errors.PyMongoError = type('PyMongoError', (Exception,), {})
    errors.DuplicateKeyError = type('DuplicateKeyError', (errors.PyMongoError,), {})
    pymongo.errors = errors
    sys.modules['pymongo'] = pymongo
    sys.modules['pymongo.errors'] = errors

if not hasattr(pymongo.errors, 'DuplicateKeyError'):
    pymongo.errors.DuplicateKeyError = type('DuplicateKeyError', (pymongo.errors.PyMongoError,), {})

import catalog_db

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=timezone.utc)
DOC = {
    'slug': 'why-i-quit-being-the-demon-king',
    'title': 'Why I Quit Being the Demon King',
    'published': True,
    'created_at': NOW,
    'updated_at': NOW,
    'metadata_updated_at': NOW,
    'metadata_lookup': {'status': 'matched', 'attempted_at': NOW},
    'description': 'Verified metadata description',
    'cover_url': 'https://s4.anilist.co/example.jpg',
    'chapters': [{'number': '1', 'title': 'Chapter 1', 'pages': 19,
                  'telegram': {'chat_id': -100123, 'documents': [{'message_id': 100}]}},
                 {'number': '2', 'title': 'Chapter 2'}],
    'telegram': {'file_id': 'secret-file-id'},
}


class Cursor:
    def __init__(self, docs):
        self.docs = docs
    def sort(self, *args):
        return self
    def limit(self, count):
        return self
    def __iter__(self):
        return iter(self.docs)


class Collection:
    def __init__(self, docs):
        self.docs = docs
    def find(self, query, projection):
        assert projection == catalog_db.PUBLIC_TITLE_PROJECTION
        return Cursor(self.docs)
    def find_one(self, query, projection=None):
        assert projection == catalog_db.PUBLIC_TITLE_PROJECTION
        return self.docs[0] if self.docs else None


class CatalogFixTests(unittest.TestCase):
    def test_enriched_catalog_is_json_serializable_and_private_fields_removed(self):
        with patch.object(catalog_db, 'collection', return_value=Collection([DOC])):
            result = catalog_db.public_catalog('manhwa')
        self.assertEqual(result['total'], 1)
        self.assertFalse(result['partial'])
        item = result['items'][0]
        self.assertEqual(item['description'], 'Verified metadata description')
        self.assertEqual(item['created_at'], NOW.isoformat())
        self.assertEqual(len(item['chapters']), 2)
        encoded = json.dumps(result)
        for private in ('metadata_lookup', 'telegram', 'chat_id', 'file_id', 'attempted_at', 'metadata_updated_at'):
            self.assertNotIn(private, encoded)

    def test_empty_category_is_empty_not_failure(self):
        with patch.object(catalog_db, 'collection', return_value=Collection([])):
            result = catalog_db.public_catalog('manga')
        self.assertEqual(result['total'], 0)
        self.assertFalse(result['partial'])

    def test_one_unavailable_database_does_not_blank_entire_catalog(self):
        def source(cat):
            if cat == 'manga':
                raise catalog_db.PyMongoError('test failure')
            return Collection([DOC] if cat == 'manhwa' else [])
        with patch.object(catalog_db, 'collection', side_effect=source):
            result = catalog_db.public_catalog()
        self.assertTrue(result['partial'])
        self.assertIn('manga', result['unavailable_categories'])
        self.assertEqual(result['total'], 1)

    def test_all_categories_unavailable_returns_explicit_error(self):
        with patch.object(catalog_db, 'collection', side_effect=catalog_db.PyMongoError('test')):
            with self.assertRaises(RuntimeError):
                catalog_db.public_catalog()

    def test_detail_uses_safe_metadata_fields(self):
        item = catalog_db.public_title(DOC, 'manhwa')
        self.assertEqual(item['cover_url'], DOC['cover_url'])
        self.assertEqual(item['category'], 'manhwa')
        self.assertNotIn('metadata_lookup', item)
        self.assertEqual(item['chapters'][0], {'number':'1','title':'Chapter 1'})

    def test_backend_json_safe_for_nested_datetime(self):
        from website_server import _json_default
        result = json.dumps({'timestamp': NOW, 'nested': {'when': NOW}}, default=_json_default)
        self.assertEqual(json.loads(result)['timestamp'], NOW.isoformat())

    def test_real_http_catalog_and_title_responses_with_enrichment_dates(self):
        from website_server import Handler, QuietHTTPServer
        import website_server
        fake = Collection([DOC])
        server = QuietHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT/'website')))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        try:
            with patch.object(catalog_db, 'collection', return_value=fake), patch.object(website_server, 'collection', return_value=fake):
                thread.start()
                base = f'http://127.0.0.1:{server.server_port}'
                for path in ('/api/catalog?category=manhwa',
                             '/api/title?category=manhwa&slug=why-i-quit-being-the-demon-king'):
                    with self.subTest(path=path):
                        with urllib.request.urlopen(base + path, timeout=3) as response:
                            self.assertEqual(response.status, 200)
                            data = json.load(response)
                        if 'items' in data:
                            self.assertEqual(data['total'], 1)
                        else:
                            self.assertEqual(data['title'], DOC['title'])
        finally:
            server.shutdown() if thread.is_alive() else None
            server.server_close()
            thread.join(timeout=3)

    def test_website_assets_have_matching_v44_cache_tag(self):
        html = (ROOT/'website'/'index.html').read_text()
        self.assertRegex(html, r'styles\.css\?v=4[4-9]')
        self.assertRegex(html, r'app\.js\?v=4[4-9]')


if __name__ == '__main__':
    unittest.main()

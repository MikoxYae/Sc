"""Regression tests for metadata fallbacks, local cover, and public catalog."""
import importlib
import io
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# The production project requires PyMongo. Lightweight fake module allows
# these pure-function regressions to run even in the packaging environment.
try:
    import pymongo
except ImportError:
    fake = types.ModuleType('pymongo')
    fake.MongoClient = type('MongoClient', (), {})
    fake.DESCENDING = -1
    fake.errors = types.ModuleType('pymongo.errors')
    fake.errors.PyMongoError = type('PyMongoError', (Exception,), {})
    sys.modules['pymongo'] = fake
    sys.modules['pymongo.errors'] = fake.errors

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PIL import Image
from sc_core.catalog_metadata import (query_titles, select_metadata, valid_cover, compatible_type, normalize)
from sc_core.catalog_db import public_title
from sc_core import cover_proxy
from sc_core import metadata_override

class FakeEngine:
    def __init__(self): self.called = []
    def anilist(self, title):
        self.called.append(('anilist', title))
        if normalize(title) == normalize('Isegye Milf Hunter'):
            return [dict(title='Isegye Milf Hunter', type='Manhwa',
                         original_title='이세계 밀프 헌터',
                         alternative_titles=['MILF Hunting In Another World'],
                         description='A fantasy series with a different world and new adventures.',
                         cover='https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/example.jpg',
                         genres=['Fantasy'], original_language='ko',
                         sources={'anilist':42}, source_urls={'anilist':'https://anilist.co/manga/42'})]
        return []
    def mangaupdates(self,title):
        self.called.append(('mangaupdates',title)); return []
    def mangadex(self,title):
        self.called.append(('mangadex',title)); return []

class MetadataTests(unittest.TestCase):
    def test_verified_alias_fetches_correct_work(self):
        engine = FakeEngine()
        result = select_metadata('Milf Hunting In Another World Raw', 'adult_manhwa', engine)
        self.assertTrue(result['found'])
        self.assertEqual(result['values']['description'], 'A fantasy series with a different world and new adventures.')
        self.assertEqual(result['values']['metadata_match'], 'verified_alias')
        self.assertTrue(result['values']['cover_url'].startswith('https://s4.anilist.co/'))
        self.assertIn(('anilist','Isegye Milf Hunter'),engine.called)
    def test_bad_title_does_not_match(self):
        self.assertFalse(select_metadata('Completely Different Book', 'adult_manhwa', FakeEngine())['found'])
    def test_unrelated_webnovel_rejected(self):
        candidate = {'title': 'Isegye Milf Hunter', 'type': 'Other', 'original_language':'en'}
        self.assertFalse(compatible_type('adult_manhwa', candidate))
    def test_raw_trim(self):
        self.assertIn('Example',query_titles('Example RAW','manhwa'))
    def test_strict_art_hosts(self):
        self.assertFalse(valid_cover('https://127.0.0.1/private'))
        self.assertFalse(valid_cover('https://s4.anilist.co.bad.example/image.jpg'))
        self.assertTrue(valid_cover('https://s4.anilist.co/img.jpg'))
    def test_public_doc_only_exposes_cover_boolean(self):
        doc = {'title':'Sample','slug':'sample','cover_local':'adult_manhwa-sample.webp','chapters':[{'number':'1'}]}
        safe = public_title(doc,'adult_manhwa')
        self.assertEqual(safe['has_cover'],True)
        self.assertNotIn('cover_local',safe)
    def test_cover_redirect_never_leaves_allowlist(self):
        class Resp:
            is_redirect = True
            headers = {'Location':'http://127.0.0.1/secrets'}
            def close(self): pass
        class Session:
            def get(self, url, **kwargs): return Resp()
        with self.assertRaises(ValueError):
            cover_proxy.cover_bytes('https://s4.anilist.co/cover.jpg', session=Session())

    def test_owner_art_is_valid_local_webp(self):
        with TemporaryDirectory() as folder:
            previous = metadata_override.COVERS
            prev_proxy = cover_proxy.OWNER_COVERS
            metadata_override.COVERS = Path(folder)
            cover_proxy.OWNER_COVERS = Path(folder)
            try:
                image = Path(folder)/'test.jpg'
                Image.new('RGB',(120,200)).save(image)
                name=metadata_override.convert_cover(image,'adult_manhwa-sample.webp')
                self.assertEqual(name,'adult_manhwa-sample.webp')
                self.assertTrue(cover_proxy.owner_cover_bytes(name))
                with self.assertRaises(ValueError): cover_proxy.owner_cover_bytes('../secret.webp')
            finally:
                metadata_override.COVERS = previous
                cover_proxy.OWNER_COVERS = prev_proxy

if __name__=='__main__': unittest.main()

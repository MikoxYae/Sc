"""Offline regression tests: no network, MongoDB, or Telegram account required."""
import sys
import unittest
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import pymongo
except ImportError:
    fake=types.ModuleType('pymongo')
    fake.MongoClient=object
    fake.DESCENDING=-1
    fake.errors=types.ModuleType('pymongo.errors')
    fake.errors.PyMongoError=type('PyMongoError',(Exception,),{})
    sys.modules['pymongo']=fake
    sys.modules['pymongo.errors']=fake.errors

from catalog_metadata import valid_cover, exact_match, select_metadata, enrich_published_title


def item(title='Why I Quit Being the Demon King', provider='anilist', **kwargs):
    base={'title':title,'type':'Manhwa','cover':'https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/test.jpg',
          'description':'A fantasy about a demon lord leaving his throne.',
          'original_title':'마왕을 그만둔 이유', 'genres':['Fantasy'],'authors':['A. Writer'],
          'alternative_titles':[], 'sources':{provider:3}, 'source_urls':{provider:'https://example.org'}}
    base.update(kwargs)
    return base


class FakeEngine:
    def __init__(self, al=None, mu=None, md=None):
        self.al=al if al is not None else [item()]
        self.mu=mu if mu is not None else []
        self.md=md if md is not None else []
    def anilist(self, title):return self.al
    def mangaupdates(self, title):return self.mu
    def mangadex(self, title):return self.md


class Changes:
    def __init__(self, modified=1):self.modified_count=modified


class FakeCollection:
    def __init__(self):
        self.doc={'slug':'why-i-quit-being-the-demon-king',
                  'title':'Why I Quit Being the Demon King','published':True,
                  'chapters':[{'number':'1','telegram':{'chat_id':-100123,'documents':[{'message_id':222}]}}],
                  'updated_at':'old-upload-time'}
    def find_one(self, query):return self.doc.copy()
    def update_one(self, query, changes):
        assert set(changes) == {'$set'}
        self.doc.update(changes['$set'])
        return Changes()

class MetadataV43Tests(unittest.TestCase):
    def test_safe_cover_host(self):
        self.assertTrue(valid_cover('https://s4.anilist.co/file/anilistcdn/image.jpg'))
        self.assertTrue(valid_cover('https://uploads.mangadex.org/covers/id/image.jpg'))
        self.assertFalse(valid_cover('http://127.0.0.1/file.png'))
        self.assertFalse(valid_cover('https://s4.anilist.co.attacker.org/a.jpg'))
        self.assertFalse(valid_cover('file:///etc/passwd'))

    def test_exact_match_not_fuzzy(self):
        self.assertTrue(exact_match('WHY I QUIT BEING THE DEMON KING',item()))
        self.assertFalse(exact_match('Why I Quit Being the Demon Queen',item()))

    def test_merge_missing_cover_from_related_provider(self):
        primary=item(cover=None)
        fallback=item(provider='mangadex',cover='https://uploads.mangadex.org/covers/id/a.png',
                      authors=['B Writer'],description='another synopsis')
        result=select_metadata('Why I Quit Being the Demon King','manhwa',FakeEngine([primary],md=[fallback]))
        self.assertTrue(result['found'])
        self.assertEqual(result['values']['cover_url'],fallback['cover'])
        self.assertEqual(result['values']['description'],primary['description'])
        self.assertEqual(result['values']['metadata_field_sources']['cover_url'],'mangadex')

    def test_wrong_category_or_name_not_published(self):
        wrong_type=item(type='Manga')
        self.assertFalse(select_metadata('Why I Quit Being the Demon King','manhwa',FakeEngine([wrong_type]))['found'])
        self.assertFalse(select_metadata('Why I Quit Being the Demon King','manhwa',FakeEngine([item(title='Wrong Story')]))['found'])

    def test_identical_titles_ambiguous(self):
        first=item(sources={'anilist':1})
        second=item(sources={'anilist':2})
        res=select_metadata('Why I Quit Being the Demon King','manhwa',FakeEngine([first,second]))
        self.assertFalse(res['found'])
        self.assertIn('Ambiguous',res['reason'])

    def test_published_pdf_preserved(self):
        c=FakeCollection()
        original=c.doc['chapters']
        res=enrich_published_title('manhwa','why-i-quit-being-the-demon-king',engine=FakeEngine(),col=c)
        self.assertEqual(res['status'],'matched')
        self.assertEqual(c.doc['chapters'],original)
        self.assertEqual(c.doc['updated_at'],'old-upload-time')
        self.assertTrue(c.doc['cover_url'].startswith('https://s4.anilist.co'))
        self.assertEqual(c.doc['metadata_lookup']['status'],'matched')

    def test_owner_curated_fields_not_overwritten(self):
        c=FakeCollection()
        c.doc['description']='Verified by owner'
        enrich_published_title('manhwa','why-i-quit-being-the-demon-king',engine=FakeEngine(),col=c)
        self.assertEqual(c.doc['description'],'Verified by owner')

    def test_unmatched_title_keeps_no_fake_cover(self):
        c=FakeCollection()
        res=enrich_published_title('manhwa','why-i-quit-being-the-demon-king',engine=FakeEngine(al=[]),col=c)
        self.assertEqual(res['status'],'needs_review')
        self.assertNotIn('cover_url',c.doc)

    def test_frontend_connects_cover_and_description(self):
        js=(Path(__file__).parents[1]/'website'/'app.js').read_text()
        self.assertIn('x.cover_url',js)
        self.assertIn('x.description',js)
        self.assertIn('story-synopsis',js)
        self.assertIn('/api/cover?category=',js)

if __name__=='__main__':unittest.main()

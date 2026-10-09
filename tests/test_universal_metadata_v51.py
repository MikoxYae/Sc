"""Category-aware poster/synopsis fallback smoke tests (offline)."""
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sc_core.metadata_engine import MetadataEngine, normalize
from sc_core.catalog_metadata import MATCHED_TYPES, query_titles, select_metadata

class FakeEngine:
    def __init__(self):
        self.calls = []
    def anilist(self, value):
        self.calls.append(('anilist', value))
        return []
    def mangaupdates(self, value):
        self.calls.append(('mangaupdates', value))
        return []
    def mangadex(self, value, *, include_adult=False):
        self.calls.append(('mangadex', value, include_adult))
        return [dict(title='Braid of Snow', type='Manhwa', original_language='ko',
                     description='A published story about a traveling painter and winter mountains.',
                     cover='https://uploads.mangadex.org/covers/some-uuid/cover.jpg',
                     alternative_titles=[], sources={'mangadex':'uuid-123'})]

class UniversalMetadataTests(unittest.TestCase):
    def test_mangadex_ratings_by_category(self):
        class Engine(MetadataEngine):
            def request(self, provider, method, url, **kw):
                self.last = kw['params']; return {'data': []}
        engine = Engine()
        engine.mangadex('story', include_adult=True)
        self.assertIn('pornographic', engine.last['contentRating[]'])
        engine.mangadex('story', include_adult=False)
        self.assertNotIn('pornographic', engine.last['contentRating[]'])
    def test_every_category_accepted(self):
        self.assertEqual(set(MATCHED_TYPES), {
            'manga','manhwa','manhua','webtoon',
            'adult_manga','adult_manhwa','adult_webtoon'
        })
        for cat in MATCHED_TYPES:
            found = select_metadata('Braid of Snow', cat, FakeEngine())
            # The verified type must be compatible; never attach unrelated work.
            self.assertEqual(found['found'], cat in {'manhwa','adult_manhwa','webtoon','adult_webtoon'})
    def test_manual_search_title_is_queried_first(self):
        names = query_titles('Milf Hunting in Another World Raw', 'adult_manhwa',
                             extra_titles=['Owner Verified Alternative'])
        self.assertEqual(names[0], 'Owner Verified Alternative')
    def test_adult_category_explicit_rating(self):
        engine = FakeEngine()
        result = select_metadata('Braid of Snow', 'adult_manhwa', engine)
        self.assertTrue(result['found'])
        self.assertIn(('mangadex','Braid of Snow', True), engine.calls)
    def test_all_categories_use_owner_search_titles(self):
        for cat in MATCHED_TYPES:
            names = query_titles('Alternate Raw', cat, extra_titles=['Confirmed Title'])
            self.assertIn('Confirmed Title', names)
            self.assertIn('Alternate', names)
    def test_hardcoded_provider_matches_not_fuzzy(self):
        result = select_metadata('Random Different Novel', 'adult_manhwa', FakeEngine())
        self.assertFalse(result['found'])

if __name__ == '__main__': unittest.main()

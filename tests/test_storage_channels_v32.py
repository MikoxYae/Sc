"""Regression checks for one Mongo URI and category-specific Telegram channels."""
import ast
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class StorageChannelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot = (ROOT / 'Miko.py').read_text(encoding='utf-8')
        cls.catalog = (ROOT / 'catalog_db.py').read_text(encoding='utf-8')

    def test_syntax(self):
        ast.parse(self.bot)
        ast.parse(self.catalog)

    def test_all_seven_channel_options(self):
        for category in ('manga','manhwa','manhua','webtoon','adult_manga','adult_manhwa','adult_webtoon'):
            self.assertIn("'channel_" + category + "'", self.bot)

    def test_per_category_publish(self):
        self.assertIn("DATA.get('storage_channels', {}).get(category)", self.bot)
        self.assertIn("DATA.setdefault('storage_channels', {})[category] = cid", self.bot)

    def test_no_category_db_editor(self):
        self.assertNotIn('CATEGORY_DB_KB', self.bot)
        self.assertNotIn("'storage_dbs'", self.bot)
        self.assertNotIn("'db_manga'", self.bot)
        self.assertNotIn("'SC_MONGO_'+category.upper()+'_URI'", self.catalog)

if __name__ == '__main__':
    unittest.main()

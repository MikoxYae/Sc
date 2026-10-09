import unittest
from catalog_db import CATEGORIES,CATEGORY_LABELS
from Miko import category_picker,category_label
class TestCategories(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(len(CATEGORIES),7)
        self.assertEqual(category_label('adult_webtoon'),'18+ Webtoon')
    def test_picker(self):
        rows=category_picker().inline_keyboard
        self.assertTrue(all(len(row)<=2 for row in rows))
        self.assertEqual(sum(len(row) for row in rows),8)
if __name__=='__main__':unittest.main()

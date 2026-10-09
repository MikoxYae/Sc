import unittest

try:
    from catalog_db import CATEGORIES, CATEGORY_LABELS
    from Miko import category_picker, category_label
    _missing_dependency = None
except ModuleNotFoundError as exc:
    _missing_dependency = exc.name


@unittest.skipIf(_missing_dependency is not None, 'Optional dependency not installed: ' + str(_missing_dependency))
class TestCategories(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(len(CATEGORIES), 7)
        self.assertEqual(category_label('adult_webtoon'), '18+ Webtoon')

    def test_picker(self):
        rows = category_picker().inline_keyboard
        self.assertTrue(all(len(row) <= 2 for row in rows))
        self.assertEqual(sum(len(row) for row in rows), 8)


if __name__ == '__main__':
    unittest.main()

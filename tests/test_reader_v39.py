"""Reader cache and image rendering tests without Telegram network access."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if 'catalog_db' not in sys.modules:
    try:
        import catalog_db
    except ImportError:
        sys.modules['catalog_db'] = types.SimpleNamespace(CATEGORIES={'manga': 'sc_manga'}, collection=lambda _: None)
import chapter_reader


class ReaderTests(unittest.TestCase):
    def test_rejects_invalid_identifiers(self):
        for slug in ('../private', 'a/b', ''):
            with self.assertRaises(ValueError):
                chapter_reader.validate('manga', slug, '1')

    def test_render_pdf_pages_in_order(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as temp:
            original = chapter_reader.CACHE
            chapter_reader.CACHE = Path(temp)
            async def fake_download(telegram, target):
                doc = pymupdf.open()
                for i in range(3):
                    page = doc.new_page(width=420, height=750)
                    page.insert_text((25, 35), f'Page {i+1}')
                doc.save(target / 'part_001.pdf')
                doc.close()
            try:
                with patch.object(chapter_reader, '_download_parts', fake_download):
                    chapter_reader._build('a' * 64, {'documents': [{'message_id': 1}]})
                folder = Path(temp) / ('a' * 64)
                self.assertEqual(chapter_reader._manifest(folder)['pages'], 3)
                self.assertTrue((folder / '0002.webp').is_file())
                self.assertFalse((folder / 'part_001.pdf').exists())
            finally:
                chapter_reader.CACHE = original


if __name__ == '__main__':
    unittest.main()

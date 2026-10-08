import unittest
from site_adapters import discover_mangadass, extract_number, is_mangadass
from sc import parse_chapter

class MangaDassTests(unittest.TestCase):
    def test_discovery(self):
        html = '''<a href="/manga/soul-land-iv-the-ultimate-combat/chapter-1">Chapter 1</a>
        <a href="/manga/soul-land-iv-the-ultimate-combat/chapter-575.5">Chapter 575.5</a>
        <a href="/manga/other/chapter-4">Chapter 4</a>'''
        links = discover_mangadass(html, 'https://mangadass.com/manga/soul-land-iv-the-ultimate-combat')
        self.assertEqual(set(links), {'1','575.5'})
    def test_reader(self):
        title, imgs = parse_chapter('<h1>Chapter 1</h1><div class="reading-content"><img data-src="/a.jpg"></div>', 'https://mangadass.com/manga/test/chapter-1')
        self.assertEqual(imgs, ['https://mangadass.com/a.jpg'])
    def test_number(self):
        self.assertEqual(extract_number('https://mangadass.com/manga/test/chapter-575.5'), '575.5')
        self.assertTrue(is_mangadass('https://mangadass.com/manga/test'))
if __name__ == '__main__': unittest.main()

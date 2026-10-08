import unittest
from sc import parse_chapter, safe_url


class ScraperTests(unittest.TestCase):
    def test_order_and_dedupe(self):
        html = '<h1>Chapter 1</h1><div class="reading-content"><img data-src="/1.jpg"><img src="/2.png"><img src="/1.jpg"></div>'
        title, images = parse_chapter(html, 'https://example.org/chapter')
        self.assertEqual(title, 'Chapter 1')
        self.assertEqual(images, ['https://example.org/1.jpg', 'https://example.org/2.png'])

    def test_private_ip_rejected(self):
        with self.assertRaises(ValueError):
            safe_url('http://127.0.0.1/secret')


if __name__ == '__main__':
    unittest.main()

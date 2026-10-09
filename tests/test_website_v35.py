"""Website baseline checks that continue working across CSS/JS releases."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WebsiteBaselineTests(unittest.TestCase):
    def test_health_route(self):
        self.assertIn("u.path=='/api/health'", (ROOT/'website_server.py').read_text())

    def test_no_legacy_readmes(self):
        self.assertFalse(list(ROOT.glob('README_V*.md')))

    def test_website_assets(self):
        html = (ROOT/'website/index.html').read_text()
        js = re.search(r'app\.js\?v=(\d+)', html)
        css = re.search(r'styles\.css\?v=(\d+)', html)
        self.assertIsNotNone(js)
        self.assertIsNotNone(css)
        self.assertEqual(js.group(1), css.group(1))

    def test_secret_not_bundled(self):
        self.assertFalse((ROOT/'config.py').exists())


if __name__ == '__main__':
    unittest.main()

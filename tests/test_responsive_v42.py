"""Sc v42 responsive layout regression tests.

Browser checks are optional for environments without Playwright/Chromium.
They use in-memory HTML and fake chapter API responses: no server,
Telegram account, MongoDB account, or API credentials are needed.
"""
import re
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'website'


class ResponsiveSourceTests(unittest.TestCase):
    def test_cache_versions(self):
        html = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn('width=device-width, initial-scale=1, viewport-fit=cover', html)
        self.assertRegex(html, r'styles\.css\?v=4[2-9]')
        self.assertRegex(html, r'app\.js\?v=4[2-9]')

    def test_layout_rules_present(self):
        css = (ROOT / 'styles.css').read_text(encoding='utf-8')
        self.assertIn('max-width: 1199px', css)
        self.assertIn('body.reader-mode .reader-images img', css)
        self.assertIn('body.reader-mode .ambient', css)
        self.assertIn('object-fit: contain', css)


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright and shutil.which('chromium'), 'Optional Chromium/Playwright not installed')
class BrowserResponsiveTests(unittest.TestCase):
    def test_viewport_and_reader_full_width(self):
        html = (ROOT / 'index.html').read_text(encoding='utf-8')
        css = (ROOT / 'styles.css').read_text(encoding='utf-8')
        js = (ROOT / 'app.js').read_text(encoding='utf-8')
        html = re.sub(r'<link[^>]+>', '', html)
        html = re.sub(r'<script src="app.js[^>]+></script>', '', html)
        html = html.replace('</head>', '<style>' + css + '</style></head>')

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, executable_path=shutil.which('chromium'), args=['--no-sandbox']
            )
            try:
                for width in (360, 390, 760, 980, 1440):
                    for route in ('#/', '#/read/manhwa/sample/1'):
                        with self.subTest(width=width, route=route):
                            page = browser.new_page(viewport={'width': width, 'height': 840})
                            try:
                                page.set_content(html)
                                page.evaluate('''() => {
                                  window.fetch = async (url) => ({ok:true,status:200,
                                    json:async()=>String(url).includes('chapter?')
                                      ? {status:'ready',pages:2}
                                      : {items:[],pages:1,total:0,user:null}});
                                }''')
                                page.evaluate('(url)=>{location.hash=url}', route)
                                page.add_script_tag(content=js)
                                page.wait_for_function("document.body.classList.contains('reader-mode') === " +
                                                       ('true' if route.startswith('#/read/') else 'false'))
                                widths = page.evaluate('''() => ({
                                  client:document.documentElement.clientWidth,
                                  scroll:document.documentElement.scrollWidth,
                                  reader:document.querySelector('.reader-shell')?.getBoundingClientRect().width,
                                  mode:document.body.classList.contains('reader-mode')
                                })''')
                                self.assertEqual(widths['client'], width)
                                self.assertEqual(widths['scroll'], width)
                                if widths['mode']:
                                    self.assertAlmostEqual(widths['reader'], width, delta=1)
                            finally:
                                page.close()
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()

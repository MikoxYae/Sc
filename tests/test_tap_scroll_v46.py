"""The v46 manga reader tap zones in a local, mocked browser (no credentials)."""
import re
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'website'


class ReaderTapSourceTests(unittest.TestCase):
    def test_reader_only_and_controls(self):
        source = (ROOT / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function bindReaderTapScroll(container)', source)
        self.assertIn("bindReaderTapScroll($('readerPages'))", source)
        self.assertIn('right?-distance:distance', source)
        self.assertIn('pointercancel', source)
        self.assertIn('reader-tap-hint', source)

    def test_cache_bust_and_no_dependency_change(self):
        html = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn('styles.css?v=46', html)
        self.assertIn('app.js?v=46', html)


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright and shutil.which('chromium'), 'Optional Chromium/Playwright unavailable')
class BrowserReaderTapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / 'index.html').read_text(encoding='utf-8')
        css = (ROOT / 'styles.css').read_text(encoding='utf-8')
        cls.js = (ROOT / 'app.js').read_text(encoding='utf-8')
        cls.html = re.sub(r'<link[^>]+>', '', cls.html)
        cls.html = re.sub(r'<script src="app.js[^>]+></script>', '', cls.html)
        cls.html = cls.html.replace('</head>', '<style>' + css + '</style></head>')
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            headless=True, executable_path=shutil.which('chromium'), args=['--no-sandbox']
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def prepare(self, mobile=False):
        ctx = self.browser.new_context(
            viewport={'width': 390, 'height': 740}, is_mobile=mobile, has_touch=mobile,
            reduced_motion='reduce', device_scale_factor=1
        )
        page = ctx.new_page()
        page.set_content(self.html)
        page.evaluate('''() => {
          window.fetch = async (url) => ({ok:true,status:200,json:async()=>
            String(url).includes('chapter?') ? {status:'ready',pages:6} :
            {items:[],pages:1,total:0,user:null}});
          location.hash='#/read/manhwa/sample/1';
        }''')
        page.add_script_tag(content=self.js)
        page.wait_for_function("document.querySelectorAll('#readerPages img').length === 6")
        page.evaluate('''async () => {
          const art='<svg xmlns="http://www.w3.org/2000/svg" width="390" height="1000"><rect width="390" height="1000" fill="black"/></svg>';
          const url='data:image/svg+xml;base64,'+btoa(art);
          const imgs=Array.from(document.querySelectorAll('#readerPages img'));
          await Promise.all(imgs.map(img => new Promise(resolve => {
            img.onload=resolve;img.onerror=resolve;img.src=url;
          })));
        }''')
        page.evaluate('window.scrollTo({top:700,behavior:"instant"})')
        return ctx,page

    def test_desktop_left_down_right_up_and_drag_ignored(self):
        context,page=self.prepare()
        try:
            at=lambda: page.evaluate('window.scrollY')
            start=at()
            page.mouse.click(60,430)
            page.wait_for_timeout(200)
            after_left=at()
            self.assertGreater(after_left, start+200, (start,after_left))
            page.mouse.click(335,430)
            page.wait_for_timeout(200)
            after_right=at()
            self.assertLess(after_right,after_left-200,(after_left,after_right))
            page.mouse.move(60,430)
            page.mouse.down()
            page.mouse.move(135,440,steps=6)
            page.mouse.up()
            page.wait_for_timeout(120)
            self.assertAlmostEqual(at(),after_right,delta=15)
        finally:
            context.close()

    def test_phone_taps_and_toolbar_link(self):
        context,page=self.prepare(mobile=True)
        try:
            get_y=lambda: page.evaluate('window.scrollY')
            start=get_y()
            page.touchscreen.tap(50,410)
            page.wait_for_timeout(230)
            after_left=get_y()
            self.assertGreater(after_left,start+200)
            page.touchscreen.tap(340,410)
            page.wait_for_timeout(230)
            self.assertLess(get_y(),after_left-200)
            # The back link still navigates normally, instead of scrolling.
            page.locator('.reader-toolbar a').click()
            page.wait_for_function("!document.body.classList.contains('reader-mode')")
            self.assertIn('#/title/manhwa/sample',page.evaluate('location.hash'))
        finally:
            context.close()


if __name__ == '__main__':
    unittest.main()

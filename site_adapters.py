"""Website-specific discovery helpers; no authentication or access-control bypass."""
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

SUPPORTED_HOSTS = ('mangadass.com', 'www.mangadass.com')
CHAPTER_PATTERN = re.compile(r'(?:chapter|chap|ch)[\s._/-]*(\d+(?:\.\d+)?)', re.I)

def is_mangadass(url):
    return (urlparse(url).hostname or '').lower() in SUPPORTED_HOSTS

def extract_number(url, label=''):
    path = urlparse(url).path
    for candidate in (path.split('/')[-1], path, label):
        match = CHAPTER_PATTERN.search(candidate)
        if match:
            return match.group(1)
    return None

def discover_mangadass(html, base):
    """Discover actual links; never invent URLs for absent chapters."""
    soup = BeautifulSoup(html, 'html.parser')
    chapters = {}
    parsed_base = urlparse(base)
    manga_slug = parsed_base.path.rstrip('/').split('/')[-1].lower()
    for anchor in soup.select('a[href]'):
        target = urljoin(base, anchor.get('href', ''))
        parsed = urlparse(target)
        if parsed.hostname != parsed_base.hostname or parsed.scheme not in ('http', 'https'):
            continue
        label = anchor.get_text(' ', strip=True)
        number = extract_number(target, label)
        if not number:
            continue
        # Restrict links to this manga, allowing chapter links nested beneath its landing page.
        if manga_slug not in parsed.path.lower() and manga_slug not in (anchor.get('data-manga') or '').lower():
            continue
        chapters.setdefault(number, target)
    return chapters

MANGADASS_READER_SELECTORS = (
    '.reading-content img', '.chapter-content img', '.reader-area img',
    '.chapter-reader img', '.wp-manga-chapter-img',
    '.reading-area img', '.page-break img', '#chapter-content img',
)

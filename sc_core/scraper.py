"""Sc: extract permitted public chapter images and assemble a PDF."""
import argparse
import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, UnidentifiedImageError
from reportlab.pdfgen import canvas
from .site_adapters import is_mangadass, MANGADASS_READER_SELECTORS

HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36', 'Accept': 'text/html,application/xhtml+xml,image/avif,image/webp,image/*;q=0.9,*/*;q=0.8'}
IMAGE_ATTRS = ('data-src', 'data-lazy-src', 'data-original', 'data-url', 'data-cfsrc', 'data-lazy', 'src')
SELECTORS = ('.reading-content img', '.chapter-content img', '.entry-content img', '.page-break img', '.chapter-images img', '.wp-manga-chapter-img', '#chapter-content img', '.chapter-reader img', '.reader-area img', '.reading-area img')


def safe_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname:
        raise ValueError('Provide a valid http(s) URL')
    host = parsed.hostname.lower()
    if host in ('localhost',) or host.endswith(('.local', '.internal')):
        raise ValueError('Local addresses are not supported')
    import ipaddress
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return url
    if not addr.is_global:
        raise ValueError('Private or reserved IP addresses are not supported')
    return url


def fetch(session, url, timeout=25):
    safe_url(url)
    r = session.get(url, timeout=timeout, allow_redirects=False)
    for _ in range(5):
        if r.status_code not in (301, 302, 303, 307, 308):
            break
        dest = r.headers.get('Location')
        if not dest:
            break
        url = safe_url(urljoin(url, dest))
        r = session.get(url, timeout=timeout, allow_redirects=False)
    r.raise_for_status()
    if r.status_code in (301, 302, 303, 307, 308):
        raise RuntimeError('Too many redirects')
    return r


def parse_chapter(html, base):
    soup = BeautifulSoup(html, 'html.parser')
    title = (soup.select_one('h1') or soup.select_one('title'))
    title = title.get_text(' ', strip=True) if title else 'Chapter'
    candidates = []
    selectors = MANGADASS_READER_SELECTORS + SELECTORS if is_mangadass(base) else SELECTORS
    for selector in selectors:
        found = soup.select(selector)
        if found:
            candidates = found
            break
    if not candidates:
        candidates = soup.select('img')
    urls = []
    for img in candidates:
        raw = next((img.get(k) for k in IMAGE_ATTRS if img.get(k) and not str(img.get(k)).startswith(('data:', 'blob:')) and str(img.get(k)).strip() not in ('#', 'about:blank')), None)
        if not raw:
            continue
        # srcset fallback for lazy-loaded images
        raw = str(raw).strip().split()[0]
        u = urljoin(base, raw)
        try:
            safe_url(u)
        except ValueError:
            continue
        if u not in urls:
            urls.append(u)
    return title, urls


def make_pdf(images, path):
    pdf = canvas.Canvas(str(path), pageCompression=1)
    count = 0
    for img_path in images:
        with Image.open(img_path) as original:
            im = ImageOps.exif_transpose(original).convert('RGB')
            width, height = im.size
            if not width or not height:
                continue
            # Preserve image aspect ratio and dimensions (PDF points).
            scale = min(1, 14400 / max(width, height))
            width, height = width * scale, height * scale
            pdf.setPageSize((width, height))
            pdf.drawImage(str(img_path), 0, 0, width=width, height=height)
            pdf.showPage()
            count += 1
    if not count:
        raise ValueError('No valid images to add to PDF')
    pdf.save()
    return count


def run(url, output, delay, max_pages, dry_run):
    safe_url(url)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    session.headers['Referer'] = url
    response = fetch(session, url)
    if 'html' not in response.headers.get('content-type', '').lower():
        raise RuntimeError('URL did not return HTML')
    title, urls = parse_chapter(response.text, response.url)
    print(f'Title: {title}\nImage references: {len(urls)}', flush=True)
    (output / 'metadata.json').write_text(json.dumps({'title': title, 'source': response.url, 'image_urls': urls}, indent=2), encoding='utf-8')
    if not urls:
        raise RuntimeError('No image references found in chapter HTML. The website may load images with JavaScript or restrict access.')
    if dry_run:
        print('Dry run complete. Image URLs saved to metadata.json')
        return
    folder = output / 'images'
    folder.mkdir(exist_ok=True)
    downloaded = []
    for index, image_url in enumerate(urls[:max_pages], 1):
        try:
            print(f'Downloading page {index}/{min(len(urls), max_pages)}', flush=True)
            r = fetch(session, image_url)
            if not r.headers.get('content-type', '').lower().startswith('image/'):
                print(f'Skip {index}: not an image')
                continue
            if len(r.content) > 30 * 1024 * 1024:
                print(f'Skip {index}: image exceeds 30 MB')
                continue
            with Image.open(io.BytesIO(r.content)) as image:
                image.verify()
            # Preserve original JPEG/PNG bytes. No lossy quality reduction or resizing.
            with Image.open(io.BytesIO(r.content)) as image:
                fmt = image.format
                if fmt == 'JPEG':
                    path = folder / f'{index:04d}.jpg'
                    path.write_bytes(r.content)
                elif fmt == 'PNG':
                    path = folder / f'{index:04d}.png'
                    path.write_bytes(r.content)
                else:
                    # PDF renderer requires a supported raster format.
                    # Convert other formats to lossless PNG without resizing.
                    path = folder / f'{index:04d}.png'
                    image.convert('RGB').save(path, format='PNG')
            print(f'Saved original page {index}: {path.stat().st_size / 1048576:.2f} MB', flush=True)
            downloaded.append(path)
            print(f'[{index}/{min(len(urls), max_pages)}] Saved {path.name}', flush=True)
        except (requests.RequestException, UnidentifiedImageError, OSError, ValueError, RuntimeError) as exc:
            print(f'Skip {index}: {exc}', flush=True)
        if delay and index < min(len(urls), max_pages):
            time.sleep(delay)
    if not downloaded:
        raise RuntimeError('No images downloaded. The site may require JS, authentication, or use different HTML selectors.')
    pdf_path = output / 'chapter.pdf'
    print('Building PDF...', flush=True)
    pages = make_pdf(downloaded, pdf_path)
    print(f'PDF ready: {pdf_path} ({pages} pages)')


def main():
    p = argparse.ArgumentParser(description='Sc - chapter webpage images to PDF (permitted sources only)')
    p.add_argument('url', nargs='?', help='Chapter URL')
    p.add_argument('-o', '--output', default='output', help='Output folder')
    p.add_argument('--delay', type=float, default=1.0, help='Seconds between image requests')
    p.add_argument('--max-pages', type=int, default=250, help='Maximum images to fetch')
    p.add_argument('--dry-run', action='store_true', help='Extract metadata only')
    args = p.parse_args()
    url = args.url or input('Paste chapter URL: ').strip()
    if args.max_pages < 1 or args.delay < 0:
        p.error('max-pages must be positive and delay nonnegative')
    try:
        run(url, args.output, args.delay, args.max_pages, args.dry_run)
    except (ValueError, RuntimeError, requests.RequestException) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

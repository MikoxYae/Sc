# Reader v53: faster first page and progressive loading

## What's improved

- **Newly published chapters:** after the PDF is delivered and published to MongoDB, the bot stages the original downloaded chapter images from the temporary scraper folder into a disposable reader cache. A background worker converts each to WebP. The website can serve page 1 immediately when it is prepared and add page 2, 3, etc. while the rest are prepared. No extra Telegram posts or MongoDB PDF/image storage.
- **Multipart chapters:** older chapters split into multiple PDFs can display pages from part 1 while subsequent PDF parts are still being downloaded. Each WebP is written atomically to avoid partially loaded images.
- **Previously published single-PDF chapters:** the first reader request **still must download the whole PDF** because ordinary PDFs are not reliably readable from partial bytes. Rendering becomes progressively visible page by page *after* that download; the 72-hour VPS cache makes subsequent reads faster.
- **Optional manual warm-up for older chapters:** `.venv/bin/python3 reader_prefetch.py --category manhwa --slug example-title --chapter 1` prepares that chapter's reader cache before visitors click. Use an actual published category/slug/chapter.
- **UX:** early pages show without waiting for later conversions; progress compacts and the browser updates more frequently until the first pages appear. Mobile reader scrolling and tap mapping (LEFT=UP / RIGHT=DOWN) remain unchanged.

## Files

- `chapter_reader.py` contains background cache seeding, atomic WebP publication and per-PDF-part progressive rendering.
- `Miko.py` stages original page images after successful Telegram + MongoDB publishing; failure to cache is **nonfatal** for the existing upload workflow.
- `website/app.js`, `website/styles.css`, `website/index.html` include progressive page UI + fresh cache-busting asset versions.
- `reader_prefetch.py` optionally prepares one older chapter.

## Deploy

Upload ZIP into `/root/`, then from VPS:

```sh
cd /root && unzip -o Sc-Bot-Website-Progressive-Reader-v53.zip -d /root
cd /root/Sc && systemctl restart sc-miko.service
```

Do not run `python3 miko.py` concurrently with the systemd service. Existing `config.py`, `.venv`, `data/` and Caddy setup are not included in the ZIP and should remain unchanged.

## Limitations & operations

- Full first-page readiness for **already-stored single-PDF documents before download ends is not supported**. A PDF requires its structural cross-reference information. True byte-level per-page downloads would require separately stored page images or a different storage format.
- The cache is disposable, local to this VPS, and subject to `SC_READER_CACHE_HOURS` (default 72). After a cache miss, old single PDFs need downloading again.
- Very large image sets beyond configured cache limits skip pre-warming; PDF fallback still works.
- Readers require a valid accessible storage channel and Telegram credentials; the 18+ confirmation flow stays enforced.
- If visitors are already on a page during an update, refresh it to load JS version 53.

## Diagnostics

```sh
curl -fsS http://127.0.0.1:1276/api/health
journalctl -u sc-miko.service -n 80 --no-pager | grep -Ei 'Reader|WEBSITE PUBLISHED|timeout|error'
```

## Testing

`python3 -m pytest -q tests/test_reader_v49.py tests/test_reader_v53.py` (pytest required only for testing).

# Sc Telegram Bot + MIKO Manga Website

Start both services using `python3 miko.py` (lowercase). The Telegram bot uses long polling; the website listens on port 1276. Production deployment uses `bash deploy/setup_vps.sh` to run the application with systemd and serve it through Caddy HTTPS.

The application preserves its original manga scraper, PDF conversion, Telegram channel storage, and MongoDB metadata features. Do not commit `config.py`, `.env`, session data, or credentials. Configure Telegram and MongoDB values privately on the VPS.

## VPS installation / upgrade

Upload the ZIP into `/root/` and run:

```sh
cd /root && unzip -o Sc-Bot-Website-Reader-Connection-v45.zip -d /root && cd /root/Sc && systemctl restart sc-miko.service
```

This reuses the existing virtual environment and dependencies. Only install requirements if the environment is new or missing packages. The setup does not install Docker, kill other bots, or alter unrelated Docker containers. The Caddy config is backed up before changes.

**Canonical website URL:** `https://<public-ip>.sslip.io/` (normally HTTPS port 443). `http://<public-ip>:1276/` redirects to HTTPS; this is not a second unsecured login site. HTTPS requires working DNS and open inbound ports 80 and 443. If the browser still fails while the VPS returns HTTP 200, the hosting provider firewall or the mobile ISP/DNS path must be checked; no ZIP can guarantee access through an externally blocked network.

## Troubleshooting

```sh
cd /root/Sc && bash deploy/check_access.sh
```

Do not run a second manual `python3 miko.py` while `sc-miko.service` is active; it will conflict with the port and Telegram polling. Use `systemctl restart sc-miko.service` to restart. Details: `deploy/README.md`.

## Testing

Run `python3 -m unittest discover -s tests` with the existing project dependencies installed. Some integration tests require MongoDB and network access. No live production deployment is asserted by this package.

## v42: responsive layout and manga reader

The fullscreen manga reader now fills the available viewport in Chrome mobile and desktop layouts, keeping the PDF-to-image panels in order without distortion. The landing page and category grids no longer expand the document beyond the device width. The tablet-width navigation changes to a compact menu when the desktop navigation cannot fit.

**Root cause fixed:** the decorative 900px-wide `.ambient` layer extended a 390px mobile document to almost 1000px, causing mobile Chrome to shrink or offset the reader into a narrow strip. Viewport-aware containment and a full-width reader address this without modifying server, database, Telegram, or Caddy settings.

To update an existing VPS (upload ZIP to `/root/` first):

```sh
cd /root && unzip -o Sc-Bot-Website-Responsive-v42.zip -d /root && cd /root/Sc && systemctl restart sc-miko.service
```

If you run the application manually instead of systemd, stop the service first and execute `source .venv/bin/activate && python3 miko.py`. Do not run two instances.

The website stays at its existing HTTPS URL; port `1276` is the localhost backend. No package installation, virtual environment recreation, or DNS changes are needed for v42. CSS and JS asset references are versioned `?v=42` to bypass stale styles. On Chrome Android, use normal mobile mode for normal-sized typography; Desktop site mode can still make text appear smaller because the browser forces its own desktop viewport/zoom.

### Responsive smoke test

`python3 -m unittest discover -s tests -p 'test_responsive_v42.py' -v`

The optional browser test requires Playwright and Chromium **only in the development/test environment**. It tests 360, 390, 760, 980 and 1440 CSS-pixel viewports, on homepage and reader, without any live API credentials.


## v43: Automatic verified cover artwork and synopsis

The website reads descriptive fields from the same published MongoDB title records
that hold chapter references. The Telegram storage channels continue to contain
PDFs. **No PDF/image binary content is put in MongoDB.**

### Backfill existing published titles (one-time)

Run on your VPS inside `/root/Sc` after activating the existing `.venv`:

```sh
python3 metadata_sync.py --all --force
```

For a single existing title:

```sh
python3 metadata_sync.py --category manhwa --slug why-i-quit-being-the-demon-king --force
```

Then restart the service or refresh the website. No additional Python requirements
are needed if v42's requirements have already been installed.

### Newly uploaded titles

Following successful PDF upload to the category Telegram channel and catalog
record creation, a background worker enriches the published title automatically.
The PDF delivery does **not wait** for metadata providers. Metadata lookups are
rate-limited by the engine and cached: matched entries are refreshed at most
once in 14 days, missing/failed lookups at most once in 12 hours. Refresh can be
forced using the CLI command above. The original title, chapter list, channel
message IDs and publish timestamps are never overwritten during enrichment.

### Matching and provider policy

Only titles with an **exact normalized title or listed alias** and a compatible
content category are automatically eligible. Duplicate exact-title matches in a
single source or missing matches are marked `needs_review` rather than guessed.
Results are tried from AniList, MangaUpdates and MangaDex using the existing
metadata adapter. They are merged only if title and available original-work
identifiers do not conflict. Provider-specific source IDs and provenance are
stored. Existing owner-curated fields remain unchanged.

The frontend displays verified `cover_url`, `description`, `genres`, `status` and creators
whenever verified metadata is available. If no approved provider provides a
match, the site retains its neutral placeholder and displays "Synopsis not
available from verified metadata sources yet". **Do not fabricate a poster or
synopsis or assume an unrelated title is the correct series.** Provider APIs
may be unavailable, rate-limited or have incomplete catalogs. Images must
originate from allowed HTTPS artwork endpoints. The backend serves approved
cover images as small, same-origin WebP thumbnails, optionally cached on disk
for up to 24 hours (never in MongoDB), respecting upstream no-store headers. Follow each provider's current
image usage and caching policies before publicly deploying the site.

### Troubleshooting

```sh
python3 metadata_sync.py --category manhwa --slug why-i-quit-being-the-demon-king --force
journalctl -u sc-miko.service -n 60 --no-pager
```

The backfill prints `matched`, `needs_review`, `skipped` or `failed` without
printing MongoDB credentials. Check that the MongoDB URI and VPS outbound HTTPS
access for metadata provider APIs are working. The old 1276 backend port, Caddy,
registration, Telegram controls and PDF reader are unchanged by v43.

## v44: Published catalog reliability after metadata sync

v43 introduced MongoDB `metadata_lookup.attempted_at` and
`metadata_updated_at` datetime fields. The older catalog API passed entire
records into the JSON response while only converting `created_at` and
`updated_at`, resulting in an unhandled `TypeError: Object of type datetime
is not JSON serializable`. Chrome showed **Catalog temporarily unavailable**.

v44 returns explicit public metadata fields only, excluding all Telegram channel
IDs/document references, internal MongoDB IDs and metadata lookup state. Nested
metadata timestamps are no longer included; any public date fields serialize as
ISO 8601. The catalog now reuses a bounded MongoDB connection pool, so opening
multiple categories no longer repeatedly creates new MongoDB clients. If one
category database is temporarily unavailable, the main feed shows available
stories with a clear partial-availability warning; a failed single-category
request returns HTTP 503 so users don't mistake it for an empty category.

**The Manga category showing 0 stories is normal if only a Manhwa was
published.** A Manga upload will appear in the Manga category when published.

### Deploy (no Python dependency changes)

Upload `Sc-Bot-Website-Catalog-Fixed-v44.zip` to `/root` on the VPS, then:

```sh
cd /root && unzip -o Sc-Bot-Website-Catalog-Fixed-v44.zip -d /root && cd /root/Sc && systemctl restart sc-miko.service
```

Wait a few seconds for startup and check:

```sh
curl -fsS 'http://127.0.0.1:1276/api/catalog?category=manhwa'
journalctl -u sc-miko.service -n 40 --no-pager
```

Use the public Caddy HTTPS hostname to view the website. No PDF files or MongoDB
records need to be deleted, and metadata backfill does **not** need to run again.
This patch does not change storage channel mappings, Telegram publishing, or the
reader cache. If a metadata provider could not verify a title, artwork and
synopsis will remain unavailable until a valid metadata match is found.

Local validation: `python3 -m unittest discover -s tests` (optional extras may be
skipped when unavailable). No live VPS/MongoDB/provider access was used to test
this patch.

## v45: Resilient Chapter Reader (interrupted connection / Chapter 20)

The reader previously **stopped immediately** and left an empty reading page if
one `/api/chapter` fetch failed (e.g., a transient mobile connection drop, an
upstream proxy error, or an unexpected server-side exception). The API could
also close a connection without JSON when chapter storage references were
malformed. These issues could display `Connection failed` instead of a useful
error.

v45 introduces **bounded retry** for reader GET requests (never retries
login/signup POSTs), a visible `Retry chapter` action, retry-once for
individual page images, and server-side JSON error responses for unexpected
reader errors. The HTTP accept queue is larger for bursts of page-image
requests. PDF conversion is limited to one background job at a time to avoid
competing CPU/memory spikes. Malformed Telegram storage references now report
a controlled error instead of causing an uncaught exception. Existing chapter
IDs, Telegram file storage, MongoDB metadata and cached pages are untouched.

### Update an existing VPS

The ZIP contains **no `config.py` or MongoDB secrets**. Upload it to `/root/`
and run:

```bash
cd /root && unzip -o Sc-Bot-Website-Reader-Connection-v45.zip -d /root && cd /root/Sc && systemctl restart sc-miko.service
```

No new packages or virtual environment are required. Wait a few seconds after
restart; then refresh the chapter reader in mobile Chrome. Check the website
health locally via `curl -fsS http://127.0.0.1:1276/api/health`.

For the Chapter 20 issue, if the error continues, inspect **redacted** reader
logs (avoid exposing bot tokens):

```bash
journalctl -u sc-miko.service --no-pager -n 100 | grep -E 'Reader|reader|Chapter|chapter|Unexpected'
```

If the response says a PDF is missing or storage references are incomplete,
check the configured storage channel and that the specified chapter was
actually published; a browser fix cannot reconstruct absent Telegram files.
No change to Caddy, firewall, MongoDB collections or user credentials is made.

### Local tests

`python3 -m unittest discover -s tests -v` (full suite). Regression cases in
`tests/test_reader_v45.py` simulate failed browser requests and malformed
backend chapter records without using private user data. The code has not been
deployed to the user's live VPS; real Telegram chapter retrieval requires a
post-update check.


## v46: Tap-to-scroll on the manga reader

The manga reader supports one-tap navigation when chapter images are loaded:

- Tap the **left half of a manga image** to scroll **down** roughly 72% of the visible screen.
- Tap the **right half of a manga image** to scroll **up** by the same amount.
- Normal finger swipes, mouse-wheel scrolling, and pinch zoom continue working.
- Long presses and drag gestures do not trigger the tap navigation. The chapter header and Back to Chapters links are unaffected.
- The reader displays a small instruction hint; other pages have no tap-navigation behavior.

### Deploy on an existing VPS

Upload `Sc-Bot-Website-Tap-Scroll-v46.zip` to `/root/`, then:

```sh
cd /root && unzip -o Sc-Bot-Website-Tap-Scroll-v46.zip -d /root && cd /root/Sc && systemctl restart sc-miko.service
```

No Python dependency changes, new virtual environment, MongoDB migration,
Caddy changes, or channel reconfiguration are required. The existing
`config.py`, `.venv`, and `data/` are not contained in this update.

Regression test: `python3 -m unittest discover -s tests -p 'test_tap_scroll_v46.py' -v`.

## v47: Storage-to-website publishing recovery

Adult-category uploads are published only after copying the complete PDF into
that category's Telegram storage channel **and** saving the chapter reference
in MongoDB. Completion messages explicitly report website-publishing status.
For diagnostics and restoration of previously uploaded channel PDFs, see
[docs/PUBLISHING_RECOVERY.md](docs/PUBLISHING_RECOVERY.md).

Check a category:

```sh
.venv/bin/python3 publication_check.py --category adult_manhwa
```

Dry run a repair, then apply it to the selected storage channel:

```sh
.venv/bin/python3 storage_sync.py --category adult_manhwa
.venv/bin/python3 storage_sync.py --category adult_manhwa --apply
```

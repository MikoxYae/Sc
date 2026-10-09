# Sc v39 — Telegram-backed vertical chapter reader

When a published chapter is selected, the website loads `/api/chapter`, which resolves the existing MongoDB Telegram references and queues a background preparation job. Pyrofork retrieves the PDF document(s) using the bot account, and PyMuPDF renders every page to an ordered WebP image. The frontend polls until ready and displays all pages in a continuous scroll. **PDF bytes are never stored in MongoDB.**

## Setup

Requires the existing private `config.py` with `API_ID`, `API_HASH`, `BOT_TOKEN`, `MONGO_URI`; the bot must remain in each storage channel. `pip install -r requirements.txt` is required once for the two newly added libraries. Keep the existing Caddy -> `127.0.0.1:1276` deployment; run `bash deploy/setup_vps.sh` to update the service.

The first visit to a chapter may take time while Telegram downloads and PDF conversion complete. Subsequent visits reuse disk cache. Configuration: `SC_READER_CACHE`, `SC_READER_CACHE_HOURS` (default 72), `SC_READER_MAX_PAGES` (default 600), `SC_READER_MAX_MB` (default 400). Run a periodic cache cleanup or delete `data/reader_cache` to reclaim space; only cached copies are removed, not Telegram originals.

## Limitations

- The bot needs access to the original Telegram channel post. MTProto retrieval may fail if API credentials are invalid or the bot has been removed from the channel.
- The current reader restricts adult-category chapter endpoints pending an age-verification flow.
- PDFs larger than configured limits return a visible error; there is no automatic quality degradation or compression of source PDFs.
- Rendered pages are cached locally on the VPS. This is not a CDN; monitor disk usage for heavy traffic.
- Website catalog entries must already be published with valid channel references; uploading a PDF privately without a saved MongoDB reference does not publish it.

## Testing

Run `python -m unittest discover -s tests` after dependencies are installed. Check `/api/health`, then click a published non-adult chapter and wait for images. Test repeat visits (cache), missing chapters, and bot access removal.

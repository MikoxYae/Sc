# MIKO Reader v49 — Faster PDF retrieval and progressive pages

## Launch

`python3 miko.py` starts the Telegram polling bot and website together. On VPS, the existing `sc-miko.service` manages that launcher. The website listens on `127.0.0.1:1276`, proxied through the existing Caddy HTTPS configuration.

## How chapters load

1. Read the chapter's category-specific MongoDB document references (no PDF bytes are stored in MongoDB).
2. If a Bot API `file_id` is present and Telegram permits `getFile`, download PDFs under the cloud Bot API 20 MB limit directly over HTTPS.
3. Otherwise, fetch the storage-channel message through Pyrofork's MTProto bot client (requires correct API_ID, API_HASH, BOT_TOKEN and access to the configured storage channel).
4. Transfer timeouts now consider progress and file size rather than rejecting *all* PDFs after 120 seconds.
5. PDF pages render as WebP and become readable one by one; the browser shows loading stage and page count while later pages are prepared.
6. Cache keys include the Telegram post IDs, so re-publishing a chapter invalidates its old cache. Reader cache stays on the VPS (`data/reader_cache`), not MongoDB.

## Setup/update

Upload `Sc-Bot-Website-Fast-Reader-v49.zip` to `/root/`, then:

```sh
cd /root && unzip -o Sc-Bot-Website-Fast-Reader-v49.zip -d /root
cd /root/Sc && systemctl restart sc-miko.service
```

Optional MTProto acceleration for PDFs larger than Telegram cloud Bot API's download limit:

```sh
cd /root/Sc && .venv/bin/python3 -m pip install tgcrypto-pyrofork
```

This is optional; if installation fails, Pyrofork still works without the C extension, albeit potentially slower.

## Diagnostics

```sh
curl -fsS http://127.0.0.1:1276/api/health
journalctl -u sc-miko.service -n 80 --no-pager | grep -Ei 'Reader|error|timeout|stalled'
```

The chapter `/api/chapter?...` response reports `status` (`processing`, `ready`, `error`), `stage`, `pages_ready`, and `pages_total`. The page endpoint can serve pages while the render is still processing. No public API response contains the Telegram bot token.

**Note:** HTTP 200 from the website does not prove the VPS can reach Telegram MTProto or access the storage channel. If MTProto is blocked by the hosting network, the bot is not an administrator of the configured channel, or the document message was deleted, a download may still fail. Inspect the Reader logs on the VPS. Avoid posting raw Telegram HTTP logs, which may include the bot token.

## Tuning (optional environment variables)

- `SC_READER_WORKERS=2`: simultaneous chapter preparation workers (1–2 recommended on a loaded VPS).
- `SC_READER_STALL_TIMEOUT=90`: stop a transfer if no download progress for this many seconds.
- `SC_READER_PART_TIMEOUT=180`: minimum part deadline; larger PDFs receive longer proportional deadlines.
- `SC_READER_IMAGE_WIDTH=1200`: render width bound for mobile, preserving page aspect ratio.
- `SC_READER_IMAGE_QUALITY=83`: WebP quality (65–95).
- `SC_READER_CACHE_HOURS=72`: number of hours rendered pages are retained.

To apply environment variables in systemd, use a drop-in configuration, `systemctl daemon-reload` and `systemctl restart sc-miko.service`. Do not edit secrets into source files.

## Testing

```sh
cd /root/Sc && .venv/bin/python3 -m pytest -q tests/test_reader_v49.py
```

Optional for environments without pytest: `python3 -m compileall -q sc_core/chapter_reader.py sc_core/website_server.py sc_core/bot.py` and `curl -fsS http://127.0.0.1:1276/api/health`.

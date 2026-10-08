# Sc — Telegram Manga-to-PDF Bot (v7)

Run `python Miko.py`. Existing image extraction, JPEG optimization, PDF splitting, `/status`, `/cancel` and chapter URL processing are preserved.

## Commands

- `/start`: welcome card, optional saved start picture, inline navigation.
- `/settings`: private settings menu for owner and admins. Admin management and picture configuration are owner-only.
- `/status`, `/cancel`: available to owner and admins.
- Send a permitted public chapter URL: create optimized PDF.

## Admin management

`/settings` → Admin → Add Admin → send numeric user ID in private chat. The bot attempts to delete the submitted ID message and returns to the admin menu. Remove Admin shows one button per ID; List Admins shows saved IDs. Owner cannot be removed. Admins can operate the bot but cannot manage admins or change pictures.

## Pictures

`/settings` → Pictures → Start Picture or Settings Picture → send Telegram photo. Both pictures can be identical via Use Same Picture. If no picture has been provided yet, the bot uses a text-only menu. The bot attempts to delete submitted photo messages and automatically returns to the picture menu. Telegram requires permission to delete messages; in a private chat it generally can delete incoming messages.

## Storage

Admin IDs and Telegram photo file IDs are saved atomically to `data/settings.json` and survive restarts. No MongoDB dependency is required. `config.py` remains local and is never packaged or overwritten. Keep `data/settings.json` when upgrading.

## Install / run

Existing VPS installation: `cd /root/Sc && . .venv/bin/activate && python Miko.py`

For updates upload the ZIP to `/root/`, stop old process, then extract over `/root/Sc`. No requirements changes in v5.

## Security

Never commit bot token, API hash or MongoDB password. Rotate previously shared test credentials. Only process content you have permission to access.

## Automatic Telegram Menu commands (v7)

On every successful startup the bot calls Telegram `setMyCommands`, so the Menu button lists `/start`, `/settings`, `/status`, `/cancel`, and `/help` automatically. No manual BotFather command configuration is needed. Telegram may take a moment to refresh the command list; reopen the chat if needed. This is a command *menu*, not permission enforcement: the existing handlers still restrict privileged actions to the owner/admins. The menu registration requires Telegram API access on startup.

## v7 UI changes

- All menu button labels and menu text are emoji-free.
- Telegram HTML `<b>` is used for bold headings, with `<blockquote>` for instructions.
- Telegram does not support choosing arbitrary custom fonts for bot messages; native Telegram formatting is used instead.
- No more than two buttons per row. All existing admin, picture, PDF and command-menu features remain.
- Existing config.py and data/settings.json are not included and are not overwritten.
- No dependency changes; reuse the existing virtual environment.

## v9 - Small caps Telegram UI

All user-facing menu headings, instructions, button labels, command descriptions, progress messages, and common errors use the requested Unicode small-caps style (example: `ᴛʜɪs ɪs ᴍʏ ғᴀᴠ ғᴏɴᴛ`). Headings retain Telegram HTML bold and instructions retain blockquotes. Telegram does not have small-cap equivalents for every Latin character, so a few characters use their nearest available glyph. IDs, URLs, callback identifiers, and command names remain unchanged.

No new dependencies. Existing `config.py`, `data/settings.json`, and `.venv` remain intact.

## v10: Telegram HTML formatting fix

- All HTML formatting tags remain standard HTML (`<b>`, `<blockquote>`, `<code>`).
- Only visible text and button labels use Unicode small caps.
- `/status` now sends its card with `parse_mode='HTML'` so tags render rather than appearing literally.
- Callback alerts are plain text because Telegram callback alerts do not parse HTML.
- No new dependencies. Preserve your existing local `config.py` and `data/settings.json` when updating.

## v11: Chapter processing and PDF options

- `/settings` -> **PDF Options**: set **PDF Picture** (a photo preview sent before the document), **Rename Format** (filename template), and **Caption Style** (Bold / Underline / Spoiler / Plain).
- Filename placeholders: `{title}` and `{chapter}`. Example: `{title} - Chapter {chapter}` produces `Manga Title - Chapter 1.pdf`. Formatting tags cannot style a filename; styles apply to the Telegram document **caption**.
- When a chapter URL is submitted, a single progress message updates approximately every 12 seconds with the current stage, page count and elapsed time. Telegram flood-control may defer some edits; errors are logged.
- Scraping remains sequential with the existing configurable per-image delay; it does not bypass authentication or anti-bot measures.
- The PDF picture is uploaded as a JPEG `thumbnail` in `sendDocument`, not as a separate photo. The bot resizes it to at most 320x320 and below 200 KB. Telegram clients may choose whether to display custom PDF thumbnails; the Bot API does not guarantee presentation.
- Existing `config.py`, `.venv` and saved `data/settings.json` are intentionally excluded from release ZIPs. No new dependencies.
- Note: chapter title and chapter number are derived from URL path. Sites with unusual URL patterns may need site-specific metadata parsing.
- Existing cancellation and PDF splitting remain available. `/cancel` terminates the scraper subprocess; PDF splitting/upload may finish if cancellation is requested at that stage.

Update on VPS after uploading ZIP to `/root` and stopping the previous process:

```bash
cd /root && unzip -o Sc-Telegram-Bot-Fixed-v11.zip -d /root && cd /root/Sc && source .venv/bin/activate && python Miko.py
```


## v12 chapter progress
The progress message shows manga title, chapter, active stage, page count, elapsed time and a Cancel Download inline button. It edits the same message approximately every 12 seconds. The title is initially derived from the URL and may be updated using the page title. Cancellation stops the scraper subprocess; already uploaded files cannot be recalled. Telegram upload is not interruptible by this button once upload has started.


## v13 completion display
The processing message becomes a single bold completion summary with title, chapter, page count, PDF part count, total size, and elapsed time. Each PDF is sent as a document without an additional preview-photo message.

## v14: Manga page -> chapter range

Send a manga landing URL such as `https://example.org/manga/example-series/` in a private chat. The bot discovers links to chapters present in the page's HTML and shows the number of chapters and a paginated list (25 per page). Select **Select Range** and send `1-20`. The bot processes chapters sequentially and uploads each PDF immediately, preserving your existing filename template, document thumbnail, and caption style. The existing single-chapter URL workflow still works.

- A maximum of 100 integer chapters per range is supported. Missing chapter numbers are reported, not guessed. Decimal chapters can appear in discovery, but are not currently selectable with the integer-range input.
- Discovery only sees chapter links available in server-rendered HTML. JavaScript-only chapter lists, logins, and blocked websites require a separate authorized adapter. No chapter count is fabricated.
- Only owner/admin users can request chapters. Admin access is controlled through the existing settings.
- `/cancel` and the Cancel Download callback request cancellation of the current subprocess and stop subsequent chapters. The Telegram client may finish an upload already underway.
- The completion message summarizes counts, pages, bytes, and elapsed time. If any chapter is missing or failed, a separate short issue report is sent.
- Existing `config.py`, `data/settings.json`, and `.venv` are deliberately not included in this archive and are preserved when unpacking.
- Live website and Telegram behavior has not been verified. Test with a permitted public manga series first.


## v15 update

- The chapter range prompt is edited into the batch progress message; no extra batch-start message is sent during normal operation.
- The batch completion summary has grouped fields and human-readable elapsed time.
- Original JPEG and PNG page bytes are retained, with no lossy recompression or resizing. Other formats convert to lossless PNG for PDF compatibility. PDF assembly may still increase file size.
- Existing PDF splitting and Telegram thumbnail/caption settings remain available.
- Reuse the existing `.venv`; dependencies are unchanged.

## v16 - Failed chapter recovery

- Each failed chapter is retried up to three times with short backoff.
- The final batch message lists failed chapter numbers and error details when available.
- `Retry Failed` processes only the failed chapters from the latest batch in the same bot session.
- The summary is edited in place; no separate chapter-issues message is sent.
- The retry list is in memory and is lost after bot restart.
- A network failure during Telegram upload can be ambiguous: check whether a PDF was delivered before retrying to avoid duplicates.
- No new Python dependencies; keep your existing `.venv` and `config.py`.

## MangaDass adapter (v17)

MangaDass landing pages are supported by a dedicated chapter-link discovery adapter.
Send `https://mangadass.com/manga/soul-land-iv-the-ultimate-combat` to the bot,
then choose a chapter range. Only chapter links found in the public HTML are
included; decimal chapter numbers are preserved. Reader image detection uses
site-specific selectors with the existing generic fallback. Existing PDF
naming, thumbnail, sequential delivery, retry and cancellation remain intact.

**Limitations:** Live MangaDass access was not verified in this build. If the
site loads chapter links or images only via JavaScript, requires authentication,
or blocks automated access, discovery/extraction may fail. The bot does not
bypass these restrictions. Use only for material you are authorized to download.

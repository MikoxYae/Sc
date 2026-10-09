# Sc v47 — adult-category publishing and recovery

The Telegram bot and website still run together via `python3 miko.py` or the
existing `sc-miko.service`. No Python dependencies or port configuration changed.

## Root causes addressed

- The bot previously treated a privately delivered PDF as a successful batch
  even when **18+ Manhwa** had no configured Telegram storage channel. A
  category is published only when the channel copy and MongoDB write succeed.
- Database failures after Telegram delivery formerly triggered retries and
  could create duplicate PDFs. Completed Telegram references are now preserved
  in private `data/publish_pending.json`, and these cases cannot be retried by
  re-uploading the PDF from the batch's Retry button.
- An interrupted multi-part upload is not published as an incomplete chapter.
- Missing or failed metadata-provider results do not undo a successfully
  stored chapter. Missing metadata cannot by itself hide a published title.

## Existing uploads — check and recover without re-upload

Run from `/root/Sc`, with the existing virtual environment:

```
.venv/bin/python3 publication_check.py --category adult_manhwa
.venv/bin/python3 storage_sync.py --category adult_manhwa
.venv/bin/python3 storage_sync.py --category adult_manhwa --apply
```

The second command prints a dry-run and the third commits verified complete
Telegram document references into the **adult_manhwa** catalog. They do not
store PDFs in MongoDB or download them to the VPS. Matching is deliberately
strict: `Story Title - Chapter 1.pdf` (or `- Ch 1.pdf`). Unknown rename
formats, incomplete multipart uploads and conflicting copies are skipped.

**Limitations:** Telegram MTProto channel-history access requires appropriate
bot administrator permissions and a working `API_ID`, `API_HASH`, and
`BOT_TOKEN`. If the server cannot read the channel history, no files are
modified. If the Telegram file was only delivered privately, and never copied
into the configured category channel, there is nothing to recover via channel
history; that chapter must be uploaded again after setting the channel.

## Upload flow

`/settings` > Storage > Channel ID > **18+ Manhwa** > paste the channel ID.
The bot must be an administrator in that channel. Ensure MongoDB is configured.
When submitting a source URL select **18+ Manhwa**, not **Manhwa**.
Successful final messages now explicitly say whether a chapter was **Website:
Published** or **Website: Not published**; the batch summary also counts
website-published chapters. Published content is stored under `sc_adult_manhwa`
and appears under the corresponding website category. Category misclassification
is not automatically corrected.

## Security and content restrictions

`config.py`, MongoDB secrets, `data/`, and the pending journal remain private
and are excluded from the release ZIP. Never share the real token/URI in logs.
This patch does not bypass the existing adult-reader restriction: adult chapter
images still require a separate age-eligibility implementation before being
made readable publicly. Only publish material you have rights to distribute.

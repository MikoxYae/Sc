# Sc v30 - Content category selection

After sending a URL, choose Manga, Manhwa, Manhua, Webtoon, 18+ Manga, 18+ Manhwa, or 18+ Webtoon. The selected category is stored in the Telegram conversation until processing completes. Existing chapter discovery and sequential PDF delivery remain.

When a storage channel is configured and the bot has administrator permission, completed PDF documents are copied to that channel, then chapter references are recorded in the selected MongoDB category database. If storage is not configured, the PDF is delivered privately only; it is not published on the website.

**Note:** The title is currently derived from the source URL. Verify titles and permissions before publication. The website's chapter reader and age-verification gate are not implemented yet; do not expose adult sections publicly without proper age controls. MongoDB publishing is not transactional with Telegram, so a failed database write may require reconciliation.

Existing auth, HTTPS, configuration and bot functions are unchanged. `python3 miko.py` starts bot and website.

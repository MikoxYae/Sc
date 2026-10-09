# Sc v32 - Per-category Telegram storage channels

## Storage configuration

One MongoDB URI is shared by all categories. MongoDB uses distinct logical databases (`sc_manga`, `sc_manhwa`, `sc_manhua`, `sc_webtoon`, `sc_adult_manga`, `sc_adult_manhwa`, `sc_adult_webtoon`) on the same connection. The old per-category MongoDB URI editor was removed from the Telegram menu and from the catalog URI resolver.

Open `/settings` > `Storage` > `Channel ID`, then choose Manga, Manhwa, Manhua, Webtoon, 18+ Manga, 18+ Manhwa, or 18+ Webtoon. Send the destination private channel ID in the bot's private chat. The `-100` prefix can be omitted. The bot checks its channel administrator membership before saving the ID. Each category has an independent channel ID in `data/settings.json`.

`Check Connection` checks every configured channel and the one MongoDB connection. No new Python dependencies are required.

When a chapter is processed, the selected content category determines the destination channel. The PDF is sent to the requester; when that category has a configured channel, the bot copies the document to that channel and stores the post reference in its category's MongoDB database. If the channel isn't configured, the PDF remains in the private chat and is **not published**. This release does not migrate previously stored documents or backfill old channel IDs.

## Deploying

Keep the existing private `config.py`, `.venv`, `data/`, and TLS/deployment configuration. Extract the update ZIP over `/root/Sc`. If using the existing `sc-miko.service`, restart that service; otherwise use `python3 miko.py` with your existing environment. Do not run two bot polling instances at once.

## Validation

`python3 -m unittest discover -s tests -p test_storage_channels_v32.py -v`

Live Telegram channel-admin verification and MongoDB publishing still require VPS testing.

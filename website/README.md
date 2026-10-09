# MIKO Manga Website

Production website for the Sc Telegram Bot repository. `python3 miko.py`
starts the bot and Python website backend together. Caddy serves the public
HTTPS domain while the backend binds to `127.0.0.1:1276`.

## Reader

Published chapter PDF references are stored in MongoDB; PDF documents live in
private Telegram storage channels. The VPS downloads and converts pages to
WebP for vertically scrolling mobile and desktop reading. Left tap scrolls
down, right tap scrolls up; normal swipe scrolling still works.

18+ chapters now use a working adult self-confirmation screen instead of an
unimplemented permanent 403. Select **I am 18+ — Continue** once per browser
(confirmation expires after 30 days). The confirmation is not independent
age verification, and may not meet requirements in all jurisdictions.

## Deployment

See `../README.md` and `../deploy/README.md` for setup, HTTPS, configuration,
and troubleshooting. Do not run a separate static-only server for production;
API routes and private chapter retrieval need the Python backend. Keep
`config.py`, session and MongoDB secrets outside the public website folder.

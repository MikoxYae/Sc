# Sc v24 - Metadata Review

## Features

- `/metadata` (owner-only) searches AniList GraphQL, MangaUpdates REST and MangaDex REST.
- Select a candidate to review title, source, description, author, genres, publication status and chapter count.
- Save selected metadata as an **unpublished draft** in MongoDB `sc_metadata.drafts`.
- `/settings` -> Metadata -> My Drafts: delete unwanted metadata drafts after confirmation.
- Drafts do not create fake manga listings and do not publish without authorized chapter content.
- Every provider candidate stays separate. No fuzzy auto-merge across providers. This avoids wrong-title uploads.
- Search errors are reported when a provider is unavailable. Provider API access and catalog completeness may vary.
- Existing bot, PDF, website, storage settings, and authentication remain in place.

## Owner account

The owner email is reserved: `musicstudios756@gmail.com`. It does not automatically grant access based on unverified email registration. Once MongoDB is configured, run `python owner_setup.py` on the VPS and choose a private password. Existing sessions for that email will be revoked. Website registration/login still requires HTTPS.

## Provider notes

AniList: GraphQL public read API, 30/minute temporary degraded rate noted in official docs; this client throttles requests and honors Retry-After.
MangaUpdates: REST search endpoint; availability and access conditions must be verified in production.
MangaDex: public REST; verify acceptable-use terms, attribution, and non-commercial restrictions before use on public website.
MyAnimeList: requires a developer client ID; not activated in this release.
Anime-Planet, ComicK, WEBTOON: no unauthorized scraping or undocumented API integration.

## Scope and limitations

This release is **metadata search, manual verification, drafts, and draft removal**. It does not automatically associate a draft with Telegram PDFs, publish a manga to the website, or implement an authenticated web admin dashboard. Those need a separate reviewed publishing workflow. Live provider responses and live Telegram callbacks have not been validated on the user's VPS.

## Testing

Run `python -m unittest discover -s tests` and `python -m compileall -q Miko.py metadata_engine.py owner_setup.py web_auth.py`.

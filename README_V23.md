# Sc v23 - Published Catalog and Accounts

This is an incremental upgrade of the existing Sc repository. Start both services with `python Miko.py`. Website port: 1980.

## Features
- Removes fictional catalog entries. Only MongoDB records with `published: true` and nonempty `chapters` are shown. Empty catalog is intentional until authorized content is published.
- 10 titles per page, two-column mobile cards, newest `updated_at` first, `NEW` badge for 24 hours.
- Separate MongoDB databases (`sc_manga`, `sc_manhwa`, `sc_webtoon`, `sc_adult`) with optional independent URIs configured in Telegram Storage > Category DBs. If no category URI is set, the shared MongoDB URI is used.
- Reader registration/login/profile using PBKDF2-hashed passwords and MongoDB sessions. HTTPS is required for public login; set `SC_HTTPS=1` ONLY behind a correctly configured HTTPS reverse proxy.
- Owner admin email is NOT configured until provided. After owner email verification, set `SC_OWNER_EMAIL` privately in server environment. Never expose owner credentials to JS. Admin publishing dashboard is not yet implemented.

## Published catalog document example

Database: `sc_manhwa`, collection: `titles`

```json
{"slug":"example-title","title":"Example Title","description":"Example synopsis","cover_url":"https://your-authorized-cdn.example/cover.jpg","published":true,"updated_at":"2026-10-09T00:00:00Z","chapters":[{"number":"1","title":"Chapter 1"}]}
```

In MongoDB use a BSON Date for `updated_at` for correct date sorting. `slug` must be unique within its category.

**Not yet implemented:** automatic Telegram PDF publishing, Telegram-to-reader PDF streaming, storage rollover when MongoDB fills, real admin dashboard, and actual chapter reader. These require additional implementation and should not be considered active. MongoDB Atlas storage capacity cannot be assumed automatically detectable for safe rollover.

## Security
- Never commit `config.py`, `data/*.env`, or `data/settings.json`.
- Rotate previously exposed bot tokens and MongoDB credentials.
- Use HTTPS before allowing public registration.
- The existing bot must be channel admin to use the storage channel; this update does not publish files there yet.

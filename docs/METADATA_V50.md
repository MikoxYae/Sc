# MIKO catalog metadata and poster management (v50)

## What changed

When upload titles use editorial variants such as `Raw`, the metadata lookup now
tries normalized titles. For the specifically verified Manhwa title
`Milf Hunting In Another World Raw`, its alternate title
`Isegye Milf Hunter` (`이세계 밀프 헌터`) is tried before guessing any result.
The script uses **metadata APIs**, not arbitrary scraping. The public catalog
still only shows published titles and chapters stored via Telegram+MongoDB.

Other series never inherit metadata merely because their names look similar.
Descriptions are not fabricated. If the APIs are unreachable, or no precise
matching record has synopsis/cover, the site retains a placeholder and an
operator can provide the accurate information below.

## Enrich uploaded series

```bash
cd /root/Sc
.venv/bin/python3 miko.py metadata-sync --category adult_manhwa --slug milf-hunting-in-another-world-raw --force
```

Output statuses:

- `matched`: provider information found; list of updated fields printed.
- `needs_review`: the metadata APIs did not return a verifiable match.
- `failed`: API/database/processing error; view application logs.
- `missing`: the specified slug/category has no published record.

Check the same exact series in `/api/title?category=adult_manhwa&slug=...`.
Cover images are served by `/api/cover?category=adult_manhwa&slug=...`.
The upstream APIs can refuse requests or forbid cover reuse; never scrape
protected sites or use poster assets without appropriate rights.

## Owner-provided cover/synopsis when providers are incomplete

Copy a cover image you have permission to use to your VPS, and prepare a
text file with an accurate synopsis. Both stay local (not included in ZIPs).

```bash
cd /root/Sc
.venv/bin/python3 miko.py metadata-override --category adult_manhwa \
  --slug milf-hunting-in-another-world-raw \
  --cover-file /root/approved-poster.jpg \
  --synopsis-file /root/approved-synopsis.txt
```

Or add only a caption description with `--synopsis "A verified summary of..."`.
Alternatively set a permitted AniList/MangaDex/MangaUpdates cover URL using
`--cover-url https://...`, which is validated against a safe allowlist.

These operations modify **only an already published series**. They do not
change Telegram documents, chapter lists, file IDs, channels, login or
website ports. Local images are converted into WebP in
`data/cover_uploads/` and are never stored in MongoDB; only their names are.

## Troubleshooting

If API metadata fetch returns `needs_review`, check that the exact manhwa
appears in an official provider API; do not substitute a similarly named
novel. If cover is absent despite a matching record, run:

```bash
curl -sS -o /dev/null -w 'Cover: %{http_code}\n' 'http://127.0.0.1:1276/api/cover?category=adult_manhwa&slug=milf-hunting-in-another-world-raw'
```

- `200`: poster is being served; refresh the browser once.
- `404`: no cover URL or approved owner-uploaded image on the published record.
- `502`: provider image could not be fetched by the VPS.
- `503`: MongoDB access issue; check the service logs.

Run `journalctl -u sc-miko.service -n 50 --no-pager` with any credentials
redacted before sharing logs.

## Copyright and use

Metadata and images remain subject to the providers' usage and license rules.
Only upload images or synopsis text you have permission to publish. Do not
assume that availability in a search API grants chapter redistribution rights.

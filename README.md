# Sc Telegram Bot + MIKO Manga Website

Run Telegram polling and the manga website together with **one entry point**:

```bash
cd /root/Sc
source .venv/bin/activate
python3 miko.py
```

**On a VPS with `sc-miko.service`, use `systemctl restart sc-miko.service` instead of launching a second instance.**
The website listens on localhost port **1276**; existing Caddy terminates HTTPS.

## Repository layout

```text
Sc/
├── miko.py                 # Only application launcher at repository root
├── requirements.txt        # Python runtime dependencies
├── README.md
├── .gitignore
├── sc_core/                # Internal Python package: bot, scraper, reader, API, MongoDB, metadata
├── website/                # HTML, JS, CSS (kept outside Python package)
├── deploy/                 # systemd/Caddy helpers and safe v54 migration
├── docs/                   # Further documentation
└── tests/                  # Tests; no private credentials
```

**Private VPS files remain at** `/root/Sc/config.py`, `/root/Sc/data/`, and `/root/Sc/.venv/`. Do not commit credentials. `config.example.py`, `semico.py`, and the old root-level Python modules are retired.

## Deploy this structural update (v54)

Upload the v54 ZIP to `/root/`, then:

```bash
cd /root && unzip -o Sc-Bot-Website-Organized-v54.zip -d /root && cd /root/Sc && bash deploy/migrate_v54.sh
```

The migration script checks the new package before removing only the named obsolete root files; it preserves `config.py`, `.venv`, `data`, Caddy, and other projects, and restarts only `sc-miko.service`.

## Maintenance through the SAME command

```bash
python3 miko.py metadata-sync --all --force
python3 miko.py metadata-override --help
python3 miko.py reader-prefetch --category manhwa --slug series-slug --chapter 1
python3 miko.py publication-check --category adult_manhwa
python3 miko.py storage-sync --category adult_manhwa --apply
```

The scraper is an internal subprocess: `python3 -m sc_core.scraper` (invoked automatically by the bot). It is not a second root-level launcher.

## Running tests

```bash
python3 -m compileall -q miko.py sc_core
python3 -m pytest -q tests/
```

Some reader tests use PyMuPDF, Pillow and optional runtime packages. Network/Telegram and production MongoDB access are not required for the offline unit tests.

## Architecture

Telegram stores chapter PDF files; MongoDB stores published metadata and Telegram message references. Reader PDFs/images and covers are cached in `data/`, not saved in MongoDB. Bot settings and publishing journals stay in `data/` to survive upgrades. For adult chapters the existing confirmation restrictions are unchanged.

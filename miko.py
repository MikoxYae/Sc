"""Primary launcher: python3 miko.py starts the Telegram bot and website.

The standalone scraper remains available as `python3 sc.py <chapter-url>`.
"""
import logging
import os

os.environ.setdefault("SC_WEB_PORT", "1276")
from Miko import main as start_bot_and_website


def main():
    try:
        from owner_setup import bootstrap_from_config
        print(bootstrap_from_config(), flush=True)
    except Exception as exc:
        logging.warning("Owner bootstrap unavailable: %s", type(exc).__name__)
        print("Owner bootstrap unavailable; check MongoDB connectivity.", flush=True)
    start_bot_and_website()


if __name__ == "__main__":
    main()

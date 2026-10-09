"""Single entry point for the Sc Telegram bot and manga website."""
import os

os.environ.setdefault("SC_WEB_PORT", "1276")

from miko import main

if __name__ == "__main__":
    main()

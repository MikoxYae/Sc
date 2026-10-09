"""Single command entry point for Sc Bot and MIKO Manga Website.

    python3 miko.py                           # Telegram bot + website
    python3 miko.py metadata-sync --all --force
    python3 miko.py reader-prefetch --category manhwa --slug title --chapter 1

All implementation modules live inside the sc_core package. The private
config.py stays in the project root on the VPS and is never shipped in ZIPs.
"""
import logging
import os
import sys

os.environ.setdefault("SC_WEB_PORT", "1276")

MAINTENANCE = {
    "metadata-sync": "metadata_sync",
    "metadata-override": "metadata_override",
    "reader-prefetch": "reader_prefetch",
    "publication-check": "publication_check",
    "storage-sync": "storage_sync",
}


def main():
    if len(sys.argv) > 1 and sys.argv[1] in MAINTENANCE:
        from importlib import import_module
        module = import_module("sc_core." + MAINTENANCE[sys.argv[1]])
        sys.argv = [sys.argv[0] + " " + sys.argv[1], *sys.argv[2:]]
        result = module.main()
        if isinstance(result, int):
            raise SystemExit(result)
        return
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print("Usage: python3 miko.py [metadata-sync|metadata-override|reader-prefetch|publication-check|storage-sync] [options]")
        print("Without arguments, starts the Telegram bot and manga website.")
        return
    if len(sys.argv) > 1:
        raise SystemExit("Unknown command; use python3 miko.py --help")

    from sc_core.bot import main as run_bot_and_website
    try:
        from sc_core.owner_setup import bootstrap_from_config
        print(bootstrap_from_config(), flush=True)
    except Exception as exc:
        logging.warning("Owner bootstrap unavailable: %s", type(exc).__name__)
        print("Owner bootstrap unavailable; check MongoDB connectivity.", flush=True)
    run_bot_and_website()


if __name__ == "__main__":
    main()

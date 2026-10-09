# Sc v33 - VPS deployment repair

This release preserves the Sc v32 bot and website code and adds a safer, repeatable VPS deployment script.

## What was broken

The VPS reported `sc-miko.service could not be found`, `caddy.service could not be found`, and no listeners on ports 1980/1982/443. The website therefore was not running. Installing or starting a Telegram bot manually does not automatically install a systemd service or HTTPS proxy.

## Installation

1. Upload `Sc-Bot-Website-VPS-Fixed-v33.zip` to `/root/`.
2. Stop any **manually running** `python3 miko.py` process with Ctrl+C (do not kill unknown processes).
3. Run the one-block command supplied with the ZIP.

The installer detects the public IPv4, uses `<ip>.sslip.io` as the default hostname, checks DNS, checks ports for conflicts, installs Caddy only if missing, and creates/enables `sc-miko.service`. The Python `.venv` is reused; dependencies are not reinstalled. The website listens on 127.0.0.1:1982 and Caddy serves public HTTPS on 443, with HTTP redirects from 80 and 1980. The bot and website run together via `python3 miko.py`.

## Safety

`config.py`, `data/mongo.env`, `data/settings.json`, and all private credentials are intentionally absent from the archive. The update does not migrate or delete MongoDB records. The installer refuses to overwrite an unrelated Caddy configuration or take ports occupied by unknown processes. If an old manually launched process occupies a port, stop that process yourself before rerunning.

If HTTPS fails, verify DNS and inbound ports 80/443 in your VPS provider firewall, and inspect `journalctl -u caddy -u sc-miko -n 60 --no-pager`. `sslip.io` is a third-party wildcard DNS service and its availability is not guaranteed; you can set `SC_DOMAIN` to your own DNS name.

**Security:** Rotate the previously exposed Telegram token and MongoDB password. Never publish private config files or logs containing tokens.

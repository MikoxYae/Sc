# Sc v34 - VPS hosting verification

This release improves the v33 deployment script only. It does not modify the Telegram bot, website UI, database, passwords, or existing saved settings.

Run `bash deploy/setup_vps.sh` as root after extracting the ZIP into `/root`. Existing Python virtual environment is reused. Caddy is installed only when missing.

The script validates both services and the local website. It also attempts a public HTTPS request, but certificate issuance still requires correct public DNS and inbound TCP 80/443. If the external HTTPS check fails, inspect Caddy logs and VPS firewall rules.

Do not run a second bot process when systemd is managing the bot. Never upload `config.py` or secrets to GitHub.

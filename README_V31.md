# Sc v31 - VPS auto-detected HTTPS deployment

This release keeps the existing Telegram bot and website inside the same `Sc` repository. It removes the need for self-signed browser certificates by configuring Caddy to request a publicly trusted certificate for a hostname automatically derived from the VPS public IPv4 address (`<ip>.sslip.io`). The hostname is provided by an external DNS service; this is **not** a certificate for the raw IP address.

## Before deploying
- Stop the existing `python3 miko.py` process (Ctrl+C) to free port 1980.
- Existing `/root/Sc/config.py` and `.venv` must remain on the VPS.
- VPS ports 80, 443, and 1980 must be free; do not stop unrelated applications.
- Allow inbound TCP ports 80 and 443 in the VPS firewall/provider rules. Port 1980 is optional for legacy redirects.
- DNS and Let's Encrypt/ACME certificate issuance require internet access and working public DNS.
- If `sslip.io` is unavailable or prohibited by your DNS/network, set `SC_DOMAIN` to a hostname you control that resolves to the VPS public IP.
- `setup_vps.sh` installs Caddy using apt only if it is not already installed; it does not reinstall Python dependencies or recreate `.venv`.
- Existing Caddy configuration is never overwritten unless it was created by this project.

## Operation
`sc-miko.service` starts both Telegram bot and website using `python3 miko.py`. The website listens on `127.0.0.1:1982`, Caddy terminates HTTPS on 443, and port 1980 redirects to HTTPS. On successful issuance, users should open `https://<ip>.sslip.io` (without port). Credentials and secure session cookies remain server-side; `config.py` is excluded from the ZIP.

The server trusts `X-Forwarded-Proto: https` **only from loopback** and only when `SC_TRUST_LOCAL_PROXY=1`. Avoid exposing port 1982 publicly. No fake certificate is created. If ACME issuance fails, review `journalctl -u caddy -n 80 --no-pager` and confirm DNS and ports 80/443. Do not bypass browser certificate warnings for login.

## Restart and diagnostics
`systemctl restart sc-miko` restarts both services. `systemctl status sc-miko caddy --no-pager` displays service state. `journalctl -u sc-miko -n 80 --no-pager` displays application errors. Avoid sharing bot tokens from logs.

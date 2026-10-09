# Sc VPS deployment (v38)

Use `bash deploy/setup_vps.sh` as root on the existing VPS. It reuses `/root/Sc/.venv`, `config.py`, and the existing MongoDB and Telegram settings. The systemd-managed Python bot and website run together from `python3 miko.py`; Python binds only to `127.0.0.1:1276`. Caddy serves HTTPS on port 443 and redirects HTTP `IP:1276` to HTTPS. Telegram polling has no listening port.

The setup will not stop Docker containers or unrelated processes. It backs up the Caddyfile and refuses to overwrite an unrelated Caddy configuration. It adds firewall ACCEPT rules for ports 80, 443 and 1276, but cannot modify a provider-level firewall. If Caddy has other virtual hosts, integrate the two Sc site blocks manually rather than replacing that file.

The canonical public address is `https://<public-ip>.sslip.io/`; direct `http://<ip>:1276/` is a redirect, **not** the authenticated site. If Chrome cannot open either URL while `curl` on the VPS returns 200, check the hosting provider's inbound firewall, mobile network and DNS filtering. Local `curl` success is not proof of external reachability. For reliable access, use a domain you control with an A record pointing to the VPS.

After setup, run `bash deploy/check_access.sh`. Never run another manual `python3 miko.py` while `sc-miko.service` is active; it will conflict with the website port and Telegram polling.

Docker is intentionally not installed or enabled automatically: this VPS already runs other Docker-managed bots. Moving Sc into a new container would not fix DNS/provider firewall issues and could create another duplicate instance.

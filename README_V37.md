# Sc v37 - Website port 1276

Main entry point: `python3 miko.py` starts both Telegram bot (polling) and website.
Website internal listener: `127.0.0.1:1276` when deployed through systemd. Caddy provides HTTPS at the configured hostname. Telegram polling does not listen on port 1276.

## Existing VPS update

Upload ZIP to `/root/`, then run:

```bash
cd /root && unzip -o Sc-Bot-Website-Port1276-v37.zip -d /root && cd /root/Sc && bash deploy/setup_vps.sh
```

No new Python dependencies; existing `.venv`, `config.py`, and data files are not packaged. Do not start a second manual bot while systemd is active. To run manually, first stop the systemd service, activate `.venv`, and run `python3 miko.py`.

The public HTTPS hostname remains unchanged. If another process owns port 1276, the installer refuses to kill it.

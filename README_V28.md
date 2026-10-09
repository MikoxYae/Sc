# Sc v28 - Entry point correction

`python3 miko.py` now invokes `Miko.main()` (Telegram bot + website on port 1980), not `sc.main()` (CLI scraper).

The original standalone scraper is still accessible using `python3 sc.py <chapter-url>`.

Existing `config.py`, `data/`, `.venv/` and TLS certificates are not included or overwritten.

## Deploy
Stop the old running bot, upload the ZIP to `/root/`, then run:

```bash
cd /root && unzip -o Sc-Bot-Website-Entry-Fixed-v28.zip -d /root -x 'Sc/config.py' && cd /root/Sc && . .venv/bin/activate && export SC_TLS_CERT=/root/Sc/.certs/cert.pem SC_TLS_KEY=/root/Sc/.certs/key.pem && python3 miko.py
```

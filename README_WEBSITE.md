# Sc Website Preview (Port 1980)

This is the existing Sc Telegram bot v17 plus the MIKO manga frontend prototype in `website/`.

Run from the Sc directory: `source .venv/bin/activate && python Miko.py`. Both the Telegram bot and the website preview start from the same process.

Website: `http://YOUR_VPS_IP:1980` (allow port 1980 in firewall if needed). Set `SC_WEB_PORT` or `SC_WEB_HOST` to override defaults.

**Important:** The frontend currently uses fictional sample titles and local browser-only preferences. No MongoDB, Telegram storage, login, PDF.js reader or publishing integration is implemented yet. Do not put passwords or bot tokens into the website. This is a development preview and its built-in static server is not a production web server.

Existing `config.py`, `.venv`, and `data/settings.json` are excluded from the update package; keep them on your VPS. No additional Python packages required.

To stop both services, press Ctrl+C.

## v19 Mobile UI
- Responsive mobile header and collapsible navigation, with expanded-state accessibility.
- Two-column story cards, horizontally scrollable category filters, and larger touch targets.
- Mobile bottom-sheet modals, narrower hero art, and safe-area padding.
- No changes to bot processing, config, dependencies, or website port (1980).

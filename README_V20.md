# Sc v20 - Manga Website and Telegram Storage Settings

## What's new
- Same Sc repository, `python Miko.py`, website on port 1980.
- Editorial dark/red mobile-friendly visual refresh, inspired by supplied references (not a copy).
- Ignore harmless mobile browser connection resets without suppressing other server errors.
- Owner-only Settings > Storage: set private channel ID, configure MongoDB URI, check connection.
- Channel ID automatically normalizes numeric input to `-100...`; validates bot administrator membership.
- Mongo URI tested using MongoDB ping and saved to `data/mongo.env` (0600 permissions), not committed to Git.

## Security and scope
- Keep bot admin in the private storage channel; granting admin rights does not itself publish content.
- MongoDB and Telegram storage **configuration only**: automatic PDF publication and website reader API are not implemented yet.
- Website dashboard remains a nonfunctional preview. Do not enter credentials into it.
- Avoid sharing credentials in public logs; rotate previously exposed bot token and database password.
- Website currently serves sample data. Adult content must be gated appropriately before production.

## Upgrade
Extract the v20 archive into `/root`, preserving `config.py` and `data/`.
Existing virtualenv is reused. Install requirements only when changed (v20 adds `pymongo[srv]`).

## Test
- `python -m compileall -q Miko.py sc.py website_server.py`
- Start bot, open `/settings` > `Storage` (owner only), configure channel, MongoDB and check connection.
- Open `http://YOUR_VPS_IP:1980` from mobile and verify home, navigation, search and cards.

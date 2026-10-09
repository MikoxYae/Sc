# Sc Reader v40 - Reliability update

This update addresses reader status polling that never reaches `ready`.

## Changes
- Timeout and error reporting for Telegram connection, channel message lookup, and each PDF part download.
- Use the actual file path returned by Pyrofork when downloading.
- Log PDF retrieval progress without exposing channel IDs or credentials.
- Track active reader jobs and prevent duplicate jobs after timeout.
- Retry failed jobs after a short cooldown; no indefinite processing state.
- Reduce browser status polling to every five seconds.

## Deployment
Upload ZIP to `/root`, unzip into `/root/Sc`, install dependencies **only if not already installed**, and restart `sc-miko.service`. Do not run another `miko.py` process while systemd is active.

## Reader troubleshooting
`journalctl -u sc-miko.service -f --no-pager` and open a published chapter. The `/api/chapter` endpoint returns `processing`, `ready` or `error`. An error may indicate inaccessible channel, missing Telegram permissions, network timeouts, or a PDF rendering problem.

PDFs stay in Telegram storage; MongoDB stores references only. Reader output is cached under ignored `data/reader_cache/`.

## Testing
`python -m unittest discover -s tests -p 'test_reader_v*.py'` (requires installed dependencies).

## Security
Keep `config.py` and session files out of Git and ZIP. Rotate previously exposed credentials. For licensed/authorized content only.

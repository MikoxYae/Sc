# Sc v25 — Website accounts

This update keeps the Telegram bot and manga website in the same repository and adds dedicated `#/auth/login`, `#/auth/signup`, and `#/profile` pages. The hamburger navigation also links to the account page. Account records and session hashes are stored in the `sc_accounts` MongoDB database. The owner role is granted **only** after provisioning through a trusted VPS terminal; knowing the email alone never grants privileges.

## Owner setup (one time)

Configure MongoDB through the existing Telegram bot storage settings (or gitignored `config.py`), then run `python owner_setup.py` inside the existing `.venv`. The script prompts for a password twice, saves only a salted password hash, and invalidates old owner sessions. The supplied short test password can be used for a local test, but a stronger unique password is recommended and should be changed before production.

**The owner must sign in via the website like every other user.** Account creation for the reserved owner email is blocked; the VPS provisioning step securely creates the account. No passwords or database credentials are shipped in this ZIP.

## HTTPS required

The backend intentionally rejects public HTTP sign-in/sign-up. Put the site behind an HTTPS reverse proxy, set `SC_HTTPS=1` only after HTTPS is correctly configured, and do not expose port 1980 directly to the public internet. Secure cookies are enabled with `SC_HTTPS=1`. Do not disable the HTTPS check on a public deployment.

## Verification

- Sign up a normal email with a 12+ character password, then sign in.
- Confirm `/api/me` reports `reader` and the hamburger menu shows profile.
- Sign out and sign in as the provisioned owner; `/api/me` should report `owner`.
- Verify invalid passwords fail, owner email cannot be registered publicly, and pages work on narrow mobile screens.
- Admin publishing UI is not implemented yet; the owner profile indicates verified owner access.

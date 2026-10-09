# Sc v26 - Login fixes

- `python3 miko.py` now starts bot and website.
- Responsive login/sign-up, show/hide passwords, 8-character registration validation (digit + special character).
- Owner must be provisioned once using `python3 owner_setup.py`; knowing the email alone does not grant owner access.
- Passwords are hashed in MongoDB. The previously shared test password does not satisfy the new policy; set a new password locally.
- HTTPS is mandatory for public authentication. Configure SC_TLS_CERT and SC_TLS_KEY to PEM paths, or deploy behind a correctly configured TLS reverse proxy (reverse-proxy trust requires additional configuration).
- For testing on IP address, a self-signed certificate can be created with OpenSSL. Browsers will warn that it is untrusted. Use a trusted certificate on a domain for production.
- This update preserves other Sc files, and does not include config.py, .venv, or local data.

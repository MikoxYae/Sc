# Sc v27 - Test owner configuration

The private `config.py` contains a MongoDB test URI and a **salted password hash** for the requested owner account. The plaintext password is not embedded. On startup `python3 miko.py` provisions the owner if absent; existing owner credentials are **never overwritten**.

If the owner account already exists with a different password, run `python3 owner_setup.py` to reset it interactively.

The password policy now allows 8-128 characters with a number and a special character, matching the provided testing password. The website must be opened with HTTPS; configure SC_TLS_CERT and SC_TLS_KEY to the existing cert paths.

**Security:** ZIP contains a live MongoDB test URI. Do not publish or commit it. Rotate the MongoDB password and bot token after testing. The current certificate is self-signed and not suitable for public deployment.

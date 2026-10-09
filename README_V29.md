# Sc v29 - Login connection and mobile form fixes

- Port 1980 is HTTP redirect only when TLS is enabled; port 1981 is the HTTPS app.
- Open http://YOUR_SERVER_IP:1980 to be redirected to https://YOUR_SERVER_IP:1981.
- A self-signed certificate causes a browser warning during testing. Use a trusted domain certificate for production.
- If HTTPS port 1981 is blocked, open it in the VPS firewall/provider firewall.
- Login/signup require HTTPS; never disable this check.
- Password eye button is present on login, registration and confirmation inputs.
- Existing owner credentials are not overwritten. Run python3 owner_setup.py to reset the owner password securely if needed.
- Existing config.py and data settings are not packaged.
- Run: python3 miko.py

"""Simple 18+ self-declaration for the reader (NOT identity/age verification).

Confirmation is remembered by a short-lived, signed first-party cookie.
No account, identity document or MongoDB write is required. The signing key
is generated on the VPS at first use and never ships in the source archive.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from pathlib import Path

COOKIE_NAME = 'sc_adult_confirm'
COOKIE_SECONDS = 30 * 24 * 60 * 60
KEY_FILE = Path(__file__).resolve().parent.parent / 'data' / '.adult_confirm_key'


def _key():
    path = KEY_FILE
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, 'wb') as out:
            out.write(secrets.token_bytes(32))
    # Reject a symlink or insecure secret: don't accidentally read an attacker-controlled key.
    if path.is_symlink():
        raise RuntimeError('Adult confirmation secret must not be a symlink')
    os.chmod(path, 0o600)
    secret = path.read_bytes()
    if len(secret) != 32:
        raise RuntimeError('Invalid adult confirmation secret')
    return secret


def _b64(data):
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def issue(now=None):
    expiry = int(time.time() if now is None else now) + COOKIE_SECONDS
    body = f'v1.{expiry}.{secrets.token_urlsafe(12)}'
    signature = _b64(hmac.new(_key(), body.encode('ascii'), hashlib.sha256).digest())
    return body + '.' + signature


def valid(token, now=None):
    if not isinstance(token, str) or len(token) > 180:
        return False
    match = re.fullmatch(r'v1\.(\d{10})\.([A-Za-z0-9_-]{16,32})\.([A-Za-z0-9_-]{43})', token)
    if match is None:
        return False
    expires = int(match.group(1))
    current = int(time.time() if now is None else now)
    if expires < current or expires > current + COOKIE_SECONDS + 60:
        return False
    body, given = token.rsplit('.', 1)
    expected = _b64(hmac.new(_key(), body.encode('ascii'), hashlib.sha256).digest())
    return hmac.compare_digest(expected, given)


def cookie(token, secure=True):
    suffix = '; Secure' if secure else ''
    return (f'{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; '
            f'Max-Age={COOKIE_SECONDS}{suffix}')

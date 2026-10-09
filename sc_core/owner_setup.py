"""Provision the owner from a trusted VPS terminal; never ship passwords in ZIP/Git."""
import getpass
import secrets
from datetime import datetime, timezone
from pymongo import MongoClient
from .web_auth import OWNER_EMAIL, digest, valid_password
from .catalog_db import uri_for

def main():
    uri = uri_for('manga')
    if not uri:
        raise SystemExit('Configure MongoDB in bot Storage settings or config.py first.')
    password = getpass.getpass('Owner password (8-128 chars, number + special): ')
    if not valid_password(password):
        raise SystemExit('Password must be 8-128 characters and include a number and a special character.')
    confirm = getpass.getpass('Confirm owner password: ')
    if password != confirm:
        raise SystemExit('Passwords do not match.')
    db = MongoClient(uri, serverSelectionTimeoutMS=7000)['sc_accounts']
    db.users.create_index('email', unique=True)
    salt = secrets.token_hex(16)
    db.users.update_one({'email': OWNER_EMAIL}, {'$set': {'salt': salt, 'password_hash': digest(password, salt), 'owner_verified': True, 'role': 'owner', 'owner_provisioned_at': datetime.now(timezone.utc)}, '$setOnInsert': {'created_at': datetime.now(timezone.utc)}}, upsert=True)
    db.sessions.delete_many({'email': OWNER_EMAIL})
    print('Owner account ready. Sign in on the website to activate the owner session.')

if __name__ == '__main__':
    main()


def bootstrap_from_config():
    """Create the configured owner only when absent; never reset an existing owner."""
    import config
    uri = uri_for('manga')
    if not uri:
        raise RuntimeError('MongoDB URI is missing')
    d = MongoClient(uri, serverSelectionTimeoutMS=7000)['sc_accounts']
    d.users.create_index('email', unique=True)
    email = str(getattr(config, 'OWNER_EMAIL', OWNER_EMAIL)).strip().lower()
    if email != OWNER_EMAIL:
        raise RuntimeError('Configured owner email does not match reserved owner')
    if d.users.find_one({'email': email}):
        return 'Owner account already exists; password was not changed.'
    salt = getattr(config, 'OWNER_PASSWORD_SALT', '')
    password_hash = getattr(config, 'OWNER_PASSWORD_HASH', '')
    if not salt or not password_hash:
        raise RuntimeError('Owner password hash is missing from config')
    d.users.insert_one({'email':email,'salt':salt,'password_hash':password_hash,'owner_verified':True,'role':'owner','created_at':datetime.now(timezone.utc)})
    return 'Owner account created.'

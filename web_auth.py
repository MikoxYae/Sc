"""MongoDB backed accounts; privileged role is only granted by VPS provisioning."""
import secrets, hashlib, hmac, re
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from catalog_db import uri_for

OWNER_EMAIL = 'musicstudios756@gmail.com'

def db():
    uri = uri_for('manga')
    if not uri:
        raise RuntimeError('MongoDB not configured')
    return MongoClient(uri, serverSelectionTimeoutMS=3000)['sc_accounts']

def digest(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 310000).hex()

def valid_password(password):
    return (isinstance(password, str) and 8 <= len(password) <= 128
            and bool(re.search(r'[0-9]', password))
            and bool(re.search(r'[^A-Za-z0-9\s]', password))
            and not any(c.isspace() for c in password))

def register(email, password):
    email = email.strip().lower()
    if not re.fullmatch(r'[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}', email):
        raise ValueError('Invalid email')
    if not valid_password(password):
        raise ValueError('Password must be 8-128 characters, with a number and a special character')
    if email == OWNER_EMAIL:
        raise ValueError('Owner account must be provisioned on the VPS')
    d = db()
    d.users.create_index('email', unique=True)
    salt = secrets.token_hex(16)
    d.users.insert_one({'email': email, 'salt': salt, 'password_hash': digest(password, salt), 'role': 'reader', 'created_at': datetime.now(timezone.utc)})
    return email

def login(email, password):
    d = db()
    user = d.users.find_one({'email': email.strip().lower()})
    if not user or not user.get('salt') or not user.get('password_hash') or not hmac.compare_digest(digest(password, user['salt']), user['password_hash']):
        raise ValueError('Invalid email or password')
    token = secrets.token_urlsafe(32)
    d.sessions.create_index('expires', expireAfterSeconds=0)
    d.sessions.insert_one({'token_hash': hashlib.sha256(token.encode()).hexdigest(), 'email': user['email'], 'expires': datetime.now(timezone.utc)+timedelta(days=7)})
    return token

def identity(token):
    if not token:
        return None
    d = db()
    session = d.sessions.find_one({'token_hash': hashlib.sha256(token.encode()).hexdigest(), 'expires': {'$gt': datetime.now(timezone.utc)}})
    if not session:
        return None
    account = d.users.find_one({'email': session['email']}, {'email': 1, 'role': 1, 'owner_verified': 1})
    if not account:
        return None
    role = 'owner' if account['email'] == OWNER_EMAIL and account.get('owner_verified') else account.get('role', 'reader')
    if role == 'owner' and account['email'] != OWNER_EMAIL:
        role = 'reader'
    return {'email': account['email'], 'role': role}

def logout(token):
    if token:
        db().sessions.delete_many({'token_hash': hashlib.sha256(token.encode()).hexdigest()})

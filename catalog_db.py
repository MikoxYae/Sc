"""MongoDB catalog: separate collections/databases by category, published-only reads."""
import os, json, logging
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError
ROOT=Path(__file__).resolve().parent
LOG = logging.getLogger('Sc.catalog')
CATEGORIES={'manga':'sc_manga','manhwa':'sc_manhwa','manhua':'sc_manhua',
            'webtoon':'sc_webtoon','adult_manga':'sc_adult_manga',
            'adult_manhwa':'sc_adult_manhwa','adult_webtoon':'sc_adult_webtoon'}
CATEGORY_LABELS={'manga':'Manga','manhwa':'Manhwa','manhua':'Manhua',
                 'webtoon':'Webtoon','adult_manga':'18+ Manga',
                 'adult_manhwa':'18+ Manhwa','adult_webtoon':'18+ Webtoon'}

def save_published_chapter(category,title,chapter,pages,channel,messages):
    """Store channel post references, not public Telegram URLs."""
    import re
    from datetime import datetime, timezone
    if category not in CATEGORIES or not messages:
        raise ValueError('Category or storage messages missing')
    col=collection(category)
    if col is None:raise RuntimeError('MongoDB is not configured for this category')
    slug=re.sub(r'[^a-z0-9]+','-',title.casefold()).strip('-')[:130]
    if not slug:raise ValueError('Invalid title')
    now=datetime.now(timezone.utc)
    entry={'number':str(chapter),'title':f'Chapter {chapter}', 'pages':pages,
           'telegram':{'chat_id':int(channel),'documents':messages}}
    # Repeated upload of the same chapter replaces its reference, not a duplicate entry.
    col.update_one({'slug':slug},{'$setOnInsert':{'slug':slug,'title':title,'category':category,
        'created_at':now,'chapters':[],'published':False}},upsert=True)
    col.update_one({'slug':slug},{'$pull':{'chapters':{'number':str(chapter)}}})
    col.update_one({'slug':slug},{'$push':{'chapters':entry},
        '$set':{'updated_at':now,'published':True}})


def uri_for(category):
    """One MongoDB connection shared across all category databases."""
    uri = os.getenv('SC_MONGO_URI')
    if uri:
        return uri
    try:
        import config
        uri = getattr(config, 'MONGO_URI', '') or getattr(config, 'MONGODB_URI', '')
        if uri:
            return uri
    except ImportError:
        pass
    file = ROOT / 'data' / 'mongo.env'
    return file.read_text().strip() if file.exists() else ''

# Only fields intended for public display are exposed. Telegram refs, sessions,
# internal metadata lookup state and MongoDB IDs must never reach website users.
PUBLIC_TITLE_PROJECTION = {
    '_id': 0, 'slug': 1, 'title': 1, 'category': 1,
    'created_at': 1, 'updated_at': 1,
    'chapters.number': 1, 'chapters.title': 1,
    'cover_url': 1, 'description': 1, 'genres': 1,
    'authors': 1, 'artists': 1, 'status': 1, 'year': 1,
    'rating': 1, 'original_title': 1, 'alternative_titles': 1,
    'metadata_source_urls': 1,
}

@lru_cache(maxsize=2)
def _mongo_client(uri):
    # One thread-safe connection pool for all category collections. Previously
    # each /api/catalog request created 7 new MongoClients and pools.
    return MongoClient(uri, serverSelectionTimeoutMS=3500,
                       connectTimeoutMS=3500, socketTimeoutMS=8000,
                       maxPoolSize=20)


def collection(category):
    if category not in CATEGORIES:
        raise ValueError('Invalid category')
    uri = uri_for(category)
    if not uri:
        return None
    return _mongo_client(uri)[CATEGORIES[category]]['titles']


def public_title(doc, category):
    """Convert a published MongoDB record to a small, safe JSON document."""
    if not isinstance(doc, dict):
        raise ValueError('Invalid catalog record')
    allowed = {key.split('.')[0] for key in PUBLIC_TITLE_PROJECTION if key != '_id'}
    safe = {key: value for key, value in doc.items() if key in allowed and key != 'chapters'}
    safe['category'] = category
    for key in ('created_at', 'updated_at'):
        if isinstance(safe.get(key), datetime):
            safe[key] = safe[key].isoformat()
    safe['chapters'] = [
        {'number': str(ch.get('number', '')), 'title': str(ch.get('title', ''))}
        for ch in doc.get('chapters', []) if isinstance(ch, dict)
    ]
    return safe


def public_catalog(category=None, query='', page=1, limit=10):
    categories = [category] if category else list(CATEGORIES)
    if any(c not in CATEGORIES for c in categories):
        raise ValueError('Invalid category')
    found = []
    unavailable = []
    for c in categories:
        try:
            col = collection(c)
            if col is None:
                raise RuntimeError('MongoDB connection not configured')
            criteria = {'published': True, 'chapters.0': {'$exists': True}}
            if query:
                import re
                criteria['title'] = {'$regex': re.escape(query[:70]), '$options': 'i'}
            cursor = col.find(criteria, PUBLIC_TITLE_PROJECTION).sort('updated_at', DESCENDING).limit(500)
            found.extend(public_title(doc, c) for doc in cursor)
        except (PyMongoError, RuntimeError) as exc:
            LOG.warning('Catalog read failed for category %s (%s)', c, type(exc).__name__)
            unavailable.append(c)
    if unavailable and len(unavailable) == len(categories):
        raise RuntimeError('Catalog database unavailable')
    found.sort(key=lambda x: str(x.get('updated_at') or ''), reverse=True)
    start = (page - 1) * limit
    return {
        'items': found[start:start + limit], 'page': page, 'total': len(found),
        'pages': max(1, (len(found) + limit - 1) // limit),
        'partial': bool(unavailable), 'unavailable_categories': unavailable,
    }


def ensure_indexes():
    for category in CATEGORIES:
        col = collection(category)
        if col is not None:
            col.create_index('slug', unique=True)
            col.create_index([('published', 1), ('updated_at', -1)])

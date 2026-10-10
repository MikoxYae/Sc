"""MongoDB catalog: separate collections/databases by category, published-only reads."""
import os, json, logging, re
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError
from sc_core import genre_taxonomy
ROOT=Path(__file__).resolve().parent.parent
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
    'cover_url': 1, 'cover_local': 1, 'description': 1, 'genres': 1, 'tags': 1,
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
    safe['has_cover'] = bool(safe.get('cover_url') or safe.get('cover_local'))
    safe.pop('cover_local', None)
    safe['category'] = category
    for key in ('created_at', 'updated_at'):
        if isinstance(safe.get(key), datetime):
            safe[key] = safe[key].isoformat()
    safe['chapters'] = [
        {'number': str(ch.get('number', '')), 'title': str(ch.get('title', ''))}
        for ch in doc.get('chapters', []) if isinstance(ch, dict)
    ]
    return safe


MAX_SELECTED_GENRES = 16


def normalize_genre_selection(values):
    """Validate and deduplicate requested genre names, without inventing tags.

    The frontend sends repeated ?genre=Action&genre=Drama query parameters.
    A single comma-delimited parameter also works for interoperable clients.
    """
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        raise ValueError('Invalid genres')
    names = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError('Invalid genre')
        for piece in value.split(','):
            name = ' '.join(piece.split()).strip()
            if not name:
                continue
            if len(name) > 65 or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
                raise ValueError('Invalid genre')
            key = name.casefold()
            if key not in seen:
                names.append(name)
                seen.add(key)
            if len(names) > MAX_SELECTED_GENRES:
                raise ValueError('Too many genres selected')
    return names


def _published_criteria():
    return {'published': True, 'chapters.0': {'$exists': True}}


def public_genres(category=None):
    """Broad selectable vocabulary + real genres and tags from published titles.

    AniList's base genres and common community tags are made visible even when
    no currently published manga has that label. Filtering *never* assigns a
    genre to any manga; only existing, published titles with verified metadata
    can match a selected label. No external API call is needed to show options.
    """
    categories = [category] if category else list(CATEGORIES)
    if any(c not in CATEGORIES for c in categories):
        raise ValueError('Invalid category')
    found = {name.casefold(): name for name in genre_taxonomy.vocabulary()}
    unavailable = []
    for cat in categories:
        try:
            col = collection(cat)
            if col is None:
                raise RuntimeError('MongoDB connection not configured')
            for field in ('genres', 'tags'):
                for entry in col.distinct(field, _published_criteria()):
                    if not isinstance(entry, str):
                        continue
                    name = genre_taxonomy.canonical(entry)
                    if not name or len(name) > 65:
                        continue
                    found.setdefault(name.casefold(), name)
        except (PyMongoError, RuntimeError) as exc:
            LOG.warning('Genre discovery failed for %s (%s)', cat, type(exc).__name__)
            unavailable.append(cat)
    choices = sorted(found.values(), key=str.casefold)
    return {
        'genres': choices,
        'anilist_genres': list(genre_taxonomy.ANILIST_GENRES),
        'extra_genres': [x for x in choices if not genre_taxonomy.is_anilist_genre(x)],
        'partial': bool(unavailable),
        'unavailable_categories': unavailable,
        'source_note': 'AniList genres and common themes; results require matching published metadata.',
    }


def public_catalog(category=None, query='', page=1, limit=10, genres=None):
    categories = [category] if category else list(CATEGORIES)
    if any(c not in CATEGORIES for c in categories):
        raise ValueError('Invalid category')
    selected_genres = normalize_genre_selection(genres)
    found = []
    unavailable = []
    for c in categories:
        try:
            col = collection(c)
            if col is None:
                raise RuntimeError('MongoDB connection not configured')
            criteria = _published_criteria()
            if query:
                criteria['title'] = {'$regex': re.escape(query[:70]), '$options': 'i'}
            if selected_genres:
                # ANY/OR match against both real provider genres AND tags.
                # Anchoring prevents Action matching Live Action, and aliases
                # handle e.g. School Life (filter) vs School (AniList tag).
                aliases = set()
                for genre in selected_genres:
                    aliases.update(genre_taxonomy.alternatives(genre_taxonomy.canonical(genre)))
                patterns = [re.compile(r'^\s*' + re.escape(value) + r'\s*$', re.IGNORECASE)
                            for value in sorted(aliases)]
                # Webtoon is also a publication format, so category titles
                # satisfy that filter even if upstream has no Webtoon tag.
                if not (c in ('webtoon', 'adult_webtoon') and any(
                        genre_taxonomy.canonical(g) == 'Webtoon' for g in selected_genres)):
                    criteria['$or'] = [
                        {'genres': {'$in': patterns}},
                        {'tags': {'$in': patterns}},
                    ]
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
        'genres': selected_genres,
        'partial': bool(unavailable), 'unavailable_categories': unavailable,
    }


def ensure_indexes():
    for category in CATEGORIES:
        col = collection(category)
        if col is not None:
            col.create_index('slug', unique=True)
            col.create_index([('published', 1), ('updated_at', -1)])

"""MongoDB catalog: separate collections/databases by category, published-only reads."""
import os, json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError
ROOT=Path(__file__).resolve().parent
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

def collection(category):
    if category not in CATEGORIES:raise ValueError('Invalid category')
    uri=uri_for(category)
    if not uri:return None
    client=MongoClient(uri,serverSelectionTimeoutMS=3000,connectTimeoutMS=3000)
    return client[CATEGORIES[category]]['titles']

def public_catalog(category=None,query='',page=1,limit=10):
    categories=[category] if category else list(CATEGORIES)
    if any(c not in CATEGORIES for c in categories):raise ValueError('Invalid category')
    # Cross-category merged feed sorted by latest published update.
    found=[]
    for c in categories:
        col=collection(c)
        if col is None:continue
        criteria={'published':True,'chapters.0':{'$exists':True}}
        if query:criteria['title']={'$regex':__import__('re').escape(query[:70]),'$options':'i'}
        for d in col.find(criteria,{'_id':0,'telegram':0,'storage':0,'chapters.telegram':0,'chapters.file_id':0}).sort('updated_at',DESCENDING).limit(500):
            d['category']=c
            for k in ('updated_at','created_at'):
                if isinstance(d.get(k),datetime):d[k]=d[k].isoformat()
            d['chapters']=[{'number':str(x.get('number','')),'title':str(x.get('title',''))} for x in d.get('chapters',[]) if isinstance(x,dict)]
            found.append(d)
    found.sort(key=lambda x:str(x.get('updated_at','')),reverse=True)
    start=(page-1)*limit
    return {'items':found[start:start+limit],'page':page,'total':len(found),'pages':max(1,(len(found)+limit-1)//limit)}

def ensure_indexes():
    for category in CATEGORIES:
        col=collection(category)
        if col is not None:
            col.create_index('slug',unique=True)
            col.create_index([('published',1),('updated_at',-1)])

"""Provider-based metadata lookup. No scraping or automatic publishing."""
import difflib
import html
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
import requests
from pymongo import MongoClient

GRAPHQL = 'https://graphql.anilist.co'
ANILIST_QUERY = '''query ($search:String!){Page(page:1,perPage:8){media(type:MANGA,search:$search){id idMal title{english romaji native} synonyms description(asHtml:false) coverImage{extraLarge large} bannerImage genres tags{name} staff(perPage:10){edges{node{name{full}} role}} status startDate{year month day} endDate{year month day} chapters volumes averageScore popularity isAdult countryOfOrigin format siteUrl}}}'''

class ProviderError(Exception):
    pass

class MetadataEngine:
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self._last = {}

    def request(self, provider, method, url, **kwargs):
        gap = {'anilist':2.2,'mangaupdates':1.5,'mangadex':1.2}.get(provider,2)
        wait = gap - (time.monotonic() - self._last.get(provider,0))
        if wait > 0:time.sleep(wait)
        self._last[provider] = time.monotonic()
        for attempt in range(3):
            try:
                r = self.session.request(method,url,timeout=18,headers={'User-Agent':'ScMetadata/1.0 (contact: project operator)','Accept':'application/json'},**kwargs)
                if r.status_code in (429,500,502,503,504):
                    if attempt == 2:raise ProviderError(f'{provider} HTTP {r.status_code}')
                    time.sleep(min(12,int(r.headers.get('Retry-After','2')) if r.headers.get('Retry-After','2').isdigit() else 2**attempt))
                    continue
                r.raise_for_status()
                return r.json()
            except (requests.RequestException, ValueError) as exc:
                if attempt == 2:raise ProviderError(f'{provider}: {type(exc).__name__}') from exc
                time.sleep(2**attempt)

    def anilist(self, query):
        data=self.request('anilist','POST',GRAPHQL,json={'query':ANILIST_QUERY,'variables':{'search':query}})
        if data.get('errors'):raise ProviderError('AniList GraphQL error')
        out=[]
        for m in ((data.get('data') or {}).get('Page') or {}).get('media') or []:
            title=m.get('title') or {}
            name=title.get('english') or title.get('romaji') or title.get('native')
            if not name:continue
            staff=m.get('staff') or {}
            authors=[];artists=[]
            for edge in staff.get('edges') or []:
                person=((edge.get('node') or {}).get('name') or {}).get('full')
                role=(edge.get('role') or '').lower()
                if person and ('story' in role or 'original' in role or 'writer' in role):authors.append(person)
                if person and ('art' in role or 'illustrat' in role):artists.append(person)
            status={'RELEASING':'Ongoing','FINISHED':'Completed','HIATUS':'Hiatus','CANCELLED':'Cancelled','NOT_YET_RELEASED':'Upcoming'}.get(m.get('status'),'Unknown')
            country=m.get('countryOfOrigin')
            typ={'JP':'Manga','KR':'Manhwa','CN':'Manhua'}.get(country,'Other')
            out.append({'title':name,'original_title':title.get('native'),'alternative_titles':list(dict.fromkeys([x for x in [title.get('romaji'),title.get('english'),*(m.get('synonyms') or [])] if x and x!=name])),'description':html.unescape(re.sub(r'<[^>]*>','',m.get('description') or '')) or None,'cover':(m.get('coverImage') or {}).get('extraLarge') or (m.get('coverImage') or {}).get('large'),'banner':m.get('bannerImage'),'genres':m.get('genres') or [],'tags':[t.get('name') for t in m.get('tags') or [] if t.get('name')],'authors':authors,'artists':artists,'status':status,'original_status':m.get('status'),'chapters':m.get('chapters'),'volumes':m.get('volumes'),'rating':m.get('averageScore'),'popularity':m.get('popularity'),'content_rating':'Adult' if m.get('isAdult') else None,'original_language':{'JP':'ja','KR':'ko','CN':'zh'}.get(country),'type':typ,'format':m.get('format'),'year':(m.get('startDate') or {}).get('year'),'sources':{'anilist':m.get('id'),'myanimelist':m.get('idMal')},'source_urls':{'anilist':m.get('siteUrl')},'provider':'anilist'})
        return out

    def mangadex(self, query, *, include_adult=False):
        # MangaDex's default search omits 'pornographic' titles. Explicitly
        # request the complete rating set ONLY for an owner-classified 18+ entry.
        # All ratings remain provider metadata, not distribution permissions.
        ratings = ['safe', 'suggestive', 'erotica']
        if include_adult:
            ratings.append('pornographic')
        params = {'title': query, 'limit': 8,
                  'includes[]': ['author', 'artist', 'cover_art'],
                  'contentRating[]': ratings}
        data=self.request('mangadex','GET','https://api.mangadex.org/manga',params=params)
        out=[]
        for item in data.get('data') or []:
            a=item.get('attributes') or {}; titles=a.get('title') or {}
            title=titles.get('en') or next(iter(titles.values()),None)
            if not title:continue
            rel=item.get('relationships') or []
            authors=[(r.get('attributes') or {}).get('name') for r in rel if r.get('type')=='author']
            artists=[(r.get('attributes') or {}).get('name') for r in rel if r.get('type')=='artist']
            desc=a.get('description') or {}
            cover_rel=next((r for r in rel if r.get('type')=='cover_art'),None)
            cover_file=((cover_rel or {}).get('attributes') or {}).get('fileName')
            out.append({'title':title,'original_title':None,'alternative_titles':[v for d in a.get('altTitles') or [] for v in d.values() if v],'description':desc.get('en') or next(iter(desc.values()),None),'cover':f'https://uploads.mangadex.org/covers/{item["id"]}/{cover_file}' if cover_file else None,'genres':[t.get('attributes',{}).get('name',{}).get('en') for t in a.get('tags') or [] if t.get('attributes',{}).get('group')=='genre'],'authors':[x for x in authors if x],'artists':[x for x in artists if x],'status':{'ongoing':'Ongoing','completed':'Completed','hiatus':'Hiatus','cancelled':'Cancelled'}.get(a.get('status'),'Unknown'),'chapters':None,'content_rating':(a.get('contentRating') or '').capitalize() or None,'original_language':a.get('originalLanguage'),'type':{'ja':'Manga','ko':'Manhwa','zh':'Manhua','zh-hk':'Manhua'}.get(a.get('originalLanguage'),'Other'),'year':a.get('year'),'sources':{'mangadex':item.get('id')},'source_urls':{'mangadex':'https://mangadex.org/title/'+item['id']},'provider':'mangadex'})
        return out

    def mangaupdates(self, query):
        """Public series search with optional details for an exact title match.

        MangaUpdates may require authorization or throttle some endpoints;
        search remains usable when the per-series detail request is denied.
        """
        data=self.request('mangaupdates','POST','https://api.mangaupdates.com/v1/series/search',
                          json={'search':query,'perpage':8})
        out=[]
        for entry in data.get('results') or []:
            item=entry.get('record') or {}
            title=item.get('title')
            if not title:continue
            full=item
            sid=item.get('series_id')
            if sid and normalize(query)==normalize(title):
                try:
                    details=self.request('mangaupdates','GET',f'https://api.mangaupdates.com/v1/series/{int(sid)}')
                    if isinstance(details,dict) and normalize(details.get('title',''))==normalize(title):
                        full=details
                except (ProviderError, ValueError):
                    pass
            url=((full.get('image') or {}).get('url') or {})
            image=url.get('original') or url.get('thumb') if isinstance(url,dict) else url if isinstance(url,str) else None
            authors=[];artists=[]
            for person in full.get('authors') or []:
                if not isinstance(person,dict):continue
                value=person.get('name')
                if value:
                    (artists if 'artist' in str(person.get('type','')).lower() else authors).append(value)
            alternative=[a.get('title') for a in full.get('associated') or [] if isinstance(a,dict) and a.get('title')]
            raw_type=str(full.get('type') or '').lower()
            media_type={'manhwa':'Manhwa','manhua':'Manhua','manga':'Manga','webtoon':'Webtoon'}.get(raw_type,'Other')
            genres=[]
            for g in full.get('genres') or []:
                name=g.get('genre') if isinstance(g,dict) else g if isinstance(g,str) else None
                if name:genres.append(name)
            desc=full.get('description')
            raw_year=full.get('year')
            try:year=int(raw_year) if raw_year else None
            except (ValueError,TypeError):year=None
            out.append({'title':title,'original_title':None,'alternative_titles':alternative,
                        'description':desc if isinstance(desc,str) else None,'cover':image,
                        'genres':genres,'authors':authors,'artists':artists,'status':'Unknown',
                        'chapters':None,'content_rating':None,'type':media_type,'year':year,
                        'sources':{'mangaupdates':sid},'source_urls':{'mangaupdates':full.get('url') or item.get('url')},
                        'provider':'mangaupdates'})
        return out

    def search(self, query):
        if not isinstance(query,str) or not 2<=len(query.strip())<=120:raise ValueError('Title must contain 2-120 characters')
        results=[];errors=[]
        for name in ('anilist','mangaupdates','mangadex'):
            try:results.extend(getattr(self,name)(query))
            except (ProviderError,KeyError,TypeError) as exc:errors.append(f'{name}: {str(exc)[:80]}')
        key=normalize(query)
        for item in results:
            names=[item['title'],*item.get('alternative_titles',[])]
            item['confidence']=round(max((difflib.SequenceMatcher(None,key,normalize(n)).ratio() for n in names if n),default=0),3)
        # Do not merge different-provider records without verified shared IDs.
        results.sort(key=lambda x:x['confidence'],reverse=True)
        return {'results':results[:18],'errors':errors}

def normalize(value):
    value=unicodedata.normalize('NFKC',str(value)).casefold()
    return ' '.join(re.findall(r'\w+',value))

def metadata_db(uri):
    if not uri:raise RuntimeError('Configure MongoDB in bot settings first')
    return MongoClient(uri,serverSelectionTimeoutMS=5000)['sc_metadata']

def save_draft(uri, record, owner_id):
    from uuid import uuid4
    db=metadata_db(uri)
    draft={'draft_id':uuid4().hex[:16],'owner_id':owner_id,'metadata':record,'status':'draft','created_at':datetime.now(timezone.utc)}
    db.drafts.insert_one(draft)
    return draft['draft_id']

def list_drafts(uri, owner_id):
    return list(metadata_db(uri).drafts.find({'owner_id':owner_id,'status':'draft'},{'_id':0,'draft_id':1,'metadata.title':1}).sort('created_at',-1).limit(15))

def remove_draft(uri, draft_id, owner_id):
    return metadata_db(uri).drafts.delete_one({'draft_id':draft_id,'owner_id':owner_id,'status':'draft'}).deleted_count

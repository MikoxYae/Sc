"""Careful provider-based enrichment for already published Sc catalog records.

This module never downloads chapters or publishes records: it updates descriptive
metadata only, from confirmed close matches, and leaves Telegram references intact.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from .metadata_engine import MetadataEngine, normalize

LOG = logging.getLogger('Sc.catalog_metadata')
PROVIDER_PRIORITY = ('anilist', 'mangaupdates', 'mangadex')
MATCHED_TYPES = {
    'manga': 'Manga', 'manhwa': 'Manhwa', 'manhua': 'Manhua',
    'webtoon': 'Webtoon', 'adult_manga': 'Manga',
    'adult_manhwa': 'Manhwa', 'adult_webtoon': 'Webtoon',
}
# Use cover URLs from known provider artwork hosts; no arbitrary URL ingestion.
COVER_HOSTS = (
    's4.anilist.co', 'img.anili.st', 'uploads.mangadex.org',
    'mangaupdates.com', 'www.mangaupdates.com',
    'cdn.mangaupdates.com', 'images.mangaupdates.com',
)
REFRESH_AFTER = timedelta(days=14)
RETRY_AFTER = timedelta(hours=12)
LEASE_TIME = timedelta(minutes=5)

# A small, evidence-checked alias registry for titles distributed under translated
# or editorial names. Only aliases independently known to be the SAME work go here.
# Avoid fuzzy title joins (there is a similarly named unrelated web novel).
VERIFIED_ALIASES = {
    'adult_manhwa': {
        normalize('Milf Hunting in Another World Raw'): (
            'Isegye Milf Hunter', 'Isekai Milf Hunter', '이세계 밀프 헌터',
            'Milf Hunting in Another World', 'Milf Hunter in Another World',
        ),
        normalize('Milf Hunting in Another World'): (
            'Isegye Milf Hunter', 'Isekai Milf Hunter', '이세계 밀프 헌터',
            'Milf Hunting in Another World Raw', 'Milf Hunter in Another World',
        ),
    },
}
EDITORIAL_SUFFIX = re.compile(r'\s+(?:\((?:raw|english|eng|uncensored|official)\)|\[(?:raw|english|eng|uncensored|official)\]|(?:raw|english|eng|uncensored|official))\s*$', re.IGNORECASE)

def query_titles(title: str, category: str, extra_titles=()) -> list[str]:
    """Search names from the actual record, not fuzzy guesswork.

    Operator-approved alternative titles may be supplied for ANY catalog
    category. Every returned result must still exactly match one of these
    names and pass the compatible work-type check.
    """
    stem = title.strip()
    # Repeated editorial suffixes occur on scanlation distribution sites.
    for _ in range(3):
        cleaned = EDITORIAL_SUFFIX.sub('', stem).strip()
        if cleaned == stem:
            break
        stem = cleaned
    group = VERIFIED_ALIASES.get(category, {})
    known = group.get(normalize(title), ()) or group.get(normalize(stem), ())
    # An owner-confirmed alternative needs to be in the bounded query list,
    # even when the built-in alias registry contains many names.
    variants = []
    if isinstance(extra_titles, (tuple, list)):
        variants.extend(x for x in extra_titles if isinstance(x, str) and 2 <= len(x.strip()) <= 120)
    if known:
        variants.append(known[0])
    variants.extend((stem, title.strip()))
    variants.extend(known[1:])
    # Provider queries must be bounded and deduplicated to respect rate limits.
    result, used = [], set()
    for item in variants:
        item = item.strip()
        key = normalize(item)
        if not key or key in used:
            continue
        result.append(item)
        used.add(key)
        if len(result) >= 8:
            break
    return result

def exact_match_any(names: list[str], record: dict) -> bool:
    return any(exact_match(name, record) for name in names)


def valid_cover(url: str | None) -> bool:
    if not isinstance(url, str) or len(url) > 1800 or any(x in url for x in '\r\n\\'):
        return False
    try:
        parts = urlsplit(url)
        return (parts.scheme == 'https' and parts.hostname in COVER_HOSTS
                and not parts.username and not parts.password and parts.port in (None, 443))
    except ValueError:
        return False


def exact_match(title: str, record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    desired = normalize(title)
    candidates = [record.get('title'), record.get('original_title')]
    candidates.extend(record.get('alternative_titles') or [])
    return bool(desired and any(isinstance(n, str) and normalize(n) == desired for n in candidates))


def compatible_type(category: str, item: dict) -> bool:
    expected = MATCHED_TYPES.get(category)
    actual = item.get('type')
    # Some databases do not classify their titles. Do not infer an incompatible type.
    if expected is None:
        return False
    # For the confirmed translated title, do not accidentally bind a similarly
    # named web novel to an adult Manhwa entry.
    if category == 'adult_manhwa' and any(
            exact_match_any(list(aliases), item)
            for aliases in VERIFIED_ALIASES.get(category, {}).values()):
        return actual == 'Manhwa' or item.get('original_language') == 'ko'
    if actual in (None, 'Other', 'Unknown'):
        return True
    if expected == 'Webtoon':
        return actual in ('Webtoon', 'Manhwa', 'Manga', 'Manhua')
    return expected == actual


def same_work(primary: dict, alternate: dict, category: str | None = None) -> bool:
    """Only allow enrichment from an exact-title, compatible work.

    Cross-provider IDs (when present) are stronger; native-name clashes reject a
    merge. No heuristic merging of similarly named series.
    """
    names = [primary.get('title'), *(primary.get('alternative_titles') or [])]
    matched_name = any(isinstance(n, str) and exact_match(n, alternate) for n in names)
    if not matched_name and category:
        for aliases in VERIFIED_ALIASES.get(category, {}).values():
            group = list(aliases)
            if (exact_match_any(group, primary) and exact_match_any(group, alternate)):
                matched_name = True
                break
    if not matched_name:
        return False
    x = primary.get('original_language')
    y = alternate.get('original_language')
    if x and y and x != y:
        return False
    x = primary.get('original_title')
    y = alternate.get('original_title')
    if x and y and normalize(x) != normalize(y):
        return False
    ids_a = primary.get('sources') or {}
    ids_b = alternate.get('sources') or {}
    shared = set(ids_a) & set(ids_b)
    if any(ids_a[k] and ids_b[k] and str(ids_a[k]) != str(ids_b[k]) for k in shared):
        return False
    return True


def clean_description(text: str | None) -> str | None:
    if not isinstance(text, str):
        return None
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:4000] if len(text) > 25 else None


def normalize_lists(values, limit: int = 30) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    answer = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            continue
        name = re.sub(r'\s+', ' ', value).strip()[:110]
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            answer.append(name)
        if len(answer) >= limit:
            break
    return answer


def select_metadata(title: str, category: str, engine: MetadataEngine, *, extra_titles=()) -> dict:
    """Return candidate metadata and provenance without inventing missing fields."""
    if not 2 <= len(title.strip()) <= 120 or category not in MATCHED_TYPES:
        raise ValueError('Invalid title or category')
    candidates = []
    errors = []
    aliases = query_titles(title, category, extra_titles=extra_titles)
    for name in PROVIDER_PRIORITY:
        # Stop querying a provider as soon as we have a good cover and synopsis
        # from a matching record. Other providers remain fallback/enrichment.
        seen = set()
        for query in aliases[:5]:
            if normalize(query) in seen:
                continue
            seen.add(normalize(query))
            try:
                results = (engine.mangadex(query, include_adult=True)
                           if name == 'mangadex' and category.startswith('adult_')
                           else getattr(engine, name)(query))
                matches = [item for item in results if exact_match_any(aliases, item)
                           and compatible_type(category, item)]
                candidates.extend((name, item) for item in matches)
                if any(valid_cover(m.get('cover')) and clean_description(m.get('description'))
                       for m in matches):
                    break
            except Exception as exc:
                errors.append(f'{name}: {type(exc).__name__}')
                # A provider with network/API errors should not be called again
                # for every alias in this operation. Continue to next provider.
                break
        if any(valid_cover(item.get('cover')) and clean_description(item.get('description'))
               for _, item in candidates):
            # Poster and synopsis are now available. Avoid extra API requests.
            break
    if not candidates:
        return {'found': False, 'errors': errors,
                'reason': 'No verified exact-title match. Review the series title or provider IDs.'}
    unique_matches = {}
    for provider, item in candidates:
        identity = str((item.get('sources') or {}).get(provider) or
                       normalize(item.get('original_title') or item.get('title') or ''))
        unique_matches[(provider, identity)] = (provider, item)
    candidates = list(unique_matches.values())
    candidates.sort(key=lambda pair: PROVIDER_PRIORITY.index(pair[0]))
    # Multiple exact-title records from one provider are ambiguous even if the
    # original titles differ. Never guess which similarly named series is right.
    for provider in PROVIDER_PRIORITY:
        unique = {str((data.get('sources') or {}).get(provider) or data.get('original_title') or data.get('title'))
                  for p, data in candidates if p == provider}
        if len(unique) > 1:
            return {'found': False, 'errors': errors,
                    'reason': f'Ambiguous exact-title results in {provider}; manual review required.'}
    _, primary = candidates[0]
    # Known alias names are verified against the candidate and content type;
    # do not allow unrelated similarly named series to enrich each other.
    related = [(p, data) for p, data in candidates if same_work(primary, data, category)]
    if not related:
        related = [candidates[0]]
    values = {}
    field_sources = {}
    for key in ('cover_url', 'description', 'genres', 'tags', 'authors', 'artists',
                'status', 'alternative_titles', 'original_title', 'original_language',
                'year', 'rating'):
        for provider, item in related:
            field = {'cover_url': 'cover'}.get(key, key)
            raw = item.get(field)
            if key == 'cover_url':
                value = raw if valid_cover(raw) else None
            elif key == 'description':
                value = clean_description(raw)
            elif key in ('genres', 'tags', 'authors', 'artists', 'alternative_titles'):
                value = normalize_lists(raw)
            elif key == 'status':
                value = raw if raw not in ('Unknown', None, '') else None
            elif key == 'rating':
                value = raw if isinstance(raw, (int, float)) and 0 <= raw <= 100 else None
            elif key == 'year':
                value = raw if isinstance(raw, int) and 1850 <= raw <= 2150 else None
            else:
                value = raw if isinstance(raw, str) and raw.strip() else None
            if value is not None and value != []:
                values[key] = value
                field_sources[key] = provider
                break
    sources = {}
    source_urls = {}
    for p, item in related:
        sources.update({k: v for k, v in (item.get('sources') or {}).items() if v is not None})
        source_urls.update({k: v for k, v in (item.get('source_urls') or {}).items() if v})
    values.update({'metadata_sources': sources, 'metadata_source_urls': source_urls,
                   'metadata_field_sources': field_sources, 'metadata_match': 'verified_alias' if normalize(primary.get('title', '')) != normalize(title) else 'exact_title',
                   'metadata_updated_at': datetime.now(timezone.utc)})
    return {'found': True, 'values': values, 'errors': errors,
            'providers': list(dict.fromkeys(p for p, _ in related))}


def _due(doc: dict, force: bool) -> bool:
    if force:
        return True
    status = (doc.get('metadata_lookup') or {}).get('status')
    at = (doc.get('metadata_lookup') or {}).get('attempted_at')
    if isinstance(at, datetime):
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        gap = LEASE_TIME if status == 'running' else REFRESH_AFTER if status == 'matched' else RETRY_AFTER
        if datetime.now(timezone.utc) - at < gap:
            return False
    return True


def enrich_published_title(category: str, slug: str, *, engine=None,
                           force: bool = False, col=None) -> dict:
    """Atomic refresh of a published entry; never edits chapters or file IDs."""
    if category not in MATCHED_TYPES or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,130}', slug):
        raise ValueError('Invalid category/slug')
    if col is None:
        from .catalog_db import collection
        col = collection(category)
    if col is None:
        return {'status': 'unavailable', 'reason': 'MongoDB connection not configured'}
    criteria = {'slug': slug, 'published': True, 'chapters.0': {'$exists': True}}
    doc = col.find_one(criteria)
    if not doc:
        return {'status': 'missing'}
    if not _due(doc, force):
        return {'status': 'skipped'}
    # Claim using compare-and-set. Avoid concurrent publishing jobs repeating calls.
    now = datetime.now(timezone.utc)
    if doc.get('metadata_lookup'):
        filter_ = {**criteria, 'metadata_lookup': doc['metadata_lookup']}
    else:
        filter_ = {**criteria, 'metadata_lookup': {'$exists': False}}
    changed = col.update_one(filter_, {'$set': {'metadata_lookup': {'status': 'running', 'attempted_at': now}}})
    if not changed.modified_count:
        return {'status': 'skipped'}
    try:
        # Saved, owner-reviewed search names work in every manga / manhwa /
        # manhua / webtoon category (including all 18+ variants).
        verified_queries = doc.get('metadata_search_titles') or []
        # Alternative titles from earlier verified matches can help subsequent
        # refreshes after upstream name changes.
        verified_queries = list(verified_queries) + list(doc.get('alternative_titles') or [])
        outcome = select_metadata(doc['title'], category, engine or MetadataEngine(),
                                  extra_titles=verified_queries)
        if outcome['found']:
            values = outcome['values']
            # Keep owner-curated fields intact. Missing fields can be filled, and
            # existing automated values refreshed only when they are already marked
            # as provider-managed.
            # Only metadata that came from automated providers may be replaced.
            # Owner-curated synopsis and owner-uploaded covers always win.
            managed = {key for key, source in (doc.get('metadata_field_sources') or {}).items()
                       if source in PROVIDER_PRIORITY}
            changes = {k: v for k, v in values.items()
                       if k not in ('metadata_field_sources', 'metadata_sources',
                                    'metadata_source_urls', 'metadata_updated_at',
                                    'metadata_match')
                       and (not doc.get(k) or k in managed)}
            provenance = dict(doc.get('metadata_field_sources') or {})
            provenance.update({k: v for k, v in values['metadata_field_sources'].items()
                               if k in changes})
            changes.update({'metadata_field_sources': provenance,
                            'metadata_sources': values['metadata_sources'],
                            'metadata_source_urls': values['metadata_source_urls'],
                            'metadata_updated_at': values['metadata_updated_at'],
                            'metadata_match': values['metadata_match']})
            col.update_one(criteria, {'$set': {**changes,
                'metadata_lookup': {'status': 'matched', 'attempted_at': now,
                                    'providers': outcome['providers']}}})
            return {'status': 'matched', 'fields': sorted(changes),
                    'cover': bool(doc.get('cover_local') or changes.get('cover_url') or doc.get('cover_url')),
                    'synopsis': bool(changes.get('description') or doc.get('description')),
                    'providers': outcome['providers'], 'errors': outcome['errors']}
        else:
            col.update_one(criteria, {'$set': {'metadata_lookup': {
                'status': 'needs_review', 'attempted_at': now, 'reason': outcome['reason']}}})
            return {'status': 'needs_review', 'reason': outcome['reason'], 'errors': outcome['errors']}
    except Exception as exc:
        LOG.exception('Metadata enrichment failed for %s/%s', category, slug)
        col.update_one(criteria, {'$set': {'metadata_lookup': {
            'status': 'failed', 'attempted_at': now, 'reason': type(exc).__name__}}})
        return {'status': 'failed', 'reason': type(exc).__name__}

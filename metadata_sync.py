"""Backfill published cover art and synopsis from verified provider matches.

Examples:
  python3 metadata_sync.py --all
  python3 metadata_sync.py --category manhwa --slug why-i-quit-being-the-demon-king
  python3 metadata_sync.py --all --force
"""
import argparse
import logging
from catalog_db import CATEGORIES, collection
from catalog_metadata import enrich_published_title


def main(argv=None):
    parser = argparse.ArgumentParser(description='Enrich already-published title metadata (no PDF download)')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true', help='Scan every published category')
    group.add_argument('--category', choices=sorted(CATEGORIES), help='Published content category')
    parser.add_argument('--slug', help='Exact title slug; requires --category')
    parser.add_argument('--force', action='store_true', help='Refresh metadata even if recently checked')
    parser.add_argument('--limit', type=int, default=50, help='Max entries per category (1..100)')
    args = parser.parse_args(argv)
    if args.slug and not args.category:
        parser.error('--slug requires --category')
    if not 1 <= args.limit <= 100:
        parser.error('--limit must be between 1 and 100')
    cats = list(CATEGORIES) if args.all else [args.category]
    completed = 0
    for cat in cats:
        col = collection(cat)
        if col is None:
            print(f'{cat}: MongoDB is not configured; skipped')
            continue
        q = {'published': True, 'chapters.0': {'$exists': True}}
        if args.slug:
            q['slug'] = args.slug
        for doc in col.find(q, {'_id': 0, 'title': 1, 'slug': 1}).limit(args.limit):
            outcome = enrich_published_title(cat, doc['slug'], force=args.force, col=col)
            completed += 1
            print(f'{cat}/{doc["slug"]}: {outcome["status"]}', flush=True)
            if outcome['status'] in ('needs_review', 'failed'):
                print('  ' + outcome.get('reason', 'Unknown error')[:120], flush=True)
            elif outcome['status'] == 'matched':
                print('  providers=' + ','.join(outcome.get('providers', [])) + '; updated=' + ','.join(outcome.get('fields', [])), flush=True)
    print(f'Checked {completed} published titles; PDF and Telegram files unchanged.')


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')
    main()

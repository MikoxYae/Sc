"""Read-only publishing status for a single content category.

Example: .venv/bin/python3 publication_check.py --category adult_manhwa
Does not print Telegram IDs, secrets, or stored file references.
"""
import argparse
from .catalog_db import CATEGORIES, collection
from .publish_recovery import pending
from .storage_sync import selected_channel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--category', choices=sorted(CATEGORIES), default='adult_manhwa')
    args = parser.parse_args()
    print('Category:', args.category)
    print('Storage channel:', 'SET' if selected_channel(args.category) else 'NOT SET')
    print('Pending commits:', sum(bool(x.get('ready')) for x in pending(args.category)))
    col = collection(args.category)
    if col is None:
        print('MongoDB: NOT CONFIGURED')
        return 1
    try:
        count = col.count_documents({'published': True, 'chapters.0': {'$exists': True}})
        print('Published titles:', count)
        for item in col.find({'published': True, 'chapters.0': {'$exists': True}},
                             {'_id': 0, 'title': 1, 'chapters.number': 1}).sort('updated_at', -1).limit(8):
            print('Title:', str(item.get('title', ''))[:95],
                  '| chapters:', len(item.get('chapters', [])))
    except Exception as exc:
        print('MongoDB error:', type(exc).__name__)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

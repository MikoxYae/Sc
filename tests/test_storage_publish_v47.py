"""Offline regression tests for adult-category publishing and repair."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Test shim for optional MongoDB on machines without the production requirements.
try:
    import pymongo
except ModuleNotFoundError:
    import test_catalog_v44  # installs in-memory pymongo shim

import publish_recovery
import storage_sync
import catalog_db


class StorageRepairV47Tests(unittest.TestCase):
    def test_pdf_parser_supports_one_part_and_split_chapters(self):
        self.assertEqual(storage_sync.parse_pdf_name('Why I Quit Being the Demon King - Chapter 3.pdf'),
                         ('Why I Quit Being the Demon King', '3', 1, 1))
        self.assertEqual(storage_sync.parse_pdf_name('Some title - Ch 2.5 - Part 1 of 2.pdf'),
                         ('Some title', '2.5', 1, 2))
        self.assertIsNone(storage_sync.parse_pdf_name('randomfile.pdf'))
        self.assertIsNone(storage_sync.parse_pdf_name('Some title - Chapter 5 - Part 3 of 2.pdf'))

    def test_group_requires_complete_multipart_pdf(self):
        items = [(('Title A', '1', 1, 2), {'message_id': 11})]
        self.assertEqual(list(storage_sync.groups_from_messages(items)), [('Title A', '1', None)])
        items.append((('Title A', '1', 2, 2), {'message_id': 12}))
        self.assertEqual(list(storage_sync.groups_from_messages(items))[0][2],
                         [{'message_id': 11}, {'message_id': 12}])

    def test_pending_journal_is_private_replayable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'data' / 'pending.json'
            with patch.object(publish_recovery, 'JOURNAL', target):
                record = {'message_id': 77, 'filename': 'Safe - Chapter 1.pdf', 'file_id': 'ref'}
                publish_recovery.record('adult_manhwa', 'Safe', '1', 18, -1001234567890, [record], ready=True)
                self.assertEqual(len(publish_recovery.pending('adult_manhwa')), 1)
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)
                called = []
                def fake_save(*args):
                    called.append(args)
                with patch.object(catalog_db, 'save_published_chapter', side_effect=fake_save):
                    self.assertEqual(publish_recovery.replay('adult_manhwa', dry_run=False), (1, 0))
                    self.assertEqual(publish_recovery.replay('adult_manhwa', dry_run=False), (0, 0))
                self.assertEqual(called[0][0], 'adult_manhwa')
                self.assertEqual(len(publish_recovery.pending('adult_manhwa')), 0)

    def test_partials_are_not_published(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(publish_recovery, 'JOURNAL', Path(temp) / 'pending.json'):
                publish_recovery.record('adult_manhwa', 'Safe', '2', 0, -1001234567890,
                                        [{'message_id': 50}], ready=False)
                with patch.object(catalog_db, 'save_published_chapter') as f:
                    self.assertEqual(publish_recovery.replay('adult_manhwa', dry_run=False), (0, 0))
                    f.assert_not_called()

    def test_same_separate_category_storage(self):
        self.assertEqual(catalog_db.CATEGORIES['adult_manhwa'], 'sc_adult_manhwa')
        self.assertNotEqual(catalog_db.CATEGORIES['adult_manhwa'], catalog_db.CATEGORIES['manhwa'])

if __name__ == '__main__':
    unittest.main()

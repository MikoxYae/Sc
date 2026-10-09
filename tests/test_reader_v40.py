"""Reader job lifecycle regression tests (no network calls)."""
import sys, unittest, tempfile, time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import chapter_reader as r
except ModuleNotFoundError as exc:
    if exc.name != 'pymongo':
        raise
    import types
    sys.modules['catalog_db'] = types.SimpleNamespace(CATEGORIES={'manga':'sc_manga'}, collection=lambda _: None)
    import chapter_reader as r
class JobTests(unittest.TestCase):
    def test_running_job_is_not_requeued_when_expired(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(r, 'CACHE', Path(tmp)), patch.object(r, 'chapter_record', return_value={'documents':[{'message_id':1}]}), patch.object(r.WORKERS, 'submit') as submit:
            key=r.key_for('manga','example','1')
            with r.LOCK:
                r.RUNNING.add(key)
                r.JOBS[key]={'status':'processing','at':time.time()-r.JOB_TIMEOUT-10}
            try:
                value=r.prepare('manga','example','1')
                self.assertEqual(value['status'],'error')
                submit.assert_not_called()
            finally:
                with r.LOCK:
                    r.RUNNING.discard(key)
                    r.JOBS.pop(key,None)
    def test_missing_channel_reference(self):
        with patch.object(r, 'collection', return_value=None):
            with self.assertRaises(RuntimeError):r.chapter_record('manga','example','1')
if __name__=='__main__': unittest.main()

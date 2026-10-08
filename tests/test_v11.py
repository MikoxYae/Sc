import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
class V11Tests(unittest.TestCase):
    def test_compiles(self):
        for name in ('Miko.py','sc.py'):
            ast.parse((ROOT/name).read_text())
    def test_progress_and_format_controls(self):
        code=(ROOT/'Miko.py').read_text()
        for value in ('progress_text(', 'pdf_pic', 'rename_format', 'caption_style', 'timeout=12', 'filename_for(', 'reply_document('):
            self.assertIn(value,code)
    def test_no_secrets_bundled(self):
        self.assertFalse((ROOT/'config.py').exists())
if __name__=='__main__': unittest.main()

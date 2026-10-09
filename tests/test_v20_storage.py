import unittest
import ast
from pathlib import Path

class V20Checks(unittest.TestCase):
    def test_miko_syntax(self):
        ast.parse(Path('Miko.py').read_text())
    def test_server_reset_handling(self):
        s=Path('website_server.py').read_text()
        self.assertIn('ConnectionResetError',s)
        self.assertIn('QuietHTTPServer',s)
    def test_storage_settings(self):
        s=Path('Miko.py').read_text()
        self.assertIn("'storage_channel'",s)
        self.assertIn('save_mongo_uri',s)
        self.assertIn('get_chat_member',s)

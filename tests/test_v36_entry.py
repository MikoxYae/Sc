import ast
import pathlib
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
class PortTests(unittest.TestCase):
    def test_entrypoint(self):
        src = (ROOT / 'miko.py').read_text()
        ast.parse(src)
        self.assertIn('1276', src)
        self.assertIn('from Miko import main', src)
    def test_deployment(self):
        src = (ROOT / 'deploy' / 'setup_vps.sh').read_text()
        self.assertIn('127.0.0.1:1276', src)
        self.assertIn('/root/Sc/miko.py', src)
        self.assertIn('http://$IP:1276', src)

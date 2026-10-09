"""Offline package-layout guardrails so later updates do not regress imports."""
import ast
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'sc_core'


class RepositoryLayoutTests(unittest.TestCase):
    def test_only_one_root_python_launcher(self):
        self.assertEqual(sorted(p.name for p in ROOT.glob('*.py') if p.name != 'config.py'), ['miko.py'])
        self.assertTrue((ROOT/'requirements.txt').is_file())
        self.assertFalse((ROOT/'config.example.py').exists())
        self.assertFalse((ROOT/'semico.py').exists())

    def test_imports_and_subprocess_entrypoint(self):
        source = (PKG/'bot.py').read_text()
        self.assertIn("'-m', 'sc_core.scraper'", source)
        self.assertIn('ROOT = Path(__file__).resolve().parent.parent', source)
        for f in PKG.glob('*.py'):
            tree = ast.parse(f.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.level == 0:
                        self.assertNotIn(node.module, {'Miko', 'sc', 'catalog_db', 'website_server', 'site_adapters'})

    def test_private_data_paths_remain_at_root(self):
        self.assertIn('parent.parent', (PKG/'chapter_reader.py').read_text())
        self.assertIn('parent.parent', (PKG/'adult_access.py').read_text())
        self.assertIn('parent.parent', (PKG/'publish_recovery.py').read_text())
        self.assertIn("parent.parent/'website'", (PKG/'website_server.py').read_text())

    def test_launcher_and_internal_scraper_cli(self):
        output = subprocess.run([sys.executable, str(ROOT/'miko.py'), '--help'], capture_output=True, text=True, check=True, cwd=ROOT)
        self.assertIn('metadata-sync', output.stdout)
        result = subprocess.run([sys.executable, '-m', 'sc_core.scraper', '--help'], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()

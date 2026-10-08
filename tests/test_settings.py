import unittest
from pathlib import Path

class StructureTest(unittest.TestCase):
    def test_config_not_shipped(self):
        self.assertFalse((Path(__file__).parents[1] / 'config.py').exists())
    def test_menu_rows_max_two(self):
        source = (Path(__file__).parents[1] / 'Miko.py').read_text()
        self.assertIn('def keyboard(rows):', source)
        self.assertIn("'admin_add'", source)

if __name__ == '__main__': unittest.main()

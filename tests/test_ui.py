import ast
from pathlib import Path

def test_syntax():
    ast.parse((Path(__file__).resolve().parents[1] / 'Miko.py').read_text())

def test_ui_formatting():
    text = (Path(__file__).resolve().parents[1] / 'Miko.py').read_text()
    assert '<blockquote>' in text
    assert '<b>' in text
    assert "('Add Admin','admin_add')" in text

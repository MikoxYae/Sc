import ast
from pathlib import Path

def test_smallcaps_present():
    src = (Path(__file__).resolve().parents[1] / 'Miko.py').read_text(encoding='utf-8')
    ast.parse(src)
    assert "'a':'ᴀ'" in src
    assert 'smallcaps(label)' in src
    assert "BotCommand('start', smallcaps(" in src
    assert 'html.escape(smallcaps(title))' in src

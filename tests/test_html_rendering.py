import ast
from pathlib import Path


def test_html_card_messages_use_html_parse_mode():
    source = (Path(__file__).resolve().parents[1] / "Miko.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    funcs = {node.name: node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)}
    status_calls = [node for node in ast.walk(funcs["status"]) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "reply_text"]
    assert status_calls
    assert all(any(k.arg == "parse_mode" and isinstance(k.value, ast.Constant) and k.value.value == "HTML" for k in call.keywords) for call in status_calls)

def test_callback_alert_does_not_contain_html_card():
    source = (Path(__file__).resolve().parents[1] / "Miko.py").read_text(encoding="utf-8")
    assert "q.answer(card(" not in source

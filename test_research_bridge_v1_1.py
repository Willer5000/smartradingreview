from pathlib import Path

def test_bridge_is_read_only():
    root=Path(__file__).resolve().parent
    text=(root/'research_bridge.py').read_text()
    assert '.post(' not in text and '.patch(' not in text and '.delete(' not in text
    assert "READ_ONLY_BRIDGE" in text

def test_no_background_threads():
    text=(Path(__file__).resolve().parent/'research_bridge.py').read_text().lower()
    assert 'threading' not in text

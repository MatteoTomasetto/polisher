from polisher.diffview import word_diff
from polisher.history import History


def test_word_diff_marks_changes():
    ops = word_diff("The cat sat on the mat", "The cat sits on the rug")
    assert ("delete", "sat") in ops and ("insert", "sits") in ops
    assert ("delete", "mat") in ops and ("insert", "rug") in ops
    assert "".join(t for op, t in ops if op != "insert") == "The cat sat on the mat"
    assert "".join(t for op, t in ops if op != "delete") == "The cat sits on the rug"


def test_word_diff_identical():
    assert word_diff("same text", "same text") == [("equal", "same text")]


def test_history_roundtrip(tmp_path):
    h = History(tmp_path / "h.db")
    h.add(app="word", mode="polish", provider="ollama", original="a", result="b")
    h.add(app="word", mode="rephrase", provider="ollama", original="c", result="d")
    recent = h.recent()
    assert [e.original for e in recent] == ["c", "a"]
    assert h.get(recent[1].id).result == "b"
    h.clear()
    assert h.recent() == []

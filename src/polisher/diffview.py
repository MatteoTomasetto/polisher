"""Word-level diff used by the preview window."""
from __future__ import annotations

import difflib
import re

_TOKEN = re.compile(r"\s+|\w+|[^\w\s]", re.UNICODE)


def word_diff(old: str, new: str) -> list[tuple[str, str]]:
    """Return [(op, text)] where op is 'equal', 'delete' or 'insert'."""
    a, b = _TOKEN.findall(old), _TOKEN.findall(new)
    out: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            out.append(("equal", "".join(a[i1:i2])))
            continue
        if i2 > i1:
            out.append(("delete", "".join(a[i1:i2])))
        if j2 > j1:
            out.append(("insert", "".join(b[j1:j2])))
    return out


def similarity(old: str, new: str) -> float:
    """0..1, how much of the text survived. Low values mean a rewrite or translation."""
    a, b = _TOKEN.findall(old), _TOKEN.findall(new)
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def similarity(old: str, new: str) -> float:
    """0..1, how much of the text is unchanged (used to pick the default preview style)."""
    a, b = _TOKEN.findall(old), _TOKEN.findall(new)
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()

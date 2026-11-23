"""Hide LaTeX from the LLM so it can only edit the prose.

protect() swaps math, comments and non-text commands for opaque tokens such as @@L3@@,
restore() puts them back and returns None if the model dropped any token, so a mangled
formula never reaches your document.
"""
from __future__ import annotations

import re

_ENVS = "equation|align|gather|multline|flalign|alignat|eqnarray|displaymath|math"
# Commands whose arguments are keys/paths/URLs, not prose.
_NO_TEXT = (
    r"cite[a-zA-Z]*|[a-zA-Z]*ref|label|url|includegraphics|input|include|bibliography|"
    r"bibliographystyle|usepackage|documentclass|nocite|vspace|hspace|setlength|pagestyle"
)

_PATTERN = re.compile(
    r"(?P<comment>(?<!\\)%[^\n]*)"
    r"|(?P<env>\\begin\{(?P<envname>" + _ENVS + r")(?P<star>\*?)\}.*?"
    r"\\end\{(?P=envname)(?P=star)\})"
    r"|(?P<dd>\$\$.*?\$\$)"
    r"|(?P<brk>\\\[.*?\\\])"
    r"|(?P<par>\\\(.*?\\\))"
    r"|(?P<inline>(?<!\\)\$(?:\\.|[^$\\])+?\$)"
    r"|(?P<plain>\\(?:" + _NO_TEXT + r")\*?(?:\[[^\]]*\])*(?:\{[^}]*\})?)"
    r"|(?P<cmd>\\[a-zA-Z]+\*?(?:\[[^\]]*\])?)"
    r"|(?P<esc>\\[^a-zA-Z\s])",
    re.DOTALL,
)

_HINT = re.compile(
    r"\\[a-zA-Z]{2,}|\\begin\{"
    r"|(?<!\\)\$[^\s$]+\$"  # $x$
    r"|(?<!\\)\$[^$\n]*[\\^_{}=][^$\n]*\$"  # $a + b_1$
)


def looks_like_latex(text: str) -> bool:
    return bool(_HINT.search(text))


def protect(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}

    def swap(match: re.Match) -> str:
        token = f"@@L{len(mapping)}@@"
        mapping[token] = match.group(0)
        return token

    return _PATTERN.sub(swap, text), mapping


def restore(text: str, mapping: dict[str, str]) -> str | None:
    """Put the LaTeX back. Returns None if any protected token went missing."""
    if any(token not in text for token in mapping):
        return None
    for token, original in mapping.items():
        text = text.replace(token, original)
    return text

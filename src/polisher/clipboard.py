"""Read the current selection and write the result back, by simulating Copy / Paste."""
from __future__ import annotations

import sys
import time
import uuid

import pyperclip


class ClipboardError(Exception):
    pass


_controller = None


def _kb():
    global _controller
    if _controller is None:
        from pynput.keyboard import Controller

        _controller = Controller()
    return _controller


def _combo(char: str) -> None:
    from pynput.keyboard import Key

    kb = _kb()
    with kb.pressed(Key.cmd if sys.platform == "darwin" else Key.ctrl):
        kb.press(char)
        kb.release(char)


def read() -> str:
    try:
        return pyperclip.paste() or ""
    except pyperclip.PyperclipException:
        return ""


def write(text: str) -> None:
    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException as exc:
        raise ClipboardError(
            "No clipboard backend found. On Linux install xclip (X11) or wl-clipboard (Wayland)."
        ) from exc


def copy_selection(timeout: float = 0.9) -> str:
    """Press Copy and return what was selected ('' if nothing changed)."""
    sentinel = f"__polisher_{uuid.uuid4().hex}__"
    write(sentinel)
    _combo("c")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.025)
        current = read()
        if current != sentinel:
            return current
    return ""


def paste_text(text: str, settle: float = 0.3) -> None:
    write(text)
    time.sleep(0.05)
    _combo("v")
    time.sleep(settle)  # let the app read the clipboard before we restore it

"""Global hotkeys, one code path per platform family.

Windows: a low-level hook detects the combo and swallows the key, so the app never sees it
(Ctrl+P would not open Print). Linux and macOS: pynput's listener; the key still reaches the
app, so pick a combo the app doesn't use. On macOS letters are matched by physical key
position (ANSI/QWERTY), because Option and Control change the character a key produces.
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable

_MODIFIERS = {
    "ctrl": "ctrl", "control": "ctrl",
    "shift": "shift",
    "alt": "alt", "option": "alt", "opt": "alt",
    "cmd": "cmd", "command": "cmd", "win": "cmd", "super": "cmd", "meta": "cmd",
}

_WIN_NAMED = {"space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B}

# macOS virtual key codes (kVK_ANSI_*), i.e. physical key positions.
_MAC_VK = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11,
    "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21,
    "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29, "o": 31, "u": 32, "i": 34, "p": 35,
    "l": 37, "j": 38, "k": 40, "n": 45, "m": 46, "space": 49,
}


def parse_hotkey(spec: str) -> tuple[frozenset[str], str]:
    """'ctrl+alt+p' -> (frozenset({'ctrl', 'alt'}), 'p')."""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError(f"hotkey '{spec}' needs at least one modifier plus a key")
    *mods, key = parts
    try:
        normalized = frozenset(_MODIFIERS[m] for m in mods)
    except KeyError as exc:
        raise ValueError(f"unknown modifier {exc} in hotkey '{spec}'") from None
    if key in _MODIFIERS:
        raise ValueError(f"hotkey '{spec}' must end with a normal key")
    return normalized, key


def win_vk(key: str) -> int:
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return 0x6F + int(key[1:])
    if key in _WIN_NAMED:
        return _WIN_NAMED[key]
    raise ValueError(f"unsupported key '{key}' for Windows hotkeys")


def _modifier_name(key) -> str | None:
    base = (getattr(key, "name", "") or "").split("_")[0]
    return base if base in ("ctrl", "shift", "alt", "cmd") else None


class Hotkeys:
    def __init__(self, bindings: dict[str, Callable[[], None]]):
        self._bindings: dict[tuple[frozenset[str], str], Callable[[], None]] = {}
        for spec, callback in bindings.items():
            if spec:
                parsed = parse_hotkey(spec)
                if parsed in self._bindings:
                    raise ValueError(f"hotkey '{spec}' is assigned twice")
                self._bindings[parsed] = callback
        self._down: set[str] = set()
        self._suppressed: set[int] = set()
        # Ignore OS key-repeat events until the triggering key is released.
        self._active_combos: set[tuple[frozenset[str], str]] = set()
        self._listener = None

    # -- public -------------------------------------------------------------
    def start(self) -> None:
        from pynput import keyboard

        kwargs = {"win32_event_filter": self._win_filter} if sys.platform == "win32" else {}
        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release, **kwargs
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()

    def wait_for_release(self, timeout: float = 1.2) -> None:
        """Block until the modifier keys are up, so our simulated Ctrl+C isn't polluted."""
        deadline = time.monotonic() + timeout
        while self._down and time.monotonic() < deadline:
            time.sleep(0.01)

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _threaded(callback: Callable[[], None]) -> Callable[[], None]:
        def run() -> None:
            threading.Thread(target=callback, daemon=True).start()
        return run

    def _on_press(self, key) -> None:
        if (mod := _modifier_name(key)) is not None:
            self._down.add(mod)
            return
        if sys.platform == "win32":
            return  # handled (and swallowed) in _win_filter
        mods = frozenset(self._down)
        for (wanted, name), callback in self._bindings.items():
            combo = (wanted, name)
            if mods == wanted and self._key_matches(key, name) and combo not in self._active_combos:
                self._active_combos.add(combo)
                self._threaded(callback)()

    def _on_release(self, key) -> None:
        if (mod := _modifier_name(key)) is not None:
            self._down.discard(mod)
        else:
            # Clear only the matching key; a repeated key-down cannot open a second menu.
            for combo in tuple(self._active_combos):
                if self._key_matches(key, combo[1]):
                    self._active_combos.discard(combo)

    @staticmethod
    def _key_matches(key, name: str) -> bool:
        if getattr(key, "name", None) == name:  # named keys such as f5, space
            return True
        if sys.platform == "darwin":
            vk = getattr(key, "vk", None)
            return vk is not None and _MAC_VK.get(name) == vk
        char = getattr(key, "char", None)
        return char is not None and char.lower() == name

    def _win_mods(self) -> frozenset[str]:
        import ctypes

        state = ctypes.windll.user32.GetAsyncKeyState
        mods = set()
        if state(0x11) & 0x8000:
            mods.add("ctrl")
        if state(0x10) & 0x8000:
            mods.add("shift")
        if state(0x12) & 0x8000:
            mods.add("alt")
        if state(0x5B) & 0x8000 or state(0x5C) & 0x8000:
            mods.add("cmd")
        return frozenset(mods)

    def _win_filter(self, msg, data):
        if data.flags & 0x10:  # injected by us (simulated Ctrl+C / Ctrl+V)
            return True
        if msg in (0x100, 0x104):  # key down
            mods = self._win_mods()
            for (wanted, key), callback in self._bindings.items():
                if data.vkCode == win_vk(key) and mods == wanted:
                    if data.vkCode not in self._suppressed:
                        self._suppressed.add(data.vkCode)
                        self._threaded(callback)()
                    self._listener.suppress_event()
        elif msg in (0x101, 0x105) and data.vkCode in self._suppressed:  # key up
            self._suppressed.discard(data.vkCode)
            self._listener.suppress_event()
        return True

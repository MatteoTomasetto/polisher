import sys
from types import SimpleNamespace as K

import pytest

from polisher.hotkeys import Hotkeys, parse_hotkey, win_vk


def test_parse():
    assert parse_hotkey("Ctrl+Alt+P") == (frozenset({"ctrl", "alt"}), "p")
    assert parse_hotkey("win+shift+z")[0] == {"cmd", "shift"}


@pytest.mark.parametrize("bad", ["p", "", "ctrl", "ctrl+shift", "hyper+p"])
def test_rejects_bad_hotkeys(bad):
    with pytest.raises(ValueError):
        parse_hotkey(bad)


def test_duplicate_hotkeys_rejected():
    with pytest.raises(ValueError):
        Hotkeys({"ctrl+alt+p": lambda: None, "alt+ctrl+p": lambda: None})


def test_windows_virtual_keys():
    assert win_vk("p") == 0x50 and win_vk("5") == 0x35
    assert win_vk("f1") == 0x70 and win_vk("f12") == 0x7B and win_vk("space") == 0x20


def make(hits):
    hk = Hotkeys({"ctrl+alt+p": lambda: hits.append("polish"), "ctrl+alt+m": lambda: hits.append("menu")})
    hk._threaded = lambda cb: cb  # run callbacks synchronously in tests
    return hk


CTRL, ALT, SHIFT = K(name="ctrl_l"), K(name="alt_l"), K(name="shift")


def test_linux_matching_by_character(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    hits = []
    hk = make(hits)
    for key in (CTRL, ALT):
        hk._on_press(key)
    hk._on_press(K(char="p", vk=112))
    hk._on_press(K(char="M", vk=109))  # uppercase still matches
    hk._on_press(K(char="x", vk=120))
    assert hits == ["polish", "menu"]
    hk._on_release(ALT)
    hk._on_press(K(char="p", vk=112))
    assert hits == ["polish", "menu"]  # alt released: no match


def test_extra_modifier_does_not_trigger(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    hits = []
    hk = make(hits)
    for key in (CTRL, ALT, SHIFT):
        hk._on_press(key)
    hk._on_press(K(char="p"))
    assert hits == []


def test_macos_matches_physical_key_even_when_option_changes_the_char(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    hits = []
    hk = make(hits)
    hk._on_press(CTRL)
    hk._on_press(ALT)
    hk._on_press(K(char="\u03c0", vk=35))  # option+p produces the pi sign, vk is still P
    hk._on_press(K(char="\x0d", vk=46))    # ctrl+m gives a control character, vk is still M
    assert hits == ["polish", "menu"]


def test_wait_for_release_returns_when_keys_up():
    hk = Hotkeys({})
    hk._down = {"ctrl"}
    hk.wait_for_release(timeout=0.05)  # times out instead of hanging
    hk._down.clear()
    hk.wait_for_release(timeout=5)

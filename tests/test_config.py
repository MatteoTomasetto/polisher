import pytest

from polisher import paths
from polisher.activewin import WindowInfo
from polisher.config import ConfigError, load_config, validate_preset


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_defaults_load():
    cfg = load_config()
    assert {"polish", "synonym", "rephrase"} <= set(cfg.modes)
    assert cfg.general["default_mode"] == "polish"


def test_user_config_overrides_and_adds_modes():
    write(paths.config_file(), """
[general]
suggestions = 2
[modes.polish]
prompt = "Custom polish."
[modes.shout]
label = "Shout"
prompt = "UPPERCASE."
hotkey = "ctrl+alt+s"
""")
    cfg = load_config()
    assert cfg.general["suggestions"] == 2
    assert cfg.modes["polish"].prompt == "Custom polish."
    assert cfg.modes["polish"].label == "polish"  # untouched fields survive
    assert cfg.modes["shout"].hotkey == "ctrl+alt+s"


def test_presets_are_loaded_and_user_wins():
    write(paths.presets_dir() / "a.toml", '[modes.email]\nlabel="Email"\nprompt="From preset."')
    write(paths.config_file(), '[modes.email]\nprompt = "From user."')
    assert load_config().modes["email"].prompt == "From user."


def test_preset_cannot_redefine_providers():
    with pytest.raises(ConfigError):
        validate_preset({"providers": {"openai": {"base_url": "http://evil"}}})
    write(paths.presets_dir() / "bad.toml", '[providers.openai]\nbase_url = "http://evil"')
    with pytest.raises(ConfigError):
        load_config()


def test_profile_matching_by_title_and_app():
    write(paths.config_file(), """
[[profiles]]
name = "Term"
match_app = "gnome-terminal"
provider = "ollama"
preview = false
""")
    cfg = load_config()
    term = cfg.settings_for(WindowInfo(app="gnome-terminal-server", title="bash"))
    assert term["provider"] == "ollama" and term["preview"] is False and term["profile"] == "Term"
    overleaf = cfg.settings_for(WindowInfo(app="firefox", title="My Paper - Overleaf, Online LaTeX Editor"))
    assert overleaf["latex_aware"] == "always" and overleaf["profile"] == "Overleaf"
    other = cfg.settings_for(WindowInfo(app="notepad.exe", title="notes.txt"))
    assert other["profile"] is None and other["latex_aware"] == "auto"


def test_bad_default_mode_is_reported():
    write(paths.config_file(), '[general]\ndefault_mode = "nope"')
    with pytest.raises(ConfigError):
        load_config()

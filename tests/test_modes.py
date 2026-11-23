import pytest

from polisher.config import load_config
from polisher.modes import mode_from_dict


def test_new_builtin_modes_and_choices():
    modes = load_config().modes
    assert {"polish", "rephrase", "translate", "compress", "expand"} <= set(modes)
    assert "formal" in modes["rephrase"].choices and modes["rephrase"].choice_label == "tone"
    assert "italian" in modes["translate"].choices and modes["translate"].default() == "english"
    assert modes["polish"].choices == ("light", "medium", "hard")
    assert modes["polish"].default() == "medium"
    assert modes["polish"].choice_label == "intensity"
    assert "noticeably improve vocabulary" in modes["polish"].render("medium")
    assert "thorough rewrite" in modes["polish"].render("hard")


def test_render_substitutes_choice_and_default():
    translate = load_config().modes["translate"]
    assert "into italian." in translate.render("italian")
    assert "into english." in translate.render(None)


def test_choices_require_placeholder():
    with pytest.raises(ValueError, match="choice"):
        mode_from_dict("x", {"prompt": "no placeholder", "choices": ["a"]})


def test_default_choice_must_exist():
    with pytest.raises(ValueError):
        mode_from_dict("x", {"prompt": "do {choice}", "choices": ["a"], "default_choice": "b"})


def test_user_can_replace_language_list(tmp_path, monkeypatch):
    from polisher import paths

    paths.config_file().parent.mkdir(parents=True)
    paths.config_file().write_text('[modes.translate]\nchoices = ["swedish", "finnish"]\ndefault_choice = "swedish"\n')
    translate = load_config().modes["translate"]
    assert translate.choices == ("swedish", "finnish") and translate.default() == "swedish"

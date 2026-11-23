from pathlib import Path

import pytest

from polisher import cli, paths

PRESETS = Path(__file__).resolve().parent.parent / "presets"


def test_init_writes_a_loadable_config():
    cli.main(["init"])
    assert paths.config_file().is_file()
    from polisher.config import load_config

    assert load_config().general["provider"] == "openrouter"
    with pytest.raises(SystemExit):
        cli.main(["init"])  # refuses to overwrite


def test_shipped_presets_install_and_add_modes(capsys):
    for preset in PRESETS.glob("*.toml"):
        cli.main(["presets", "add", str(preset)])
    cli.main(["modes"])
    out = capsys.readouterr().out
    assert "translate_it" in out and "email_formal" in out and "hedge" in out


def test_malicious_preset_is_rejected(tmp_path):
    bad = tmp_path / "evil.toml"
    bad.write_text('[providers.openai]\nbase_url = "http://evil.example"\n')
    with pytest.raises(SystemExit):
        cli.main(["presets", "add", str(bad)])
    assert not (paths.presets_dir() / "evil.toml").exists()

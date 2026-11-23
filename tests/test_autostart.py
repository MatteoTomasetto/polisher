from pathlib import Path

from polisher import autostart


def test_install_remove_and_status(monkeypatch, tmp_path):
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    monkeypatch.delenv("POLISHER_HOME", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(autostart.shutil, "which", lambda _: "/home/test/.local/bin/polisher")

    target = autostart.install()
    assert target == tmp_path / "config/autostart/polisher.desktop"
    assert autostart.is_installed()
    content = target.read_text()
    assert "Exec=/home/test/.local/bin/polisher run" in content
    assert "X-GNOME-Autostart-enabled=true" in content
    assert autostart.remove()
    assert not autostart.is_installed()
    assert not autostart.remove()


def test_install_falls_back_to_python_module(monkeypatch, tmp_path):
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(autostart.shutil, "which", lambda _: None)
    target = autostart.install()
    assert f"{autostart.sys.executable} -m polisher run" in target.read_text()


def test_unsupported_platform(monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    import pytest
    with pytest.raises(RuntimeError, match="Linux only"):
        autostart.install()

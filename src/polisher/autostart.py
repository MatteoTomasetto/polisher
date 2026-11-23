"""Install/remove a per-user desktop autostart entry (Linux/XDG)."""
from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path


def desktop_file() -> Path:
    override = os.environ.get("POLISHER_HOME")
    if override:
        config_home = Path(override).expanduser() / "config"
    else:
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")).expanduser()
    return config_home / "autostart" / "polisher.desktop"


def install() -> Path:
    if not sys.platform.startswith("linux"):
        raise RuntimeError("Automatic desktop startup is currently supported on Linux only.")
    executable = shutil.which("polisher")
    if executable:
        command = f"{shlex.quote(executable)} run"
    else:
        command = f"{shlex.quote(sys.executable)} -m polisher run"
    target = desktop_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Polisher\n"
        "Comment=Global text polishing shortcuts\n"
        f"Exec={command}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "StartupNotify=false\n"
    )
    target.write_text(content, encoding="utf-8")
    target.chmod(0o644)
    return target


def remove() -> bool:
    target = desktop_file()
    if target.exists():
        target.unlink()
        return True
    return False


def is_installed() -> bool:
    return desktop_file().is_file()

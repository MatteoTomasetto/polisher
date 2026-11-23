"""Where Polisher keeps its config and data. Set POLISHER_HOME to override both."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _override() -> Path | None:
    value = os.environ.get("POLISHER_HOME")
    return Path(value).expanduser() if value else None


def config_dir() -> Path:
    if (home := _override()) is not None:
        return home / "config"
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "polisher"


def data_dir() -> Path:
    if (home := _override()) is not None:
        return home / "data"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "polisher"


def config_file() -> Path:
    return config_dir() / "config.toml"


def presets_dir() -> Path:
    return config_dir() / "presets"


def history_file() -> Path:
    return data_dir() / "history.db"

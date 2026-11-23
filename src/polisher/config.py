"""Load defaults -> presets -> config.toml, and resolve per-app settings."""
from __future__ import annotations

import copy
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .activewin import WindowInfo
from .modes import BUILTIN_MODES, Mode, mode_from_dict


class ConfigError(Exception):
    pass


def default_hotkeys() -> dict[str, str]:
    # Same on Windows, Linux and macOS. Ctrl+P is avoided on purpose: it means Print almost
    # everywhere (and "previous line" on macOS). Ctrl+Alt+letter is free in nearly every app.
    return {"polish": "ctrl+alt+p", "menu": "ctrl+alt+m"}


def _defaults() -> dict:
    return {
        "general": {
            "provider": "openrouter",
            "default_mode": "polish",
            "suggestions": 3,
            "preview": True,         # menu: show a diff and let you choose
            "quick_preview": False,  # polish hotkey: replace right away (use your app's undo)
            "latex_aware": "auto",
            "history": True,
        },
        "hotkeys": default_hotkeys(),
        "providers": {
            "anthropic": {"model": "claude-haiku-5-5", "api_key_env": "ANTHROPIC_API_KEY"},
            "openrouter": {
                "kind": "openai",
                "model": "openrouter/free",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key_env": "OPENROUTER_API_KEY",
            },
            "openai": {
                "model": "gpt-4o-mini",
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
            "ollama": {"model": "llama3.1", "base_url": "http://localhost:11434"},
        },
    }


DEFAULT_PROFILES: list[dict] = [
    {"name": "Overleaf", "match_title": "overleaf", "latex_aware": "always"},
    {"name": "TeX editor", "match_title": r"\.tex\b", "latex_aware": "always"},
]

_PROFILE_META = {"name", "match_title", "match_app"}


@dataclass
class Config:
    general: dict
    hotkeys: dict
    providers: dict
    modes: dict[str, Mode]
    profiles: list[dict] = field(default_factory=list)

    def settings_for(self, window: WindowInfo | None) -> dict:
        """General settings with the first matching profile applied on top."""
        settings = dict(self.general)
        settings["profile"] = None
        if window is None:
            return settings
        for profile in self.profiles:
            if _profile_matches(profile, window):
                settings.update({k: v for k, v in profile.items() if k not in _PROFILE_META})
                settings["profile"] = profile.get("name", "unnamed")
                break
        return settings


def _profile_matches(profile: dict, window: WindowInfo) -> bool:
    title_re, app_re = profile.get("match_title"), profile.get("match_app")
    if not title_re and not app_re:
        return False
    if title_re and not re.search(title_re, window.title or "", re.IGNORECASE):
        return False
    if app_re and not re.search(app_re, window.app or "", re.IGNORECASE):
        return False
    return True


def read_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def validate_preset(data: dict) -> None:
    """Presets may only add modes and profiles (never providers, keys or URLs)."""
    extra = set(data) - {"modes", "profiles", "meta"}
    if extra:
        raise ConfigError(f"presets may only contain modes and profiles, found: {sorted(extra)}")
    for key, mode in (data.get("modes") or {}).items():
        if not isinstance(mode, dict):
            raise ConfigError(f"mode '{key}' must be a table")
        if key not in BUILTIN_MODES and not isinstance(mode.get("prompt"), str):
            raise ConfigError(f"mode '{key}' needs a text 'prompt'")
        if "choices" in mode and not (
            isinstance(mode["choices"], list) and all(isinstance(c, str) for c in mode["choices"])
        ):
            raise ConfigError(f"mode '{key}': 'choices' must be a list of strings")
    for profile in data.get("profiles") or []:
        if not isinstance(profile, dict) or not (
            profile.get("match_title") or profile.get("match_app")
        ):
            raise ConfigError("every profile needs match_title or match_app")


def _merge_modes(target: dict[str, dict], source: dict | None) -> None:
    for key, mode in (source or {}).items():
        merged = {**target.get(key, {}), **mode}
        target[key] = merged


def load_config(path: Path | None = None, *, with_presets: bool = True) -> Config:
    cfg = _defaults()
    mode_dicts: dict[str, dict] = copy.deepcopy(BUILTIN_MODES)
    profiles: list[dict] = []

    if with_presets and paths.presets_dir().is_dir():
        for preset in sorted(paths.presets_dir().glob("*.toml")):
            data = read_toml(preset)
            try:
                validate_preset(data)
            except ConfigError as exc:
                raise ConfigError(f"{preset.name}: {exc}") from exc
            _merge_modes(mode_dicts, data.get("modes"))
            profiles = list(data.get("profiles") or []) + profiles

    user_path = path or paths.config_file()
    if user_path.is_file():
        user = read_toml(user_path)
        for section in ("general", "hotkeys"):
            cfg[section].update(user.get(section) or {})
        for name, values in (user.get("providers") or {}).items():
            cfg["providers"].setdefault(name, {}).update(values)
        _merge_modes(mode_dicts, user.get("modes"))
        profiles = list(user.get("profiles") or []) + profiles

    try:
        modes = {key: mode_from_dict(key, data) for key, data in mode_dicts.items()}
    except (ValueError, TypeError) as exc:
        raise ConfigError(str(exc)) from exc

    general = cfg["general"]
    if general["default_mode"] not in modes:
        raise ConfigError(f"default_mode '{general['default_mode']}' is not a defined mode")
    if general["provider"] not in cfg["providers"]:
        raise ConfigError(f"provider '{general['provider']}' is not configured")

    return Config(
        general=general,
        hotkeys=cfg["hotkeys"],
        providers=cfg["providers"],
        modes=modes,
        profiles=profiles + copy.deepcopy(DEFAULT_PROFILES),
    )

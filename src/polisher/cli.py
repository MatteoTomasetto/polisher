"""Command line entry point: `polisher` (run), `polisher test`, `polisher history`, ..."""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from importlib import resources
from pathlib import Path

from . import __version__, paths
from .config import ConfigError, load_config, read_toml, validate_preset


def _load():
    try:
        return load_config()
    except ConfigError as exc:
        sys.exit(f"Config error: {exc}")


def cmd_run(args) -> None:
    cfg = _load()
    try:
        from .ui import UI
    except ImportError:
        sys.exit("Tkinter is missing. On Debian/Ubuntu: sudo apt install python3-tk")
    from .app import App

    app = App(cfg, UI())
    h = cfg.hotkeys
    print(f"Polisher {__version__} is running. Provider: {cfg.general['provider']}")
    print(f"  {h.get('polish') or '(off)':<14} {cfg.general['default_mode']} the selection, one result, replaced right away")
    print(f"  {h.get('menu') or '(off)':<14} open the menu with every mode")
    print("To undo a replacement use the app's own undo (Ctrl+Z, or Cmd+Z on macOS).")
    print("Press Ctrl+C here to quit.")
    app.run()


def cmd_init(args) -> None:
    target = paths.config_file()
    if target.exists() and not args.force:
        sys.exit(f"{target} already exists (use --force to overwrite).")
    target.parent.mkdir(parents=True, exist_ok=True)
    example = resources.files("polisher").joinpath("config.example.toml")
    target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Wrote {target}")


def cmd_config_path(args) -> None:
    print(paths.config_file())


def cmd_modes(args) -> None:
    cfg = _load()
    for key, mode in cfg.modes.items():
        extra = f"  [{mode.hotkey}]" if mode.hotkey else ""
        picks = f"  {mode.choice_label}: {', '.join(mode.choices)}" if mode.choices else ""
        print(f"{key:<14} {mode.label}{extra}{picks}")


def cmd_test(args) -> None:
    from .engine import Engine, EngineError

    cfg = _load()
    text = args.text if args.text is not None else sys.stdin.read()
    if args.mode not in cfg.modes:
        sys.exit(f"Unknown mode '{args.mode}'. Try: polisher modes")
    settings = dict(cfg.general)
    if args.provider:
        settings["provider"] = args.provider
    try:
        options = Engine(cfg).run(
            text, cfg.modes[args.mode], settings, choice=args.choice,
            n=args.suggestions,
        )
    except EngineError as exc:
        sys.exit(f"Error: {exc}")
    for i, option in enumerate(options, 1):
        print(f"--- option {i} ---\n{option}")


def cmd_history(args) -> None:
    from .history import History

    history = History()
    if args.clear:
        history.clear()
        print("History cleared.")
        return
    if args.restore is not None:
        entry = history.get(args.restore)
        if entry is None:
            sys.exit(f"No history entry #{args.restore}")
        import pyperclip

        pyperclip.copy(entry.original)
        print(f"Copied the original text of #{entry.id} to the clipboard.")
        return
    for e in history.recent(args.limit):
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.ts))
        print(f"#{e.id}  {when}  {e.mode}  ({e.app})")
        print(f"   - {e.original[:100]!r}\n   + {e.result[:100]!r}")


def cmd_presets(args) -> None:
    target_dir = paths.presets_dir()
    if args.action == "list":
        found = sorted(target_dir.glob("*.toml")) if target_dir.is_dir() else []
        print("\n".join(p.name for p in found) or "No presets installed.")
        return
    source = args.source
    if not source:
        sys.exit("Usage: polisher presets add FILE_OR_URL")
    if source.startswith(("http://", "https://")):
        import httpx

        try:
            response = httpx.get(source, timeout=15, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            sys.exit(f"Download failed: {exc}")
        name, content = Path(source.split("?")[0]).name, response.text
    else:
        src = Path(source).expanduser()
        if not src.is_file():
            sys.exit(f"File not found: {src}")
        name, content = src.name, src.read_text(encoding="utf-8")
    if not name.endswith(".toml"):
        name += ".toml"
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / Path(name).name
    dest.write_text(content, encoding="utf-8")
    try:
        validate_preset(read_toml(dest))
        load_config()
    except ConfigError as exc:
        dest.unlink(missing_ok=True)
        sys.exit(f"Rejected preset: {exc}")
    print(f"Installed {dest.name}. Run `polisher modes` to see what it added.")


def cmd_doctor(args) -> None:
    ok = lambda flag: "ok  " if flag else "FAIL"  # noqa: E731
    print(f"Polisher {__version__} on {sys.platform}, Python {sys.version.split()[0]}")
    try:
        import tkinter  # noqa: F401
        print(f"[{ok(True)}] tkinter")
    except ImportError:
        print(f"[{ok(False)}] tkinter missing (Debian/Ubuntu: sudo apt install python3-tk)")
    try:
        import pyperclip

        pyperclip.copy("polisher-check")
        print(f"[{ok(pyperclip.paste() == 'polisher-check')}] clipboard")
    except Exception as exc:
        print(f"[{ok(False)}] clipboard: {exc}")
    try:
        import pynput.keyboard  # noqa: F401
        print(f"[{ok(True)}] pynput (keyboard hooks)")
    except Exception as exc:
        print(f"[{ok(False)}] pynput: {str(exc).splitlines()[-1]}")
    if sys.platform.startswith("linux"):
        import os

        if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
            print("[WARN] Wayland session: global hotkeys and key simulation are restricted. Use an X11 session.")
        print(f"[{ok(bool(shutil.which('xdotool')))}] xdotool (per-app profiles)")
    if sys.platform == "darwin":
        print("[INFO] macOS: grant Accessibility permission to your terminal in System Settings > Privacy & Security.")
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"[{ok(False)}] config: {exc}")
        return
    print(f"[{ok(True)}] config ({paths.config_file()} {'found' if paths.config_file().exists() else 'not found, using defaults'})")
    name = cfg.general["provider"]
    pcfg = cfg.providers[name]
    needs_key = name == "anthropic" or ("api.openai.com" in pcfg.get("base_url", ""))
    if needs_key:
        import os

        has_key = bool(pcfg.get("api_key") or os.environ.get(pcfg.get("api_key_env", ""), ""))
        print(f"[{ok(has_key)}] API key for '{name}' ({pcfg.get('api_key_env')})")
    else:
        print(f"[INFO] provider '{name}' at {pcfg.get('base_url')} (no key needed)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="polisher", description="Polish text anywhere with an LLM.")
    parser.add_argument("--version", action="version", version=f"polisher {__version__}")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("run", help="start the background app (default)").set_defaults(func=cmd_run)
    p = sub.add_parser("init", help="write a commented config file")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)
    sub.add_parser("config-path", help="print the config file location").set_defaults(func=cmd_config_path)
    sub.add_parser("modes", help="list available modes").set_defaults(func=cmd_modes)
    sub.add_parser("doctor", help="check that everything needed is installed").set_defaults(func=cmd_doctor)
    p = sub.add_parser("test", help="run a mode on some text without the GUI")
    p.add_argument("text", nargs="?", help="text to edit (reads stdin if omitted)")
    p.add_argument("--mode", default="polish")
    p.add_argument("--choice", help="tone or language for modes that have choices (e.g. --mode translate --choice italian)")
    p.add_argument("--provider")
    p.add_argument("--suggestions", type=int)
    p.set_defaults(func=cmd_test)
    p = sub.add_parser("history", help="show, restore or clear the local history")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--restore", type=int, metavar="ID", help="copy that entry's original text to the clipboard")
    p.add_argument("--clear", action="store_true")
    p.set_defaults(func=cmd_history)
    p = sub.add_parser("presets", help="install or list shared prompt presets")
    p.add_argument("action", choices=["add", "list"])
    p.add_argument("source", nargs="?", help="file path or URL of a preset .toml")
    p.set_defaults(func=cmd_presets)

    args = parser.parse_args(argv)
    (args.func if args.cmd else cmd_run)(args)

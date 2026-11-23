"""Glue: hotkey -> capture selection -> LLM -> (menu / preview) -> paste."""
from __future__ import annotations

import threading
import time
import traceback

from . import clipboard
from .activewin import get_active_window, reactivate
from .config import Config
from .engine import Engine, EngineError
from .history import History
from .hotkeys import Hotkeys
from .ui import Item


class App:
    def __init__(self, cfg: Config, ui, engine: Engine | None = None, history: History | None = None):
        self.cfg, self.ui = cfg, ui
        self.engine = engine or Engine(cfg)
        if history is None and cfg.general.get("history", True):
            history = History()
        self.history = history
        self._lock = threading.Lock()
        self._last_choice: dict[str, str] = {}  # remembered per mode while the app runs
        self._last_popup_pos = (40, 40)

        bindings = {
            cfg.hotkeys.get("polish", ""): lambda: self.trigger(),
            cfg.hotkeys.get("menu", ""): lambda: self.trigger(menu=True),
        }
        for key, mode in cfg.modes.items():
            if mode.hotkey:
                bindings[mode.hotkey] = lambda k=key: self.trigger(mode_key=k)
        self.hotkeys = Hotkeys(bindings)

    def run(self) -> None:
        self.hotkeys.start()
        try:
            self.ui.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self.hotkeys.stop()

    def trigger(self, *, mode_key: str | None = None, menu: bool = False) -> None:
        """menu=False is the quick path: one result, pasted straight away."""
        if not self._lock.acquire(blocking=False):
            return  # already working on something
        try:
            self._process(mode_key, menu)
        except (EngineError, clipboard.ClipboardError) as exc:
            self._show_error(str(exc))
        except Exception as exc:  # never let a hotkey thread die silently
            traceback.print_exc()
            self._show_error(f"error: {exc}")
        finally:
            self._lock.release()

    def _show_error(self, message: str) -> None:
        """Show failures at the popup/menu location instead of the screen corner."""
        show = getattr(self.ui, "show_error", None)
        if show:
            show(message, self._last_popup_pos, 9000)
        else:  # compatibility with small test/fake UIs
            self.ui.toast(message, 9000)

    def _pick_choice(self, mode, pos) -> str | None:
        last = self._last_choice.get(mode.key) or mode.default()
        start = mode.choices.index(last) if last in mode.choices else 0
        choice = self.ui.pick(
            f"{mode.label.lower()} · {mode.choice_label}",
            [Item(c, c) for c in mode.choices], pos, start=start, allow_custom=True,
        )
        if choice:
            self._last_choice[mode.key] = choice
        return choice

    def _process(self, mode_key: str | None, menu: bool) -> None:
        window = get_active_window()
        settings = self.cfg.settings_for(window)
        self.hotkeys.wait_for_release()
        previous = clipboard.read()
        try:
            text = clipboard.copy_selection()
            if not text.strip():
                self.ui.toast("select some text first")
                return

            pos = self.ui.pointer()
            self._last_popup_pos = pos
            choice = None
            if menu:
                items = [Item(k, m.label, submenu=bool(m.choices)) for k, m in self.cfg.modes.items()]
                mode_key = self.ui.pick("polisher", items, pos)
                if mode_key is None:
                    return
                mode = self.cfg.modes[mode_key]
                if mode.choices:
                    choice = self._pick_choice(mode, pos)
                    if choice is None:
                        return
                count, preview = None, settings.get("preview", True)
            else:
                mode = self.cfg.modes[mode_key or settings["default_mode"]]
                choice = mode.default() if mode.choices else None
                count = settings.get("quick_suggestions", 1)
                preview = settings.get("quick_preview", False)

            self.ui.show_busy(f"{mode.label}...", pos)
            try:
                options = self.engine.run(text, mode, settings, n=count, choice=choice)
            finally:
                self.ui.hide_busy()

            if preview:
                chosen = self.ui.review(text, options, f"{mode.label} · {choice}" if choice else mode.label)
            else:
                chosen = options[0]
            if chosen is None or chosen == text:
                return
            if menu or preview:  # our windows had focus: hand it back before pasting
                reactivate(window)
                time.sleep(0.25)

            clipboard.paste_text(chosen)  # one paste = one undo step in the app
            if self.history is not None:
                self.history.add(
                    app=window.app or window.title,
                    mode=f"{mode.key}:{choice}" if choice else mode.key,
                    provider=settings.get("provider", ""), original=text, result=chosen,
                )
        finally:
            clipboard.write(previous)

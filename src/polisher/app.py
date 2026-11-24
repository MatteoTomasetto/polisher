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
from .modes import Mode
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
            self._show_status("polisher is already working", self._last_popup_pos)
            return
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

    def _show_status(self, message: str, pos=None) -> None:
        show = getattr(self.ui, "show_status", None)
        if show:
            show(message, pos or self._last_popup_pos, 2600)
        else:
            self.ui.toast(message, 2600)

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
                self._show_status("select some text first", self._last_popup_pos)
                return

            pos = self.ui.pointer()
            self._last_popup_pos = pos
            choice = None
            if menu:
                items = [Item(k, m.label, submenu=bool(m.choices)) for k, m in self.cfg.modes.items()]
                items.append(Item("__custom_prompt__", "custom prompt"))
                mode_key = self.ui.pick("polisher", items, pos)
                if mode_key is None:
                    return
                if mode_key == "__custom_prompt__":
                    prompt = self.ui.ask_prompt(pos)
                    if prompt is None or not prompt.strip():
                        return
                    mode = Mode(key="custom_prompt", label="custom prompt", prompt=prompt.strip())
                else:
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

            busy_labels = {
                "polish": "polishing...", "rephrase": "rephrasing...",
                "translate": "translating...", "compress": "compressing...",
                "expand": "expanding...", "synonym": "finding synonyms...",
                "custom_prompt": "applying custom prompt...",
            }
            self.ui.show_busy(busy_labels.get(mode.key, f"working on {mode.label}..."), pos)
            try:
                options = self.engine.run(text, mode, settings, n=count, choice=choice)
            finally:
                self.ui.hide_busy()

            if preview:
                chosen = self.ui.review(text, options, f"{mode.label} · {choice}" if choice else mode.label)
            else:
                chosen = options[0]
            if chosen is None:
                self._show_status("cancelled — original text kept", pos)
                return
            if chosen.strip() == text.strip():
                self._show_status("no changes suggested — original text kept", pos)
                return

            # The popup/preview may have taken keyboard focus. Explicitly reactivate the
            # original application before sending the paste keystroke on every platform.
            reactivate(window)
            time.sleep(0.30)
            clipboard.paste_text(chosen)  # one paste = one undo step in the app
            if self.history is not None:
                self.history.add(
                    app=window.app or window.title,
                    mode=f"{mode.key}:{choice}" if choice else mode.key,
                    provider=settings.get("provider", ""), original=text, result=chosen,
                )
            self._show_status("text replaced", pos)
        finally:
            clipboard.write(previous)

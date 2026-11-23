"""Minimal Tk interface: a type-to-filter menu, busy indicator, toasts and the diff preview.

Tk must live on the main thread, so the hotkey worker thread talks to it through a queue:
ask() runs a builder on the Tk thread and blocks until the window reports a result.
All of the interface's own text is lowercase on purpose.
"""
from __future__ import annotations

import queue
import tkinter as tk
from concurrent.futures import Future
from tkinter import font as tkfont
from typing import Callable

from .diffview import similarity, word_diff

BG, EDGE, HILITE, PANEL = "#141519", "#2b2e36", "#1f222a", "#101114"
FG, DIM, ACCENT = "#d9dce3", "#6e7380", "#9aa8ff"
DEL_FG, INS_FG, INS_BG = "#f28b82", "#9fe3b0", "#16291d"
_FAMILIES = ("Inter", "SF Pro Text", "Segoe UI", "Ubuntu", "Cantarell", "Helvetica Neue", "DejaVu Sans")

# (mode key, label, choices, choice label) -> returns (mode key, choice or None)
MenuItem = tuple[str, str, list[str], str]


class UI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("polisher")
        installed = set(tkfont.families(self.root))
        family = next((f for f in _FAMILIES if f in installed),
                      tkfont.nametofont("TkDefaultFont").actual("family"))
        self.font = tkfont.Font(root=self.root, family=family, size=11)
        self.small = tkfont.Font(root=self.root, family=family, size=9)
        self._jobs: queue.Queue = queue.Queue()
        self._busy: tk.Toplevel | None = None
        self.root.after(25, self._pump)

    # -- thread plumbing ------------------------------------------------------
    def mainloop(self) -> None:
        self.root.mainloop()

    def _pump(self) -> None:
        try:
            while True:
                builder, future = self._jobs.get_nowait()

                def done(value, future=future):
                    if future is not None and not future.done():
                        future.set_result(value)

                try:
                    builder(self.root, done)
                except Exception as exc:  # report to the waiting worker instead of dying
                    if future is not None and not future.done():
                        future.set_exception(exc)
        except queue.Empty:
            pass
        self.root.after(25, self._pump)

    def ask(self, builder: Callable):
        future: Future = Future()
        self._jobs.put((builder, future))
        return future.result()

    def post(self, builder: Callable) -> None:
        self._jobs.put((builder, None))

    def pointer(self) -> tuple[int, int]:
        return self.ask(lambda root, done: done(root.winfo_pointerxy()))

    def quit(self) -> None:
        self.post(lambda root, done: root.quit())

    # -- window helpers ---------------------------------------------------------
    def _borderless(self, root) -> tk.Toplevel:
        win = tk.Toplevel(root)
        win.configure(bg=EDGE)  # shows as a 1px border around the inner frame
        if root.tk.call("tk", "windowingsystem") == "aqua":
            try:  # overrideredirect windows can't take keyboard focus on macOS
                root.tk.call("::tk::unsupported::MacWindowStyle", "style", win, "plain", "none")
            except tk.TclError:
                win.overrideredirect(True)
        else:
            win.overrideredirect(True)
        win.attributes("-topmost", True)
        return win

    @staticmethod
    def _place(win: tk.Toplevel, x: int, y: int) -> None:
        win.update_idletasks()
        width, height = win.winfo_reqwidth(), win.winfo_reqheight()
        x = max(0, min(x, win.winfo_screenwidth() - width))
        y = max(0, min(y, win.winfo_screenheight() - height))
        win.geometry(f"+{x}+{y}")

    # -- menu ---------------------------------------------------------------------
    def pick_mode(self, items: list[MenuItem], pos: tuple[int, int]) -> tuple[str, str | None] | None:
        return self.ask(lambda root, done: _Palette(self, root, pos, items, done))

    # -- busy indicator and toasts ----------------------------------------------
    def show_busy(self, message: str, pos: tuple[int, int]) -> None:
        def build(root, done):
            self._hide_busy()
            win = self._borderless(root)
            tk.Label(win, text=message, bg=BG, fg=DIM, font=self.small, padx=12, pady=6).pack(padx=1, pady=1)
            self._place(win, pos[0] + 14, pos[1] + 18)
            self._busy = win

        self.post(build)

    def hide_busy(self) -> None:
        self.post(lambda root, done: self._hide_busy())

    def _hide_busy(self) -> None:
        if self._busy is not None:
            try:
                self._busy.destroy()
            except tk.TclError:
                pass
            self._busy = None

    def toast(self, message: str, ms: int = 2600) -> None:
        def build(root, done):
            win = self._borderless(root)
            tk.Label(win, text=message, bg=BG, fg=FG, font=self.small, padx=14, pady=8,
                     wraplength=380, justify="left").pack(padx=1, pady=1)
            self._place(win, win.winfo_screenwidth(), win.winfo_screenheight() - 90)
            win.after(ms, lambda: win.winfo_exists() and win.destroy())

        self.post(build)

    # -- diff preview ---------------------------------------------------------------
    def review(self, original: str, options: list[str], title: str) -> str | None:
        return self.ask(lambda root, done: self._build_review(root, done, original, options, title))

    def _build_review(self, root, done, original: str, options: list[str], title: str) -> None:
        win = tk.Toplevel(root)
        win.title(f"polisher - {title}")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        width, height = 640, 400
        win.geometry(f"{width}x{height}+{(win.winfo_screenwidth() - width) // 2}"
                     f"+{(win.winfo_screenheight() - height) // 3}")

        state = {"index": 0, "closed": False, "changes": similarity(original, options[0]) >= 0.45}
        tabs: list[tk.Label] = []

        top = tk.Frame(win, bg=BG)
        top.pack(fill="x", padx=16, pady=(14, 6))
        foot = tk.Frame(win, bg=BG)
        foot.pack(side="bottom", fill="x", padx=16, pady=(6, 14))
        body = tk.Text(win, wrap="word", bg=PANEL, fg=FG, font=self.font, relief="flat",
                       padx=16, pady=14, borderwidth=0, highlightthickness=0, spacing2=3)
        body.pack(fill="both", expand=True, padx=16)
        body.tag_configure("delete", foreground=DEL_FG, overstrike=True)
        body.tag_configure("insert", foreground=INS_FG, background=INS_BG)

        def close(value):
            if state["closed"]:
                return
            state["closed"] = True
            try:
                win.destroy()
            except tk.TclError:
                pass
            done(value)

        def render():
            candidate = options[state["index"]]
            body.configure(state="normal")
            body.delete("1.0", "end")
            if candidate.strip() == original.strip():
                body.insert("end", "no changes suggested for this text")
            elif state["changes"]:
                for op, chunk in word_diff(original, candidate):
                    body.insert("end", chunk, () if op == "equal" else (op,))
            else:
                body.insert("end", candidate)
            body.configure(state="disabled")
            for i, tab in enumerate(tabs):
                tab.configure(fg=ACCENT if i == state["index"] else DIM)
            toggle.configure(fg=ACCENT if state["changes"] else DIM)

        def select(i):
            if 0 <= i < len(options):
                state["index"] = i
                render()

        def toggle_changes():
            state["changes"] = not state["changes"]
            render()

        def link(parent, text, command, fg=DIM, **pack):
            label = tk.Label(parent, text=text, bg=BG, fg=fg, font=self.small, cursor="hand2")
            label.pack(**pack)
            label.bind("<Button-1>", lambda e: command())
            return label

        tk.Label(top, text=title, bg=BG, fg=DIM, font=self.small).pack(side="left", padx=(0, 14))
        if len(options) > 1:
            for i in range(len(options)):
                tabs.append(link(top, str(i + 1), lambda i=i: select(i), side="left", padx=5))
        toggle = link(top, "changes", toggle_changes, side="right")

        hint = "enter replace   esc cancel   d changes"
        if len(options) > 1:
            hint += f"   1-{len(options)} switch"
        tk.Label(foot, text=hint, bg=BG, fg=DIM, font=self.small).pack(side="left")
        link(foot, "replace", lambda: close(options[state["index"]]), fg=ACCENT, side="right", padx=(14, 0))
        link(foot, "cancel", lambda: close(None), side="right")

        def on_key(event):
            if event.keysym == "Escape":
                close(None)
            elif event.keysym in ("Return", "KP_Enter"):
                close(options[state["index"]])
            elif event.char == "d":
                toggle_changes()
            elif event.char.isdigit() and event.char != "0":
                select(int(event.char) - 1)

        win.bind("<Key>", on_key)
        win.protocol("WM_DELETE_WINDOW", lambda: close(None))
        render()
        win.after(10, lambda: (win.lift(), win.focus_force()))


class _Palette:
    """The popup menu: type to filter, 1-9 to jump, arrows/enter, right arrow opens a sub-step."""

    MAX_ROWS = 12

    def __init__(self, ui: UI, root, pos, items: list[MenuItem], done) -> None:
        self.ui, self.pos, self.items, self.done = ui, pos, items, done
        self.parent: MenuItem | None = None  # set while choosing a tone / language
        self.query, self.index, self.closed = "", 0, False
        self.rows: list[tuple[str, str, bool, bool]] = []

        self.win = ui._borderless(root)
        card = tk.Frame(self.win, bg=BG)
        card.pack(padx=1, pady=1)
        head = tk.Frame(card, bg=BG)
        head.pack(fill="x", padx=14, pady=(10, 8))
        self.crumb = tk.Label(head, bg=BG, fg=DIM, font=ui.font)
        self.typed = tk.Label(head, bg=BG, fg=FG, font=ui.font)
        self.caret = tk.Label(head, text="|", bg=BG, fg=ACCENT, font=ui.font)
        self.hint = tk.Label(head, bg=BG, fg=DIM, font=ui.small)
        for widget in (self.crumb, self.typed, self.caret, self.hint):
            widget.pack(side="left")
        tk.Frame(card, bg=EDGE, height=1).pack(fill="x")
        self.listing = tk.Frame(card, bg=BG)
        self.listing.pack(fill="x", pady=(4, 6))

        self.win.bind("<Key>", self.on_key)
        self.win.after(400, lambda: self.win.bind(
            "<FocusOut>", lambda e: self.close(None) if e.widget is self.win else None))
        self.win.after(20000, lambda: self.close(None))  # never leave a stuck popup behind
        self.render()
        self.win.after(10, self.win.focus_force)

    # -- data ---------------------------------------------------------------------
    def compute_rows(self) -> list[tuple[str, str, bool, bool]]:
        """[(value, label, opens_submenu, is_custom)] for the current page and filter."""
        if self.parent is None:
            pool = [(key, label, bool(choices)) for key, label, choices, _ in self.items]
        else:
            pool = [(c, c, False) for c in self.parent[2]]
        q = self.query.strip().lower()
        if q:
            starts = [r for r in pool if r[1].lower().startswith(q)]
            pool = starts + [r for r in pool if q in r[1].lower() and r not in starts]
        rows = [(v, label, sub, False) for v, label, sub in pool[: self.MAX_ROWS]]
        if self.parent is not None and q and not any(r[1].lower() == q for r in rows):
            rows.append((self.query.strip(), f"use {self.query.strip()}", False, True))
        return rows

    def render(self) -> None:
        self.rows = self.compute_rows()
        self.index = max(0, min(self.index, len(self.rows) - 1))
        if self.parent is None:
            self.crumb.configure(text="polisher " if not self.query else "")
        else:
            self.crumb.configure(text=f"{self.parent[1].lower()} / {self.parent[3] or 'choose'} ")
        self.typed.configure(text=self.query)
        self.hint.configure(text=" type to filter" if not self.query and self.parent is None else "")

        for child in self.listing.winfo_children():
            child.destroy()
        self.widgets: list[tuple[tk.Frame, list[tk.Label], tk.Frame]] = []
        for i, (_, label, sub, custom) in enumerate(self.rows):
            row = tk.Frame(self.listing, bg=BG, cursor="hand2")
            row.pack(fill="x")
            bar = tk.Frame(row, bg=BG, width=2)
            bar.pack(side="left", fill="y")
            number = str(i + 1) if (not self.query and i < 9) else ""
            parts = [
                tk.Label(row, text=number, width=2, bg=BG, fg=DIM, font=self.ui.small, anchor="e"),
                tk.Label(row, text=label.lower() if not custom else label, bg=BG, fg=FG,
                         font=self.ui.font, anchor="w", width=20, pady=3),
                tk.Label(row, text="›" if sub else "", bg=BG, fg=DIM, font=self.ui.font, width=2),
            ]
            for part in parts:
                part.pack(side="left", padx=(6, 0) if part is parts[0] else 0)
            for widget in (row, *parts):
                widget.bind("<Button-1>", lambda e, i=i: self.choose(i))
                widget.bind("<Enter>", lambda e, i=i: self.move_to(i))
            self.widgets.append((row, parts, bar))
        self.paint()
        self.ui._place(self.win, self.pos[0], self.pos[1] + 14)

    def paint(self) -> None:
        for i, (row, parts, bar) in enumerate(self.widgets):
            selected = i == self.index
            colour = HILITE if selected else BG
            row.configure(bg=colour)
            for part in parts:
                part.configure(bg=colour)
            bar.configure(bg=ACCENT if selected else BG)

    # -- actions ------------------------------------------------------------------
    def move_to(self, i: int) -> None:
        if i != self.index and 0 <= i < len(self.widgets):
            self.index = i
            self.paint()

    def choose(self, i: int) -> None:
        if not 0 <= i < len(self.rows):
            return
        value, _, sub, _ = self.rows[i]
        if self.parent is None and sub:
            self.parent = next(item for item in self.items if item[0] == value)
            self.query, self.index = "", 0
            self.render()
        elif self.parent is None:
            self.close((value, None))
        else:
            self.close((self.parent[0], value))

    def back(self) -> None:
        if self.parent is not None:
            self.parent, self.query, self.index = None, "", 0
            self.render()

    def close(self, value) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self.done(value)

    def on_key(self, event) -> None:
        key = event.keysym
        if key == "Escape":
            self.close(None)
        elif key in ("Return", "KP_Enter"):
            self.choose(self.index)
        elif key == "Down":
            self.move_to((self.index + 1) % max(1, len(self.rows)))
        elif key == "Up":
            self.move_to((self.index - 1) % max(1, len(self.rows)))
        elif key in ("Right", "Tab"):
            if self.rows and self.rows[self.index][2]:
                self.choose(self.index)
        elif key == "Left":
            self.back()
        elif key == "BackSpace":
            if self.query:
                self.query, self.index = self.query[:-1], 0
                self.render()
            else:
                self.back()
        elif event.char and event.char.isprintable():
            if event.char in "123456789" and not self.query and int(event.char) <= len(self.rows):
                self.choose(int(event.char) - 1)
            else:
                self.query, self.index = self.query + event.char, 0
                self.render()

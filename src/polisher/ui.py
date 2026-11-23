"""Minimal Tk interface: a lowercase popup menu, a busy hint, toasts and a diff preview.

Tk must live on the main thread, so the hotkey worker talks to it through a queue:
ask() runs a builder on the Tk thread and blocks until the window reports a result.
"""
from __future__ import annotations

import queue
import sys
import tkinter as tk
import tkinter.font as tkfont
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Callable

from .diffview import similarity, word_diff

BG, PANEL, BORDER, ROW = "#16171b", "#121317", "#2c2e35", "#22242a"
FG, MUTED, ACCENT = "#d9dbe1", "#6c717c", "#8fb4ff"
DEL_FG, INS_FG, INS_BG = "#f08a8a", "#8fe3b0", "#14281d"

_FONT_CANDIDATES = (
    "SF Pro Text", ".AppleSystemUIFont", "Segoe UI Variable Text", "Segoe UI",
    "Inter", "Cantarell", "Noto Sans", "DejaVu Sans",
)


@dataclass(frozen=True)
class Item:
    value: str
    label: str
    submenu: bool = False  # shows a "›" hint: picking it opens a second step


class UI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        available = set(tkfont.families(self.root))
        family = next((f for f in _FONT_CANDIDATES if f in available),
                      tkfont.nametofont("TkDefaultFont").actual("family"))
        self.font, self.small = (family, 11), (family, 9)
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
                except Exception as exc:  # hand the error to the waiting worker
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

    # -- helpers ----------------------------------------------------------------
    @staticmethod
    def _borderless(root, interactive: bool = False) -> tk.Toplevel:
        """Undecorated window. Passive ones (busy hint, toast) never take focus from your app;
        interactive ones (the menu) must be able to receive keystrokes."""
        win = tk.Toplevel(root)
        if interactive and sys.platform == "darwin":
            try:  # a borderless window that can still become the key window
                win.tk.call("::tk::unsupported::MacWindowStyle", "style", win._w, "plain", "none")
            except tk.TclError:
                win.overrideredirect(True)
        else:
            win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.97)
        except tk.TclError:
            pass
        win.configure(bg=BORDER)
        return win

    @staticmethod
    def _place(win: tk.Toplevel, x: int, y: int) -> None:
        win.update_idletasks()
        width, height = win.winfo_reqwidth(), win.winfo_reqheight()
        x = max(0, min(x, win.winfo_screenwidth() - width))
        y = max(0, min(y, win.winfo_screenheight() - height))
        win.geometry(f"+{x}+{y}")

    @staticmethod
    def _win_foreground(win: tk.Toplevel) -> None:
        """Windows only: a background process may not take the foreground unless it briefly
        attaches to the input queue of the current foreground window."""
        import ctypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        foreground = user32.GetForegroundWindow()
        this_thread = kernel32.GetCurrentThreadId()
        other = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        attach = bool(other) and other != this_thread
        if attach:
            user32.AttachThreadInput(this_thread, other, True)
        try:
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            if attach:
                user32.AttachThreadInput(this_thread, other, False)

    @staticmethod
    def _grab_focus(win: tk.Toplevel, grab: bool = True) -> None:
        """Get keyboard focus for a window, trying a few times after it appears.

        Linux: Tk never gives X11 focus to borderless windows (and its own focus_get() can
        claim we have it), so a global grab routes the keyboard to the popup until it closes.
        Windows / macOS: best effort, see README; the mouse always works.
        """
        def attempt() -> None:
            try:
                if not win.winfo_exists():
                    return
                win.lift()
                win.focus_force()
                if sys.platform == "win32":
                    UI._win_foreground(win)
                elif grab and sys.platform.startswith("linux"):
                    win.grab_set_global()
            except Exception:
                pass

        if sys.platform == "darwin":
            import os
            import subprocess

            try:
                subprocess.Popen(
                    ["osascript", "-e", 'tell application "System Events" to set frontmost of '
                     f"(first process whose unix id is {os.getpid()}) to true"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except OSError:
                pass
        for delay in (10, 60, 130, 250, 450):
            win.after(delay, attempt)

    # -- popup menu ------------------------------------------------------------------
    def pick(self, title: str, items: list[Item], pos: tuple[int, int], *, start: int = 0,
             allow_custom: bool = False) -> str | None:
        """Show a small menu near pos. Keys: arrows, enter, esc, 1-9, or type to filter.

        With allow_custom, whatever you type can be chosen as a free-text value.
        Returns the chosen value, or None if dismissed.
        """
        def build(root, done):
            win = self._borderless(root, interactive=True)
            inner = tk.Frame(win, bg=BG)
            inner.pack(padx=1, pady=1)
            header = tk.Label(inner, text=title, bg=BG, fg=MUTED, font=self.small, anchor="w",
                              padx=16, width=28)
            header.pack(fill="x", pady=(12, 6))
            body = tk.Frame(inner, bg=BG)
            body.pack(fill="x", padx=6, pady=(0, 8))
            state = {"query": "", "index": start, "closed": False, "visible": [], "rows": []}

            def close(value):
                if state["closed"]:
                    return
                state["closed"] = True
                try:
                    win.destroy()
                except tk.TclError:
                    pass
                done(value)

            def visible() -> list[Item]:
                q = state["query"].strip().lower()
                if not q:
                    return list(items)
                found = [it for it in items if q in it.label.lower()]
                found.sort(key=lambda it: not it.label.lower().startswith(q))
                if allow_custom and not any(it.label.lower() == q for it in found):
                    found.append(Item(state["query"].strip(), f'use "{q}"'))
                return found

            def choose(i):
                if 0 <= i < len(state["visible"]):
                    close(state["visible"][i].value)

            def paint():
                for i, (row, bar, label, hint) in enumerate(state["rows"]):
                    selected = i == state["index"]
                    shade = ROW if selected else BG
                    for widget in (row, label, hint):
                        widget.configure(bg=shade)
                    bar.configure(bg=ACCENT if selected else shade)

            def hover(i):
                state["index"] = i
                paint()

            def render():
                for child in body.winfo_children():
                    child.destroy()
                state["rows"] = []
                state["visible"] = visible()
                state["index"] = max(0, min(state["index"], len(state["visible"]) - 1))
                header.configure(text=f"{title}  ›  {state['query']}" if state["query"] else title)
                if not state["visible"]:
                    tk.Label(body, text="no match", bg=BG, fg=MUTED, font=self.font,
                             anchor="w", padx=14, pady=6).pack(fill="x")
                for i, item in enumerate(state["visible"]):
                    row = tk.Frame(body, bg=BG, cursor="hand2")
                    bar = tk.Frame(row, width=2, bg=BG)
                    bar.pack(side="left", fill="y")
                    label = tk.Label(row, text=item.label.lower(), bg=BG, fg=FG, font=self.font,
                                     anchor="w", padx=12, pady=5)
                    label.pack(side="left", fill="x", expand=True)
                    hint_text = "›" if item.submenu else (str(i + 1) if i < 9 else "")
                    hint = tk.Label(row, text=hint_text, bg=BG, fg=MUTED, font=self.small, padx=12)
                    hint.pack(side="right")
                    row.pack(fill="x")
                    for widget in (row, bar, label, hint):
                        widget.bind("<Button-1>", lambda e, i=i: choose(i))
                        widget.bind("<Enter>", lambda e, i=i: hover(i))
                    state["rows"].append((row, bar, label, hint))
                paint()
                self._place(win, pos[0], pos[1] + 12)

            def on_key(event):
                key = event.keysym
                if key == "Escape":
                    close(None)
                elif key in ("Return", "KP_Enter"):
                    choose(state["index"])
                elif key == "Down" and state["visible"]:
                    hover((state["index"] + 1) % len(state["visible"]))
                elif key == "Up" and state["visible"]:
                    hover((state["index"] - 1) % len(state["visible"]))
                elif key == "BackSpace":
                    state["query"] = state["query"][:-1]
                    render()
                elif event.char and event.char.isdigit() and not state["query"]:
                    choose(int(event.char) - 1)
                elif event.char and event.char.isprintable() and (event.char != " " or state["query"]):
                    state["query"] += event.char
                    state["index"] = 0
                    render()

            def on_click(event):  # with the grab, clicks outside the popup arrive here
                inside = (0 <= event.x_root - win.winfo_rootx() < win.winfo_width()
                          and 0 <= event.y_root - win.winfo_rooty() < win.winfo_height())
                if not inside:
                    close(None)

            win.bind("<Key>", on_key)
            win.bind("<Button-1>", on_click, add="+")
            win.after(400, lambda: win.bind(
                "<FocusOut>", lambda e: close(None) if e.widget is win else None))
            win.after(30000, lambda: close(None))  # never leave a stuck popup behind
            render()
            self._grab_focus(win)

        return self.ask(build)

    # -- busy hint and toasts ---------------------------------------------------------
    def show_busy(self, message: str, pos: tuple[int, int]) -> None:
        def build(root, done):
            self._hide_busy()
            win = self._borderless(root)
            tk.Label(win, text=message.lower(), bg=BG, fg=MUTED, font=self.small,
                     padx=12, pady=6).pack(padx=1, pady=1)
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
            tk.Label(win, text=message.lower(), bg=BG, fg=FG, font=self.font, padx=16, pady=10,
                     wraplength=380, justify="left").pack(padx=1, pady=1)
            self._place(win, win.winfo_screenwidth(), win.winfo_screenheight() - 90)
            win.after(ms, lambda: win.winfo_exists() and win.destroy())

        self.post(build)

    def show_error(self, message: str, pos: tuple[int, int], ms: int = 9000) -> None:
        """Show an actionable error popup where the menu appeared; dismiss on click/Esc."""
        def build(root, done):
            win = self._borderless(root)
            panel = tk.Frame(win, bg=BG)
            panel.pack(padx=1, pady=1)
            tk.Label(panel, text="polisher · error", bg=BG, fg="#f08a8a", font=self.small,
                     anchor="w", padx=14, pady=(10, 4)).pack(fill="x")
            tk.Label(panel, text=message, bg=BG, fg=FG, font=self.font, padx=14, pady=6,
                     wraplength=430, justify="left", anchor="w").pack(fill="x")
            hint = tk.Label(panel, text="click or press esc to dismiss", bg=BG, fg=MUTED,
                            font=self.small, anchor="e", padx=14, pady=(4, 9))
            hint.pack(fill="x")
            def close(_event=None):
                if win.winfo_exists():
                    win.destroy()
            win.bind("<Button-1>", close)
            win.bind("<Escape>", close)
            self._place(win, pos[0] + 14, pos[1] + 18)
            win.after(ms, close)

        self.post(build)

    # -- diff preview ---------------------------------------------------------------
    def review(self, original: str, options: list[str], title: str) -> str | None:
        def build(root, done):
            win = tk.Toplevel(root)
            win.title(f"polisher · {title}")
            win.configure(bg=BG)
            win.attributes("-topmost", True)
            width, height = 680, 400
            x = (win.winfo_screenwidth() - width) // 2
            y = (win.winfo_screenheight() - height) // 3
            win.geometry(f"{width}x{height}+{x}+{y}")

            state = {"index": 0, "closed": False}
            # a translation or heavy rewrite is unreadable as a diff, so start clean there
            show_changes = tk.BooleanVar(value=similarity(original, options[0]) >= 0.5)

            bar = tk.Frame(win, bg=BG)
            bar.pack(fill="x", padx=14, pady=(12, 6))
            foot = tk.Frame(win, bg=BG)
            foot.pack(side="bottom", fill="x", padx=14, pady=12)
            body = tk.Text(win, wrap="word", bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                           padx=16, pady=14, borderwidth=0, highlightthickness=0,
                           font=(self.font[0], 12), spacing3=4)
            body.pack(fill="both", expand=True, padx=14, pady=4)
            body.tag_configure("delete", foreground=DEL_FG, overstrike=True)
            body.tag_configure("insert", foreground=INS_FG, background=INS_BG)
            tabs: list[tk.Label] = []

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
                    body.insert("end", "no changes suggested for this text.")
                elif show_changes.get():
                    for op, chunk in word_diff(original, candidate):
                        body.insert("end", chunk, () if op == "equal" else (op,))
                else:
                    body.insert("end", candidate)
                body.configure(state="disabled")
                for i, tab in enumerate(tabs):
                    tab.configure(fg=BG if i == state["index"] else MUTED,
                                  bg=ACCENT if i == state["index"] else BG)

            def select(i):
                if 0 <= i < len(options):
                    state["index"] = i
                    render()

            tk.Label(bar, text=title, bg=BG, fg=MUTED, font=self.small).pack(side="left", padx=(0, 12))
            if len(options) > 1:
                for i in range(len(options)):
                    tab = tk.Label(bar, text=str(i + 1), bg=BG, fg=MUTED, font=self.small,
                                   cursor="hand2", padx=8, pady=2)
                    tab.pack(side="left", padx=1)
                    tab.bind("<Button-1>", lambda e, i=i: select(i))
                    tabs.append(tab)
            tk.Checkbutton(bar, text="show changes", variable=show_changes, command=render,
                           bg=BG, fg=MUTED, selectcolor=PANEL, activebackground=BG,
                           activeforeground=FG, highlightthickness=0, borderwidth=0,
                           font=self.small).pack(side="right")

            tk.Button(foot, text="replace  ↵", command=lambda: close(options[state["index"]]),
                      bg=ACCENT, fg=BG, activebackground=ACCENT, relief="flat", borderwidth=0, highlightthickness=0,
                      font=self.font, padx=16, pady=5, cursor="hand2").pack(side="right")
            tk.Button(foot, text="cancel  esc", command=lambda: close(None), bg=BG, fg=MUTED,
                      activebackground=BG, relief="flat", borderwidth=0, highlightthickness=0,
                      font=self.font, padx=12, pady=5, cursor="hand2").pack(side="right", padx=6)
            if len(options) > 1:
                tk.Label(foot, text=f"1-{len(options)} switch option", bg=BG, fg=MUTED,
                         font=self.small).pack(side="left")

            def on_key(event):
                if event.keysym == "Escape":
                    close(None)
                elif event.keysym in ("Return", "KP_Enter"):
                    close(options[state["index"]])
                elif event.char.isdigit() and event.char != "0":
                    select(int(event.char) - 1)

            win.bind("<Key>", on_key)
            win.protocol("WM_DELETE_WINDOW", lambda: close(None))
            render()
            self._grab_focus(win, grab=False)

        return self.ask(build)

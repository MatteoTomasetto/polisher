"""End-to-end smoke test on X11 (run under Xvfb + a window manager, see README 'development').

Simulates an editor, selects text, triggers Polisher through the real clipboard/keyboard path
and checks what ends up in the editor. A fake LLM is used, so no API key is needed.
"""
import os
import subprocess
import sys
import tempfile
import threading
import time

from polisher.app import App
from polisher.config import load_config
from polisher.ui import UI


class FakeEngine:
    def run(self, text, mode, settings, *, n=None, choice=None):
        n = n or mode.suggestions or settings["suggestions"]
        tag = mode.key + (f":{choice}" if choice else "")
        body = text.strip()
        return [f"[{tag}] {body}", f"[alt:{tag}] {body}", f"[third:{tag}] {body}"][:n]


# Know when a popup/preview has really appeared instead of guessing with sleeps.
shown = threading.Event()
_orig_grab = UI._grab_focus


def _spy(win, grab=True):
    shown.set()
    _orig_grab(win, grab)


UI._grab_focus = staticmethod(_spy)


def wait_window():
    assert shown.wait(15), "popup never appeared"
    shown.clear()
    time.sleep(0.7)  # let the focus attempts land


def key(name):
    subprocess.run(["xdotool", "key", name], check=True)


def type_(text):
    subprocess.run(["xdotool", "type", "--delay", "70", text], check=True)


ui = UI()
app = App(load_config(), ui, engine=FakeEngine(), history=None)

# The fake editor is a separate process, so it (not Polisher) owns keyboard focus, as in real life.
tmp = tempfile.mkdtemp()
CMD, OUT = os.path.join(tmp, "cmd.txt"), os.path.join(tmp, "out.txt")
editor = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), "fake_editor.py"), CMD, OUT])
results = {}


def editor_text():
    with open(OUT, encoding="utf-8") as fh:
        return fh.read()


def reset(content):
    with open(CMD, "w", encoding="utf-8") as fh:
        fh.write(content)
    while os.path.exists(CMD):
        time.sleep(0.05)
    time.sleep(0.8)


def run(name, steps, *, menu=False, content="hello wrld"):
    reset(content)
    worker = threading.Thread(target=lambda: app.trigger(menu=menu))
    worker.start()
    steps()
    worker.join(15)
    time.sleep(0.5)
    results[name] = editor_text()


def scenario():
    time.sleep(2.0)
    run("quick", lambda: time.sleep(2.0))  # no preview, one result, pasted right away
    run("tone", lambda: (wait_window(), type_("reph"), key("Return"), wait_window(),
                         type_("for"), key("Return"), wait_window(), key("2"), key("Return")),
        menu=True)
    run("custom language", lambda: (wait_window(), type_("tran"), key("Return"), wait_window(),
                                    type_("klingon"), key("Return"), wait_window(), key("Return")),
        menu=True, content="ciao")
    run("digit shortcut", lambda: (wait_window(), key("5"), wait_window(), key("Return")),
        menu=True, content="word")
    run("cancel", lambda: (wait_window(), key("Escape")), menu=True, content="keep me")
    editor.terminate()
    ui.quit()


threading.Thread(target=scenario, daemon=True).start()
ui.root.after(90000, ui.quit)
ui.mainloop()

expected = {
    "quick": "[polish] hello wrld",
    "tone": "[alt:rephrase:formal] hello wrld",
    "custom language": "[translate:klingon] ciao",
    "digit shortcut": "[expand] word",
    "cancel": "keep me",
}
for name, value in results.items():
    mark = "ok  " if expected.get(name) == value else "FAIL"
    print(f"[{mark}] {name:16} -> {value!r}")
ok = results == expected
print("PASS" if ok else f"FAIL, expected {expected}")
sys.exit(0 if ok else 1)

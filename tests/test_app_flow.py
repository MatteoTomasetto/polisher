from polisher.app import App
from polisher.config import load_config
from polisher.activewin import WindowInfo


class FakeUI:
    def __init__(self, chosen=None):
        self.chosen = chosen
        self.messages = []
        self.review_calls = 0

    def pointer(self):
        return (100, 120)

    def pick(self, title, items, pos, **kwargs):
        if title == "polisher":
            return "polish"
        return "medium"

    def show_busy(self, *args):
        pass

    def hide_busy(self):
        pass

    def review(self, original, options, title):
        self.review_calls += 1
        return self.chosen if self.chosen is not None else options[0]

    def show_status(self, message, pos, ms):
        self.messages.append((message, pos, ms))

    def show_error(self, message, pos, ms):
        self.messages.append(("ERROR: " + message, pos, ms))

    def toast(self, message, ms=0):
        self.messages.append((message, None, ms))


class FakeEngine:
    def __init__(self, result):
        self.result = result

    def run(self, *args, **kwargs):
        return self.result


def test_unchanged_result_shows_feedback_and_does_not_paste(monkeypatch):
    import polisher.app as app_module

    cfg = load_config()
    ui = FakeUI()
    app = App(cfg, ui, engine=FakeEngine(["the same text"]))
    monkeypatch.setattr(app_module, "get_active_window", lambda: WindowInfo())
    monkeypatch.setattr(app_module.clipboard, "read", lambda: "previous")
    monkeypatch.setattr(app_module.clipboard, "copy_selection", lambda: "the same text")
    writes = []
    monkeypatch.setattr(app_module.clipboard, "write", lambda value: writes.append(value))
    monkeypatch.setattr(app_module.clipboard, "paste_text", lambda value: writes.append("PASTE:" + value))
    monkeypatch.setattr(app_module.time, "sleep", lambda *_: None)

    app._process("polish", False)

    assert any("no changes suggested" in message for message, *_ in ui.messages)
    assert not any(item.startswith("PASTE:") for item in writes)
    assert writes[-1] == "previous"


def test_changed_result_is_pasted_and_reports_success(monkeypatch):
    import polisher.app as app_module

    cfg = load_config()
    ui = FakeUI(chosen="A polished sentence.")
    app = App(cfg, ui, engine=FakeEngine(["A polished sentence."]))
    monkeypatch.setattr(app_module, "get_active_window", lambda: WindowInfo())
    monkeypatch.setattr(app_module.clipboard, "read", lambda: "previous")
    monkeypatch.setattr(app_module.clipboard, "copy_selection", lambda: "rough sentence")
    writes = []
    monkeypatch.setattr(app_module.clipboard, "write", lambda value: writes.append(value))
    monkeypatch.setattr(app_module.clipboard, "paste_text", lambda value: writes.append("PASTE:" + value))
    monkeypatch.setattr(app_module, "reactivate", lambda window: None)
    monkeypatch.setattr(app_module.time, "sleep", lambda *_: None)

    app._process("polish", False)

    assert "PASTE:A polished sentence." in writes
    assert any(message == "text replaced" for message, *_ in ui.messages)


def test_quick_preview_true_opens_review_for_quick_hotkey(monkeypatch):
    import polisher.app as app_module

    cfg = load_config()
    cfg.general["quick_preview"] = True
    ui = FakeUI(chosen="A polished sentence.")
    app = App(cfg, ui, engine=FakeEngine(["A polished sentence."]))
    monkeypatch.setattr(app_module, "get_active_window", lambda: WindowInfo())
    monkeypatch.setattr(app_module.clipboard, "read", lambda: "previous")
    monkeypatch.setattr(app_module.clipboard, "copy_selection", lambda: "rough sentence")
    writes = []
    monkeypatch.setattr(app_module.clipboard, "write", lambda value: writes.append(value))
    monkeypatch.setattr(app_module.clipboard, "paste_text", lambda value: writes.append("PASTE:" + value))
    monkeypatch.setattr(app_module, "reactivate", lambda window: None)
    monkeypatch.setattr(app_module.time, "sleep", lambda *_: None)

    app._process("polish", False)

    assert ui.review_calls == 1
    assert "PASTE:A polished sentence." in writes

"""Find out which app/window is in the foreground (used for per-app profiles)."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowInfo:
    app: str = ""
    title: str = ""
    window_id: str = ""


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _windows() -> WindowInfo:
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return WindowInfo()
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    app = ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if handle:
        size = wintypes.DWORD(1024)
        path = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            app = os.path.basename(path.value)
        kernel32.CloseHandle(handle)
    return WindowInfo(app=app, title=buf.value, window_id=str(hwnd))


def _mac() -> WindowInfo:
    app = _run([
        "osascript", "-e",
        'tell application "System Events" to get name of first application process '
        "whose frontmost is true",
    ])
    title = ""
    if app:
        title = _run([
            "osascript", "-e",
            f'tell application "System Events" to tell process "{app}" '
            "to get name of front window",
        ])
    return WindowInfo(app=app, title=title)


def _linux() -> WindowInfo:
    # Needs xdotool (X11). On Wayland this returns an empty WindowInfo.
    window_id = _run(["xdotool", "getactivewindow"])
    title = _run(["xdotool", "getactivewindow", "getwindowname"])
    pid = _run(["xdotool", "getactivewindow", "getwindowpid"])
    app = ""
    if pid.isdigit():
        try:
            with open(f"/proc/{pid}/comm", encoding="utf-8") as fh:
                app = fh.read().strip()
        except OSError:
            pass
    return WindowInfo(app=app, title=title, window_id=window_id)


def get_active_window() -> WindowInfo:
    try:
        if sys.platform == "win32":
            return _windows()
        if sys.platform == "darwin":
            return _mac()
        return _linux()
    except Exception:
        return WindowInfo()


def reactivate(window: WindowInfo) -> None:
    """Bring the original target application back before simulating Ctrl/Cmd+V."""
    if sys.platform.startswith("linux") and window.window_id:
        _run(["xdotool", "windowactivate", "--sync", window.window_id])
    elif sys.platform == "win32" and window.window_id:
        try:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(int(window.window_id))
        except (ValueError, OSError):
            pass
    elif sys.platform == "darwin" and window.app:
        name = window.app.replace("\\", "\\\\").replace('"', '\\"')
        _run(["osascript", "-e", f'tell application "{name}" to activate'])

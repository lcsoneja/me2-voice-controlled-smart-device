"""VCM One-Shot - desktop app window.

Double-clicking the Desktop shortcut opens a native window (pywebview) onto the one-shot
dashboard instead of a browser tab. The app starts the pipeline server first if nothing is
answering on port 8765, and stops it again on close only when it was this app that started it
(so a server you launched yourself is left alone).

If pywebview/WebView2 is unavailable it falls back to a chromeless Edge/Chrome window, which
looks the same to the user.

Usage
    pythonw VCM_OneShot_App.py             normal window
    python  VCM_OneShot_App.py --selftest  open, verify, auto-close after 5 s (no fallback)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


# When frozen into an .exe, __file__ lives in a temporary unpack folder, so resolve against the
# executable's own directory. The exe may sit beside the app (normal use) or inside dist/, so
# accept either and pick the folder that actually contains the server.
def _app_root() -> Path:
    frozen = getattr(sys, "frozen", False)
    start = Path(sys.executable).resolve().parent if frozen else Path(__file__).resolve().parent
    for candidate in (start, start.parent):
        if (candidate / "gate1_server.py").is_file():
            return candidate
    return start


HERE = _app_root()
SERVER = HERE / "gate1_server.py"
PID_FILE = HERE / "_oneshot_server.pid"
PAGE = "http://127.0.0.1:8765/oneshot.html"
HEALTH = "http://127.0.0.1:8765/oneshot.html"
TITLE = "VCM One-Shot - wake gates a single 5 s Gate 2 capture"
START_TIMEOUT = 45.0
BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _fatal(message: str) -> None:
    """Report a failure even when running windowed, where there is no console."""
    print("[app] " + message)
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "VCM One-Shot", 0x10)
    except (AttributeError, OSError):
        pass


def _server_command() -> list[str]:
    """Command that runs the pipeline server.

    Inside a frozen exe sys.executable is the exe itself, so it cannot be reused to run
    gate1_server.py - that would relaunch the app. A real Python launcher is resolved instead.
    """
    if not getattr(sys, "frozen", False):
        return [sys.executable, str(SERVER)]
    for launcher in (["py", "-3.12"], ["py"], ["python"]):
        try:
            probe = subprocess.run([*launcher, "--version"], capture_output=True, timeout=10,
                                    check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0:
            print("[app] using " + " ".join(launcher) + " for the server")
            return [*launcher, str(SERVER)]
    _fatal("Python 3 is required to run the VCM pipeline server, but it was not found on PATH.")
    raise SystemExit(3)


def start_server() -> subprocess.Popen | None:
    """Start the pipeline server when nothing is listening, and wait until it answers."""
    if healthy():
        print("[app] server already running")
        return None
    if not SERVER.is_file():
        raise SystemExit("gate1_server.py not found next to this app: " + str(SERVER))
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    print("[app] starting server ...")
    handle = subprocess.Popen(
        _server_command(),
        cwd=str(HERE),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    # Record what we started so the launcher can stop it even if this window is force-closed.
    try:
        PID_FILE.write_text(str(handle.pid), encoding="utf-8")
    except OSError:
        pass
    deadline = time.time() + START_TIMEOUT
    while time.time() < deadline:
        if healthy():
            print("[app] server ready")
            return handle
        if handle.poll() is not None:
            break
        time.sleep(0.5)
    handle.terminate()
    PID_FILE.unlink(missing_ok=True)
    raise SystemExit(
        "server did not become healthy within " + str(START_TIMEOUT) + " s"
    )


def open_browser_app() -> bool:
    for exe in BROWSERS:
        if Path(exe).is_file():
            subprocess.Popen([exe, "--app=" + PAGE, "--window-size=1280,920"])
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="open the window, close it after 5 s, and report whether it worked",
    )
    args = parser.parse_args()

    server = start_server()
    try:
        try:
            import webview  # optional dependency, imported late so a missing GUI does not break --selftest
        except ImportError:
            webview = None

        if webview is None:
            if args.selftest:
                print("SELFTEST=NO_WEBVIEW")
                return 2
            print(
                "[app] pywebview missing; opening a chromeless browser window instead"
            )
            return 0 if open_browser_app() else 1

        created = webview.create_window(
            TITLE, PAGE, width=1280, height=920, min_size=(980, 720), text_select=True
        )
        if created is None:
            raise SystemExit("could not create the application window")

        if args.selftest:

            def schedule_close() -> None:
                def worker() -> None:
                    import webview as gui  # re-import: the outer name may be the None fallback

                    time.sleep(5)
                    for item in gui.windows:
                        if item is not None:
                            item.destroy()

                threading.Thread(target=worker, daemon=True).start()

            webview.start(schedule_close)
            print("SELFTEST=WINDOW_OK")
            return 0

        webview.start()
        return 0
    finally:
        if server is not None and server.poll() is None:
            print("[app] stopping the server this app started")
            server.terminate()
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())

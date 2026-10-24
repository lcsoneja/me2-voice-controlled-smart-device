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

HERE = Path(__file__).resolve().parent
SERVER = HERE / "gate1_server.py"
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
    handle = subprocess.Popen([sys.executable, str(SERVER)], cwd=str(HERE),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              creationflags=flags)
    deadline = time.time() + START_TIMEOUT
    while time.time() < deadline:
        if healthy():
            print("[app] server ready")
            return handle
        if handle.poll() is not None:
            break
        time.sleep(0.5)
    handle.terminate()
    raise SystemExit("server did not become healthy within " + str(START_TIMEOUT) + " s")


def open_browser_app() -> bool:
    for exe in BROWSERS:
        if Path(exe).is_file():
            subprocess.Popen([exe, "--app=" + PAGE, "--window-size=1280,920"])
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true",
                        help="open the window, close it after 5 s, and report whether it worked")
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
            print("[app] pywebview missing; opening a chromeless browser window instead")
            return 0 if open_browser_app() else 1

        created = webview.create_window(TITLE, PAGE, width=1280, height=920,
                                        min_size=(980, 720), text_select=True)
        if created is None:
            raise SystemExit("could not create the application window")
        # Bind the narrowed value: type checkers cannot narrow a captured variable inside the
        # selftest closure below, so it would still look optional there.
        window = created

        if args.selftest:
            def schedule_close() -> None:
                def worker() -> None:
                    time.sleep(5)
                    window.destroy()
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


if __name__ == "__main__":
    sys.exit(main())

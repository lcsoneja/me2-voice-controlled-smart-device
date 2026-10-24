"""Native desktop window for the unified VCM monitor (Gate 1–Gate 5).

Runs the aiohttp server (gate1_server.build_app) in a background thread and
shows the local UI in a pywebview native window with standard Windows title
bar buttons. Closing the window exits the app cleanly; if the native window
cannot be created, it falls back to the default browser.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
VCM_DIR = HERE / "vcm_live_test_local" / "vcm_live_test_local"
URL = "http://127.0.0.1:8765/pipeline_all_in_one.html"

sys.path.insert(0, str(VCM_DIR))

from aiohttp import web  # noqa: E402


def start_server() -> None:
    """Build the unified app and serve it on 127.0.0.1:8765 from a daemon thread."""
    gate1_server = importlib.import_module("gate1_server")
    app = gate1_server.build_app()
    port = int(gate1_server.PORT)

    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(app, access_log=None)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, "127.0.0.1", port)
        loop.run_until_complete(site.start())
        loop.run_forever()

    threading.Thread(target=run, name="vcm-server", daemon=True).start()


def wait_ready(timeout_seconds: float = 60.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(URL, timeout=2) as response:
                if response.status == 200:
                    return True
        except OSError:
            time.sleep(0.3)
    return False


def main() -> None:
    start_server()
    if not wait_ready():
        print("Server failed to start on " + URL, file=sys.stderr)
        sys.exit(1)
    try:
        import webview

        webview.create_window("VCM Monitor \u2014 Gate 1\u20135", URL, width=1280, height=880)
        webview.start()
    except Exception as exc:  # noqa: BLE001 - keep the monitor usable without a GUI
        print("Native window unavailable (" + str(exc) + "). Falling back to the browser; open " + URL)
        import webbrowser

        webbrowser.open(URL)
        while True:
            time.sleep(3600)
    os._exit(0)  # window closed: stop the daemon server thread immediately


if __name__ == "__main__":
    main()

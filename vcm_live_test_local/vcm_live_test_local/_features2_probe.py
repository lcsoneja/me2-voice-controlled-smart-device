"""Validate capture options, holdout visibility, save and export."""

import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

import numpy as np
from playwright.sync_api import sync_playwright

from recording_lab import RecordingStore

APP = pathlib.Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8765"
store = RecordingStore(APP / "recordings")


def api(path: str, payload: dict | None = None, post: bool = False) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method="POST" if post else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit(
            "call failed " + path + ": " + type(exc).__name__ + " " + str(exc)[:120]
        )


def cleanup_export_files() -> None:
    for pattern in ("export_*.csv", "results_*.json"):
        for path in (APP / "recordings" / "exports").glob(pattern):
            try:
                path.unlink()
            except OSError as exc:
                print("CLEANUP_WARN " + type(exc).__name__)


def main() -> int:
    archives = sorted(APP.glob("recordings/_archive_me2h_holdout_*"))
    if not archives:
        print("NO_ARCHIVE")
        return 1
    try:
        subprocess.run(
            [sys.executable, "_archive_recordings.py", "--restore", archives[-1].name],
            cwd=APP,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        print("RESTORE_FAILED " + exc.stderr.decode(errors="replace")[:200])
        return 1
    entry = store.save(
        np.zeros(16000, dtype=np.float32),
        label="export probe take",
        meta={"action": "WEATHER"},
    )
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width": 1240, "height": 700})
            page.goto(BASE + "/oneshot.html", wait_until="load")
            page.wait_for_selector("#ph-list li", timeout=60000)
            page.wait_for_selector("#opt-nc", timeout=30000)
            page.check("#opt-nc")
            page.wait_for_function(
                "() => window.__oneshot.options && window.__oneshot.options.nc === true",
                timeout=20000,
                polling=300,
            )
            print("OPTIONS_NC=true")
            page.check("#opt-eos")
            page.wait_for_function(
                "() => window.__oneshot.options && window.__oneshot.options.eos === true",
                timeout=20000,
                polling=300,
            )
            print("OPTIONS_EOS=true")

            page.click("#tab-takes")
            page.wait_for_function(
                "() => document.getElementById('tk-list').children.length > 0",
                timeout=30000,
            )
            holdout_on = page.eval_on_selector_all("#tk-list li", "els => els.length")
            page.uncheck("#tk-holdout")
            page.wait_for_timeout(400)
            holdout_off = page.eval_on_selector_all("#tk-list li", "els => els.length")
            print("HOLDOUT on=" + str(holdout_on) + " off=" + str(holdout_off))

            page.check("#tk-holdout")
            page.wait_for_timeout(300)
            page.click("#tk-export")
            page.wait_for_function(
                "() => document.getElementById('tk-count').textContent.includes('.csv')",
                timeout=300000,
                polling=500,
            )
            out = page.inner_text("#tk-count")
            csv_name = out.split(" - ")[0]
            csv_path = APP / "recordings" / csv_name
            print("EXPORT path=" + csv_name + " exists=" + str(csv_path.is_file()))

            page.click("#tk-save")
            page.wait_for_function(
                "() => document.getElementById('tk-count').textContent.includes('.json')",
                timeout=300000,
                polling=500,
            )
            out = page.inner_text("#tk-count")
            json_name = out.split(" - ")[0]
            json_path = APP / "recordings" / json_name
            print("SAVE path=" + json_name + " exists=" + str(json_path.is_file()))
            browser.close()
    finally:
        store.delete(entry["id"])
    json_files = list((APP / "recordings" / "exports").glob("results_*.json"))
    if not json_files:
        print("MATRIX missing")
        return 1
    try:
        data = json.loads(json_files[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print("MATRIX_READ " + type(exc).__name__)
        return 1
    take = data["takes"][0]
    print(
        "MATRIX takes="
        + str(len(data["takes"]))
        + " per_model="
        + str(len(take["results"]))
        + " first_conf="
        + str(take["results"][0]["conf"])
    )
    cleanup_export_files()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

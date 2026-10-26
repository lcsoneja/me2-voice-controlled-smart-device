"""End-to-end validation of the recordings lab features on a live server."""

import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
APP = pathlib.Path(__file__).resolve().parent


def call(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method="POST" if data else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit(
            "call failed " + path + ": " + type(exc).__name__ + " " + str(exc)[:150]
        )


def canvas_sum(page) -> int:
    return page.evaluate(
        """() => {
            const c = document.getElementById('vu');
            const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
            let s = 0;
            for (let i = 0; i < d.length; i += 97) { s += d[i]; }
            return s;
        }"""
    )


def main() -> int:
    archives = sorted(APP.glob("recordings/_archive_me2h_holdout_*"))
    if not archives:
        raise SystemExit("no archive folder to restore")
    subprocess.run(
        [sys.executable, "_archive_recordings.py", "--restore", archives[-1].name],
        cwd=APP,
        check=True,
        capture_output=True,
    )
    rows = call("/api/oneshot/recordings")["recordings"]
    print("RESTORED n=" + str(len(rows)))
    original = next((r.get("action") for r in rows if r["id"] == "me2h_0000"), "")
    print("PROBE_TAKE=me2h_0000 original_action=" + str(original))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel="msedge",
                args=[
                    "--use-fake-ui-for-media-stream",
                    "--use-fake-device-for-media-stream",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(BASE + "/oneshot.html", wait_until="load")
            page.click("#tab-takes")
            page.wait_for_selector("#tk-list li", timeout=60000)
            print(
                "ROWS="
                + str(page.eval_on_selector_all("#tk-list li", "els => els.length"))
            )

            page.check("#tk-all")
            page.wait_for_timeout(300)
            print("ALL_SELECTED=" + page.inner_text("#tk-count"))
            page.uncheck("#tk-all")
            page.wait_for_timeout(200)

            # The row label shows the clip's label, not its id, so reach the take through the
            # filter box (which matches ids) instead of visible text.
            page.fill("#tk-filter", "me2h_0000")
            page.wait_for_timeout(300)
            page.locator("#tk-list li.tk input[type=checkbox]").first.check()
            print("ONE_SELECTED=" + page.inner_text("#tk-count"))
            page.fill("#tk-filter", "")
            page.wait_for_timeout(200)

            page.click("#tk-score-one")
            page.wait_for_function(
                "() => /chosen model|pick a Gate 2|scoring failed/.test("
                "document.getElementById('tk-count').textContent)",
                timeout=180000,
            )
            print("ONE=" + page.inner_text("#tk-count"))
            page.wait_for_timeout(300)
            print(
                "VERDICT_CELLS="
                + str(
                    page.eval_on_selector_all(
                        "#tk-result .rmiss, #tk-result .rok", "els => els.length"
                    )
                )
            )
            print(
                "SCOREBOARD_ROWS="
                + str(page.eval_on_selector_all("#sb-body tr", "els => els.length"))
            )

            before = page.eval_on_selector("#sel-phrase", "el => el.value")
            page.evaluate("window.__oneshot.advancePhrase()")
            page.wait_for_timeout(200)
            after = page.eval_on_selector("#sel-phrase", "el => el.value")
            print("ADVANCE " + repr(before) + " -> " + repr(after))

            page.evaluate(
                """() => {
                    const body = document.getElementById('log');
                    const row = document.createElement('tr');
                    ['7', 'PLAY_MUSIC [match]', '0.900', '12 ms', 'now'].forEach(t => {
                        const td = document.createElement('td');
                        td.textContent = t;
                        row.appendChild(td);
                    });
                    body.insertBefore(row, body.firstChild);
                    window.__oneshot.wireTrial(row, 'me2h_0000', 'PLAY_MUSIC', 'play some music');
                    row.firstChild.click();
                }"""
            )
            page.wait_for_selector("tr.trial-actions", timeout=10000)
            print("POPOVER=shown")
            page.click("tr.trial-actions button:has-text('play')")
            src = page.eval_on_selector("#player", "el => el.src")
            print("PLAY_SRC=" + ("ok" if "recordings/audio?id=" in src else "MISSING"))
            page.select_option("tr.trial-actions select", value="WEATHER")
            page.wait_for_timeout(900)
            action = next(
                (
                    r.get("action")
                    for r in call("/api/oneshot/recordings")["recordings"]
                    if r["id"] == "me2h_0000"
                ),
                "?",
            )
            print("TAGGED action=" + str(action))

            page.evaluate(
                """() => {
                    const body = document.getElementById('log');
                    const row = document.createElement('tr');
                    ['8', 'X', '-', '-', 'now'].forEach(t => {
                        const td = document.createElement('td');
                        td.textContent = t;
                        row.appendChild(td);
                    });
                    body.insertBefore(row, body.firstChild);
                    window.__oneshot.wireTrial(row, 'me2h_0000', '', '');
                    row.firstChild.click();
                }"""
            )
            page.wait_for_selector("tr.trial-actions", timeout=10000)
            page.click("tr.trial-actions button:has-text('delete')")
            page.wait_for_timeout(700)
            print(
                "HOLDOUT_DELETE="
                + ("refused" if "refused" in page.inner_text("#log") else "not-refused")
                + " count="
                + str(len(call("/api/oneshot/recordings")["recordings"]))
            )
            page.evaluate(
                "() => document.querySelectorAll('tr.trial-actions').forEach(a => a.remove())"
            )

            pre = canvas_sum(page)
            page.click("#btn-arm")
            page.wait_for_function("() => window.__oneshot.micOn()", timeout=30000)
            print("MIC=" + page.inner_text("#c-mic"))
            page.wait_for_timeout(400)
            live1 = canvas_sum(page)
            page.wait_for_timeout(400)
            live2 = canvas_sum(page)
            print(
                "VU changed_after_arm="
                + str(live1 != pre)
                + " live_moves="
                + str(live2 != live1)
            )
            page.click("#btn-disarm")
            page.screenshot(path="_features_ui.png")
            browser.close()
    finally:
        call("/api/oneshot/recordings/tag", {"id": "me2h_0000", "action": original})
        restored = next(
            (
                r.get("action")
                for r in call("/api/oneshot/recordings")["recordings"]
                if r["id"] == "me2h_0000"
            ),
            "?",
        )
        print("RESTORED_ACTION=" + str(restored))
        result = subprocess.run(
            [sys.executable, "_archive_recordings.py"],
            cwd=APP,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            print("ARCHIVE_OUT_FAILED " + result.stdout.decode(errors="replace")[:200])
        call("/api/oneshot/leaderboard/reset", {})
    print(
        "FINAL RECORDINGS="
        + str(len(call("/api/oneshot/recordings")["recordings"]))
        + " RANKING="
        + str(len(call("/api/oneshot/leaderboard")["ranking"]))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Mouse-driven UI smoke for the live monitor and standalone all-in-one page.
Uses Edge fake microphone so it exercises permission/audio plumbing without
recording the user's real voice or triggering any external/device action.
"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8766/"

SYNTHETIC = {
    "type": "pipe", "ts": "ui-review",
    "memory": {"seconds": 12, "max": 15, "window_frames": 6, "source": "frames"},
    "g1": {"active": True, "activation_label": "Nova", "activation_conf": 0.93,
           "remaining_s": 5.2, "votes": 2, "rms": 0.032, "floor": 0.005,
           "probs": [0.93, 0.02, 0.05]},
    "g2": {"active": True, "activation_intent": "COLOR", "activation_conf": 0.87,
           "remaining_s": 2.1, "threshold": 0.5, "conf": 0.87,
           "current_conf": 0.87, "current_intent": "COLOR", "intent": "COLOR", "probs": []},
    "action_gate": {"active": True, "triggered": True, "light_on": True, "intent": "COLOR"},
    "spec": {"gate": "gate4", "label": "Blue", "conf": 0.997},
    "specialists": {
        "gateN": {"gate": "gateN", "label": "10 seconds", "conf": 0.91},
        "gate4": {"gate": "gate4", "label": "Blue", "conf": 0.997},
        "gate5": {"gate": "gate5", "label": "Exercise", "conf": 0.93},
    },
    "final": "Blue", "new_event": True,
    "path": [], "path_text": "G1 Nova 93% -> G2 COLOR 87% -> G4 Blue 99% -> LIGHT ON: COLOR",
}


def main() -> int:
    issues = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.on("pageerror", lambda err: issues.append("page: " + str(err)[:180]))
        page.goto(BASE, wait_until="load", timeout=60000)
        page.wait_for_function("document.getElementById('status').textContent.includes('microphone live')", timeout=30000)
        main_banner = page.inner_text("#banner")
        if "STARTING" in main_banner:
            issues.append("main monitor banner stayed at STARTING after mic became live")
        print("main_banner_after_mic=", repr(main_banner))
        tabs = page.locator("button.tab[data-tab]").all_text_contents()
        for tab in ("GATE 1v8", "GATE 2", "PIPELINE", "PARALLEL", "METRICS"):
            if not any(tab in label for label in tabs):
                issues.append("missing main tab: " + tab)
        pipe_tab_box = page.locator("button[data-tab='pipe']").bounding_box()
        if pipe_tab_box is None:
            raise RuntimeError("PIPELINE tab has no visible mouse target")
        page.mouse.click(pipe_tab_box["x"] + 18, pipe_tab_box["y"] + 12)
        page.wait_for_function("document.getElementById('sec-pipe').classList.contains('active')", timeout=5000)
        page.screenshot(path=str(HERE / "vcm_monitor_ui_mouse_review.png"))
        print("main_monitor_tabs=", len(tabs), "pipe_tab_mouse=PASS")
        page.close()

        app = browser.new_page(viewport={"width": 1366, "height": 768})
        app.on("pageerror", lambda err: issues.append("all-in-one: " + str(err)[:180]))
        app.goto(BASE + "pipeline_all_in_one.html", wait_until="load", timeout=60000)
        app.wait_for_function("document.getElementById('status').textContent.includes('microphone live')", timeout=30000)
        dims = app.evaluate("({w:innerWidth,h:innerHeight,sw:document.documentElement.scrollWidth,sh:document.documentElement.scrollHeight})")
        print("viewport=", dims, "no_outer_scroll=", dims["sh"] <= dims["h"] + 2 and dims["sw"] <= dims["w"] + 2)

        # Exercise Gate 1 variant choice with real pointer/selection input.
        g1 = app.locator("#all-g1model")
        g1.click()
        g1.select_option("gate1v8_f16")
        g1_f16 = app.input_value("#all-g1model")
        g1.select_option("gate1v8_f32")
        # Exercise the Gate 2 control without loading the optional Keras model.
        g2 = app.locator("#all-g2model")
        g2.click()
        g2.select_option("gate2v2")
        # Adjust a threshold by clicking the visible slider track.
        slider = app.locator("#all-thr-nova")
        box = slider.bounding_box()
        if box is None:
            raise RuntimeError("Nova threshold slider has no visible mouse target")
        app.mouse.click(box["x"] + box["width"] * 0.72, box["y"] + box["height"] / 2)
        threshold_after_click = app.inner_text("#all-thr-nova-val")
        print("variant_mouse=", g1_f16, "-> gate1v8_f32; threshold_after_mouse_click=", threshold_after_click)

        # Calibrate through the actual button; this only observes the synthetic room noise.
        cal = app.locator("#all-calibrate")
        cb = cal.bounding_box()
        if cb is None:
            raise RuntimeError("Calibrate button has no visible mouse target")
        app.mouse.click(cb["x"] + cb["width"] / 2, cb["y"] + cb["height"] / 2)
        app.wait_for_timeout(11000)
        print("calibration_button=clicked; threshold_after_calibration=", app.inner_text("#all-thr-nova-val"))

        # Score the real local 280-recording set; this is on-device model inference, not a mock.
        score = app.locator("#pipe2ownervoiceRun")
        sb = score.bounding_box()
        if sb is None:
            raise RuntimeError("Score recordings button has no visible mouse target")
        app.mouse.click(sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] / 2)
        app.wait_for_function("document.getElementById('pipe2-ownervoice-summary').textContent.startsWith('OVERALL:')", timeout=60000)
        score_text = app.inner_text("#pipe2-ownervoice-summary")
        print("owner_voice_button=PASS; ", score_text)

        # Render a deterministic accepted pipeline event to verify the action/result affordances.
        app.evaluate("(m) => VCMALL.onServerMessage(m)", SYNTHETIC)
        action = app.inner_text("#pipe2-action")
        slot = app.inner_text("#pipe2-slot")
        route = app.inner_text("#all-gate-history")
        print("synthetic_action=", action, "slot=", slot)
        print("gate_history_rows=", app.locator("#all-gate-history tr").count(), "latest=", route[:220])
        if "Invalid Date" in route:
            issues.append("gate history rendered an invalid timestamp")
        app.screenshot(path=str(HERE / "pipeline_all_in_one_ui_mouse_review.png"), full_page=False)
        if not action.startswith("LIGHT ON:"):
            issues.append("light-first action status did not appear")
        if "G4" not in slot or "Blue" not in slot:
            issues.append("routed slot value did not appear")
        if dims["sh"] > dims["h"] + 2 or dims["sw"] > dims["w"] + 2:
            issues.append("outer page scroll at 1366x768")
        if g1_f16 != "gate1v8_f16":
            issues.append("Gate 1 variant selector did not change")
        if not issues:
            print("UI_MOUSE_RESULT=PASS")
        else:
            print("UI_MOUSE_ISSUES=", issues)
        browser.close()
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())

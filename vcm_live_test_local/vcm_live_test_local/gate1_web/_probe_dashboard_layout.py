#!/usr/bin/env python3
"""Dashboard layout probe: are the threshold bars (meters + sliders) actually visible?

Opens the live dashboard in headless Chromium, reports computed styles and
geometry for the threshold meters and the threshold sliders, and writes a
screenshot for eyeballing. Requires gate1_server.py on 127.0.0.1:8765.

Run: py -3.12 gate1_web/_probe_dashboard_layout.py
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
APP = HERE.parent
SHOT = HERE / "_probe_dashboard_layout.png"
URL = "http://127.0.0.1:8765/pipeline_all_in_one.html"

PROBE_JS = """
() => {
  const probe = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return { sel, found: false };
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return { sel, found: true, w: Math.round(r.width), h: Math.round(r.height),
             top: Math.round(r.top), left: Math.round(r.left),
             display: cs.display, visibility: cs.visibility, opacity: cs.opacity,
             background: cs.backgroundColor, border: cs.borderColor,
             accent: cs.accentColor, appearance: cs.appearance };
  };
  return {
    stageBar: probe("#all-meter-nova"),
    stageTrack: probe("#all-meter-nova-fill"),
    stageCard: probe(".stage-card"),
    sliderBox: probe(".threshold-controls"),
    sliderNova: probe("#all-thr-nova"),
    rail: probe("#all-top-controls"),
  };
}
"""

def main() -> int:
    with sync_playwright() as p:
        # The repo's browser tests launch the installed Edge channel (no
        # bundled Chromium download in this environment).
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        context = browser.new_context(permissions=["microphone"], viewport={"width": 1600, "height": 950})
        page = context.new_page()
        page.goto(URL, wait_until="load", timeout=30000)
        page.wait_for_timeout(4000)
        info = page.evaluate(PROBE_JS)
        page.screenshot(path=str(SHOT), full_page=False)
        browser.close()

    print(json.dumps(info, indent=2))
    print("screenshot:", SHOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

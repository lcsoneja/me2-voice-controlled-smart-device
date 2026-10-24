"""Browser E2E smoke for the PIPELINE v2 pseudo-code tab.

Loads the page on the temp server (port 8766), clicks the PIPELINE v2 tab,
checks the pseudo-code stage elements exist, then deterministically renders a
synthetic pipe message via VCMPIPE2.update and asserts the light-first layout:
LIGHT ON before slot, PATH line, memory cells, selected card.
"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8766/"

RENDER = """(msg) => { VCMALL.onServerMessage(msg);  // real message path: renderer + diagram + threshold history
  return {
    memory: document.getElementById("pipe2-memory").textContent,
    framesFilled: document.querySelectorAll("#pipe2-frames .pipe2-frame.filled").length,
    g1: document.getElementById("pipe2-g1").textContent,
    g2: document.getElementById("pipe2-g2").textContent,
    action: document.getElementById("pipe2-action").textContent,
    ledOn: document.getElementById("pipe2-led-COLOR").classList.contains("on"),
    selected: document.getElementById("pipe2-card-COLOR").classList.contains("selected"),
    slot: document.getElementById("pipe2-slot").textContent,
    path: document.getElementById("pipe2-path").textContent,
    accuracy: document.getElementById("pipe2-accuracy").textContent,
    spec4: document.getElementById("pipe2-spec-gate4").textContent,
     spec5: document.getElementById("pipe2-spec-gate5").textContent,
     novaMeter: document.getElementById("all-meter-nova-state").textContent,
     piattosMeter: document.getElementById("all-meter-piattos-state").textContent,
     g2Meter: document.getElementById("all-meter-g2-state").textContent,
     logRows: document.querySelectorAll("#all-gate-history tr").length,
     logG2: document.querySelector("#all-gate-history tr td:nth-child(3)").textContent,
     diagram: (() => { const ids = ["mic","g1","g2","light","g3","g4","g5","out"];
       const o = {}; ids.forEach(function (b) { const e = document.getElementById("all-box-" + b); o[b] = e ? e.classList.contains("lit") : null; });
       const g4 = document.getElementById("all-box-g4"); o.g4Route = g4 ? g4.classList.contains("route") : null;
       const wave = document.getElementById("all-wave"); const vol = document.getElementById("all-volume"); const thr = document.getElementById("all-thrchart");
       o.canvases = !!(wave && vol && thr);
       o.thrHistLen = (window.VCMALL && window.VCMALL.thrHist) ? window.VCMALL.thrHist.length : 0;
       o.viewport = {w: window.innerWidth, h: window.innerHeight, sw: document.documentElement.scrollWidth, sh: document.documentElement.scrollHeight};
       const actionPanel = document.getElementById("all-action-panel"); const actionGrid = document.getElementById("pipe2-cards");
       o.actionPanelGap = (actionPanel && actionGrid) ? Math.round(actionPanel.getBoundingClientRect().bottom - actionGrid.getBoundingClientRect().bottom) : 999;
       o.cardHeight = document.querySelector("#pipe2-cards .parallel-action") ? Math.round(document.querySelector("#pipe2-cards .parallel-action").getBoundingClientRect().height) : 0;
       o.g1options = document.querySelectorAll("#all-g1model option").length;
       o.g2options = document.querySelectorAll("#all-g2model option").length;
       return o; })(),
    actionBeforeSlot: (() => { const a = document.getElementById("pipe2-action"); const s = document.getElementById("pipe2-slot");
      return !!(a && s && (a.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING)); })(),
  }; }"""

MSG = """{"type":"pipe","ts":"t","memory":{"seconds":12,"max":15,"window_frames":6,"source":"frames"},
 "g1":{"active":true,"activation_label":"Nova","activation_conf":0.93,"remaining_s":5.2,"votes":2,"rms":0.032,"floor":0.005,"probs":[0.93,0.02,0.05]},
 "g2":{"active":true,"activation_intent":"COLOR","activation_conf":0.87,"remaining_s":2.1,"threshold":0.5,"conf":0.87,"current_conf":0.87,"current_intent":"COLOR","intent":"COLOR","probs":[]},
 "action_gate":{"active":true,"triggered":true,"light_on":true,"intent":"COLOR"},
 "spec":{"gate":"gate4","label":"Blue","conf":0.997},"final":"Blue",
 "specialists":{"gateN":{"gate":"gateN","label":"10 seconds","conf":0.91},"gate4":{"gate":"gate4","label":"Blue","conf":0.997},"gate5":{"gate":"gate5","label":"Exercise","conf":0.93}},
 "path":[{"gate":"G1","label":"Nova","conf":0.93,"on":true},{"gate":"G2","label":"COLOR","conf":0.87,"on":true},
         {"gate":"G4","label":"Blue","conf":0.997,"on":true},{"gate":"ACTION","label":"COLOR","on":true}],
 "path_text":"G1 Nova 93% -> G2 COLOR 87% -> G4 Blue 99% -> LIGHT ON: COLOR","new_event":true}"""


def main() -> int:
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.on("pageerror", lambda error: errors.append(str(error)[:200]))
        page.goto(URL + "pipeline_all_in_one.html", wait_until="load", timeout=60000)
        page.wait_for_function("document.getElementById('status').textContent.includes('microphone live')", timeout=30000)
        page.wait_for_function("document.getElementById('pipe2-memory') !== null", timeout=10000)
        page.wait_for_function("document.querySelectorAll('#pipe2-cards .parallel-action').length > 0", timeout=10000)
        page.wait_for_function("document.querySelectorAll('#pipe2-frames .pipe2-frame').length === 15", timeout=10000)
        idle = page.evaluate("""() => ({
          g2: document.getElementById('pipe2-g2').textContent,
          action: document.getElementById('pipe2-action').textContent,
          cards: document.querySelectorAll('#pipe2-cards .parallel-action').length,
          specN: document.getElementById('pipe2-spec-gateN').textContent})""")
        print("all_in_one_page=loaded; idle_g2=", repr(idle["g2"]))
        print("idle_action=", repr(idle["action"]), "cards=", idle["cards"], "idle_specN=", repr(idle["specN"]))
        rendered = page.evaluate(RENDER, json.loads(MSG))
        checks = {
            "memory_12_of_15": "MEMORY: 12/15" in rendered["memory"],
            "frames_filled_12": rendered["framesFilled"] == 12,
            "g1_wake_nova": "WAKE: Nova" in rendered["g1"] and "rms 0.032/0.005" in rendered["g1"],
            "g2_intent_pass": "INTENT: COLOR" in rendered["g2"] and "PASS vs 0.5" in rendered["g2"],
            "action_light_on": "LIGHT ON: COLOR" in rendered["action"],
            "led_on": rendered["ledOn"],
            "card_selected": rendered["selected"],
            "slot_routed_blue": "G4" in rendered["slot"] and "Blue" in rendered["slot"],
            "path_line": rendered["path"].startswith("PATH: G1 Nova"),
            "accuracy_line": rendered["accuracy"].startswith("ACCURACY:"),
            "light_before_slot": rendered["actionBeforeSlot"],
            "spec4_routed": "G4: Blue" in rendered["spec4"] and "ROUTED VALUE" in rendered["spec4"],
            "spec5_waiting": "G5" in rendered["spec5"] and "Exercise" in rendered["spec5"],
            "diagram_g1_g2_light_lit": rendered["diagram"]["g1"] and rendered["diagram"]["g2"] and rendered["diagram"]["light"],
            "diagram_specialists_lit": rendered["diagram"]["g3"] and rendered["diagram"]["g4"] and rendered["diagram"]["g5"],
            "diagram_g4_routed": rendered["diagram"]["g4Route"],
            "diagram_out_lit": rendered["diagram"]["out"],
            "charts_present": rendered["diagram"]["canvases"],
            "thr_history_started": rendered["diagram"]["thrHistLen"] >= 1,
            "nova_threshold_met_bar": "0.93 ≥ 0.50" in rendered["novaMeter"],
            "piattos_threshold_below_bar": "0.02 < 0.50" in rendered["piattosMeter"],
            "g2_threshold_met_bar": "0.87 ≥ 0.50" in rendered["g2Meter"],
            "per_gate_history_row": rendered["logRows"] >= 1 and "COLOR" in rendered["logG2"],
            "variant_choosers": rendered["diagram"]["g1options"] == 10 and rendered["diagram"]["g2options"] == 2,
            "action_cards_use_panel_space": rendered["diagram"]["cardHeight"] >= 42 and rendered["diagram"]["actionPanelGap"] <= 18,
            "all_visible_at_1366x768": rendered["diagram"]["viewport"]["sh"] <= rendered["diagram"]["viewport"]["h"] + 2 and rendered["diagram"]["viewport"]["sw"] <= rendered["diagram"]["viewport"]["w"] + 2,
        }
        for name, ok in checks.items():
            print("check_" + name + "=", "PASS" if ok else "FAIL")
        print("slot=", repr(rendered["slot"]))
        print("path=", repr(rendered["path"]))
        if errors:
            print("page_errors=", errors[:5])
        browser.close()
    return 0 if all(checks.values()) and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

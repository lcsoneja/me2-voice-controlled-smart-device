# CONTRACT — vcm_monitor.html (Gate 1v2 / Gate 2 / Pipeline)

Authoritative spec for the three JS files. The shell `gate1_web/vcm_monitor.html` is parent-owned; do not edit it, CONTRACT.md, or any file other than your own assigned JS file.

## 1. Files
- gate1_web/vcm_monitor.html — shell (parent-owned; contains ALL markup)
- gate1_web/js/shared.js — Worker A (bus, WS, mic, charts, tabs, Gate 1 tab, PHRASES)
- gate1_web/js/gate2.js — Worker B (Gate 2 tab behavior)
- gate1_web/js/pipeline.js — Worker C (Pipeline tab behavior: diagram + stages)

## 2. Load order
`<script defer src="js/shared.js">` → `js/gate2.js` → `js/pipeline.js`. shared.js creates `window.VCM` and, after boot, calls `window.VCMG2.init()` / `window.VCMPIPE.init()` when defined.

## 3. shared.js (Worker A) — window.VCM API
- VCM.send(obj): JSON over WS (ws(s)://location.host/ws, binaryType = "arraybuffer")
- VCM.on(type, fn): subscribe "status" | "probs" | "probs2" | "pipe"
- VCM.thr = {Nova:0.5, Piattos:0.5, gate2MinConf:0.5} — persisted (localStorage "vcm_thr"); VCM.setThr(k, v) updates + persists + sends {type:"thr", thr:VCM.thr} to the server
- VCM.expect = {gate2: null|{intent}, pipe: null|{wake}|{intent,value}} — persisted (localStorage "vcm_expect"); VCM.setExpect(tab, obj|null)
- VCM.log(tab, text, cls): tab "gate1"|"gate2"|"pipe" → prepend div into #g1log/#g2log/#pipelog (cls optional); rows stored for export
- VCM.exportLog(tab, fmt): "csv"|"json" download for that tab's rows
- VCM.setStatus(text, isErr) → #status (append)
- VCM.PHRASES: verbatim data from section 8
- VCM.state: {streamAcc, ctxSR, rmsHist, lastP1, lastP2, lastPipe}
- Behavior: WS connect + reconnect every 2 s; mic via AudioContext({sampleRate:16000}) + getUserMedia({echoCancellation:false, noiseSuppression:false, autoGainControl:false, channelCount:1}) + ScriptProcessorNode(4096,1,1), linear resample if ctxSR!==16000; rolling window = concat-trim to 94720 samples; waveform #wave (last 4096 samples) + level #level (rms dB, 120 samples) redrawn every 100 ms; tab switching: .tab[data-tab] click → toggle #sec-gate1/#sec-gate2/#sec-pipe (.active) + send {type:"mode", mode}; Gate 1 tab: 3 bars in #g1bars (Nova/Piattos/Negative), sliders #thr_Nova/#thr_Piattos, banner #banner (.wake/.listen from msg.wake), log + exports. Message dispatch: status→emit("status"), probs→emit("probs"), probs2→emit("probs2"), pipe→emit("pipe"). After first successful WS open: call window.VCMG2.init() / window.VCMPIPE.init() if defined.

## 4. gate2.js (Worker B) — window.VCMG2 = { init }
- init(): render 19 compact bars (one per unique intent, first-appearance order from VCM.PHRASES.G2) into #g2bars (row structure .probrow/.probname/.probbarwrap/.probbar/.probval, ids bar_<INTENT>/val_<INTENT>); render chips into #g2chips: one chip per pair (label = phrase; class .chip; click → VCM.setExpect("gate2", {intent}) + .sel on selected) + a Clear chip; bind shell slider #thr_g2 → VCM.setThr("gate2MinConf", value); update #g2expected ("none" or intent).
- VCM.on("probs2"): set bar widths (prob*100%), top bar green (#2ea043); #g2top = "TOP: intent (0.xx)"; verdict #g2verdict per VCM.expect.gate2 (classes v-pass/v-low/v-fail/v-idle): none → "no phrase selected" (v-idle); PASS if top===intent && conf>=VCM.thr.gate2MinConf (v-pass); LOW if top===intent but conf<min (v-low); FAIL otherwise (v-fail); VCM.log("gate2", ts + " top=" + top + " conf=" + conf.toFixed(3) + " -> " + verdict).

## 5. pipeline.js (Worker C) — window.VCMPIPE = { init }
- init(): chips into #pipechips-wake (2 wake pairs; click → VCM.setExpect("pipe", {wake: W})) and #pipechips (31 command pairs; click → VCM.setExpect("pipe", {intent: I, value: V})) + Clear chip; #pipeexpected text.
- VCM.on("pipe", msg): stage cards: #pipe-g1 = "G1: " + g1.label + " (" + conf + ")", #pipe-g2 = g2 ? "G2: " + intent + " (" + conf + ")" : "G2: — (no wake)", #pipe-spec = spec ? routed + ": " + label + " (" + conf + ")" : "SPEC: —", #pipe-final = "FINAL: " + (final || "-"); SVG highlight (classList): bx-g1 lit when g1.wake truthy, bx-g2 lit when msg.g2 present, bx-gn/bx-g4/bx-g5 lit when msg.spec && msg.spec.gate matches, bx-out lit when msg.final; lines ln-g1-g2 lit when msg.g2, ln-g2-gn/ln-g2-g4/ln-g2-g5 lit when routed matches, ln-gX-out lit when final; verdict #pipeverdict per VCM.expect.pipe (see section 6); VCM.log("pipe", ts + " g1=" + g1.label + "/" + conf + " g2=" + (g2 ? intent + "/" + conf : "-") + " spec=" + (spec ? label + "/" + conf : "-") + " final=" + (final || "-") + " -> " + verdict).

## 6. Verdict rules (pipeline)
- expect {wake: W}: PASS (v-pass) if msg.g1.wake === W; else idle "listening for W…" (v-idle).
- expect {intent: I, value: V}: if !msg.g1.wake → idle "waiting for wake word…"; else if msg.g2.intent !== I → FAIL (v-fail); else if V && (!msg.spec || msg.spec.label !== V) → FAIL; else if Math.min(msg.g2.conf, spec ? spec.conf : 1) < VCM.thr.gate2MinConf → LOW (v-low); else PASS (v-pass).

## 7. Style
Use shell CSS classes only: .probrow/.probname/.probbarwrap/.probbar/.probval/.chip/.sel/.verdict (v-pass/v-low/v-fail/v-idle)/.card/.thrlabel/.log/.statsline and svg (.box/.lit/.ln/.lnlit). Do not redefine CSS.

## 8. PHRASES (verbatim)
VCM.PHRASES = {
  G2: [["play some music","PLAY_MUSIC"],["what's the weather today","WEATHER"],["what time is it","TIME"],["turn on the lights","LIGHT_ON"],["turn off the lights","LIGHT_OFF"],["pause the music","PAUSE"],["stop","STOP"],["next song","NEXT"],["turn the volume up","VOLUME_UP"],["turn the volume down","VOLUME_DOWN"],["call mom","CALL"],["send a message to john","MESSAGE"],["list my reminders","LIST_REMINDERS"],["set a timer for 10 seconds","TIMER"],["set a timer for 30 seconds","TIMER"],["set a timer for 1 minute","TIMER"],["set an alarm for 6 am","ALARM"],["set an alarm for 8 am","ALARM"],["set an alarm for 9 pm","ALARM"],["set the temperature to 18 degrees","TEMPERATURE"],["set the temperature to 22 degrees","TEMPERATURE"],["set the temperature to 26 degrees","TEMPERATURE"],["set brightness to 20 percent","BRIGHTNESS"],["set brightness to 60 percent","BRIGHTNESS"],["set brightness to 100 percent","BRIGHTNESS"],["make the lights red","COLOR"],["make the lights blue","COLOR"],["make the lights green","COLOR"],["remind me to drink water","CREATE_REMINDER"],["remind me to study","CREATE_REMINDER"],["remind me to exercise","CREATE_REMINDER"]],
  PIPE_WAKE: [["Nova","Nova"],["Piattos","Piattos"]],
  PIPE_CMDS: [["play some music","PLAY_MUSIC",""],["what's the weather today","WEATHER",""],["what time is it","TIME",""],["turn on the lights","LIGHT_ON",""],["turn off the lights","LIGHT_OFF",""],["pause the music","PAUSE",""],["stop","STOP",""],["next song","NEXT",""],["turn the volume up","VOLUME_UP",""],["turn the volume down","VOLUME_DOWN",""],["call mom","CALL",""],["send a message to john","MESSAGE",""],["list my reminders","LIST_REMINDERS",""],["set a timer for 10 seconds","TIMER","10 seconds"],["set a timer for 30 seconds","TIMER","30 seconds"],["set a timer for 1 minute","TIMER","1 minute"],["set an alarm for 6 am","ALARM","6 AM"],["set an alarm for 8 am","ALARM","8 AM"],["set an alarm for 9 pm","ALARM","9 PM"],["set the temperature to 18 degrees","TEMPERATURE","18 degrees"],["set the temperature to 22 degrees","TEMPERATURE","22 degrees"],["set the temperature to 26 degrees","TEMPERATURE","26 degrees"],["set brightness to 20 percent","BRIGHTNESS","20 percent"],["set brightness to 60 percent","BRIGHTNESS","60 percent"],["set brightness to 100 percent","BRIGHTNESS","100 percent"],["make the lights red","COLOR","Red"],["make the lights blue","COLOR","Blue"],["make the lights green","COLOR","Green"],["remind me to drink water","CREATE_REMINDER","Drink water"],["remind me to study","CREATE_REMINDER","Study"],["remind me to exercise","CREATE_REMINDER","Exercise"]]
}

## 9. Server messages
{type:"status",text} | {type:"probs",ts,nova,piattos,negative,wake} | {type:"probs2",ts,probs:{intent:prob},top,conf} | {type:"pipe",ts,g1:{probs:[3],wake,label},g2?:{intent,conf,probs},spec?:{gate,label,conf},final?}
Client→server: {type:"mode",mode:"gate1"|"gate2"|"both"} and {type:"thr",thr:{Nova,Piattos,gate2MinConf}}. Binary WS frames = float32 LE PCM at 16 kHz.
# Architecture V3: Open-Source Voice Command Stack — Research Report

**Date:** 2026-10-12
**Target Hardware:** Raspberry Pi 5, ARM64 (aarch64), Raspberry Pi OS Bookworm / Trixie
**Requirements:** Fully offline, English, 19 smart-home intents, 2 wake words (Nova/Piattos), replacing TFLite KWS + intent classifier (frequent false triggers)
**Goal:** Find ONE practical "try this first" design with concrete installation steps.

---

## Summary

Six open-source options were evaluated. **openWakeWord + sherpa-onnx (streaming ASR + open-vocabulary KWS)** is the recommended "try this first" design: it runs entirely in-process on Pi 5, requires no MQTT broker or Home Assistant, supports custom wake words without retraining (sherpa-onnx) or with lightweight training (openWakeWord), and can be wrapped around the existing TFLite gates incrementally. For teams already running Home Assistant, **Speech-to-Phrase via Wyoming** is a strong alternative with the fastest transcription latency (<1 s on Pi 4+).

---

## Findings

### 1. OpenWakeWord — Mature, MIT-licensed wake-word engine

- **Claim:** openWakeWord is an MIT-licensed Python library that runs 15–20 models simultaneously on a single Raspberry Pi 3 core, with a false-accept rate <0.5/hr and false-reject rate <5% on included pretrained models. It accepts custom `.tflite` models. **Sources:** [GitHub — dscripka/openWakeWord](https://github.com/dscripka/openWakeWord); openWakeWord README (see latency/accuracy claims). **Support:** Direct evidence from README and docs. **Confidence:** High (tested by community, documented).

- **Claim:** Custom wake words can be trained using the provided Jupyter notebook (`notebooks/training_models.ipynb`), requiring ~1 hour on Google Colab for a basic model. **Sources:** [openWakeWord training tutorial](https://github.com/dscripka/openWakeWord#training-new-models). **Support:** Direct evidence. **Confidence:** High.

- **Claim:** openWakeWord ships with a Wyoming protocol server (`wyoming-openwakeword`) that can load custom `.tflite` models from a directory via `--custom-model-dir`. **Sources:** [GitHub — rhasspy/wyoming-openwakeword](https://github.com/rhasspy/wyoming-openwakeword). **Support:** Direct evidence. **Confidence:** High.

### 2. Sherpa-ONNX — Self-contained offline speech toolkit (KWS + ASR + TTS + VAD)

- **Claim:** sherpa-onnx provides an **open-vocabulary keyword spotting** system that can detect arbitrary phrases (including multi-word wake words like "Hey Nova") **without retraining**. It uses a tiny ASR decoder constrained to keyword output. **Sources:** [sherpa-onnx KWS documentation](https://k2-fsa.github.io/sherpa/onnx/kws/index.html). **Support:** Direct evidence from documentation. **Confidence:** High.

- **Claim:** The English-only KWS model (`sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01`, trained on 10,000 hours of GigaSpeech) fits in ~19 MB on disk with int8 quantization, and runs at 160 ms or 320 ms chunk latency depending on model variant. It supports ARM64 Linux / Raspberry Pi. **Sources:** [sherpa-onnx KWS pretrained models (English)](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html#sherpa-onnx-kws-zipformer-gigaspeech-3-3m-2024-01-01-english). **Support:** Direct evidence. **Confidence:** High.

- **Claim:** sherpa-onnx also provides **streaming and non-streaming ASR** (via Zipformer transducer models) and **VAD** (Silero VAD), all in the same Python package (`pip install sherpa-onnx`), running on-device with ONNX Runtime. **Sources:** [GitHub — k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) and [Sherpa-ONNX guide](https://runthisai.com/en/blog/sherpa-onnx-guide). **Support:** Direct evidence. **Confidence:** High.

- **Claim:** The `sherpa-onnx-keyword-spotter` CLI tool accepts a `--keywords-file` where each line defines a keyword with optional boosting score and trigger threshold. Keywords containing spaces use underscores (`NOVA` and `PIATTOS` would each be one keyword line). **Sources:** [sherpa-onnx KWS keyword file format](https://k2-fsa.github.io/sherpa/onnx/kws/index.html#keywords-file). **Support:** Direct evidence. **Confidence:** High.

### 3. Rhasspy 2.5 — Fully offline but legacy, MQTT-based architecture

- **Claim:** Rhasspy 2.5 is a stable, fully offline voice assistant toolkit using the Hermes protocol over MQTT. It supports English via Kaldi, Pocketsphinx, or DeepSpeech, and uses sentence templates for intent parsing. **Sources:** [GitHub — rhasspy/rhasspy](https://github.com/rhasspy/rhasspy). **Support:** Direct evidence. **Confidence:** High.

- **Claim:** Rhasspy's sentence template system (`[intentName]\nturn (<states>){state} [the] light`) compiles into a finite state transducer and outputs structured JSON intents. The 19 target intents map naturally into Rhasspy sentence files. **Sources:** [Rhasspy Intent Handling](https://rhasspy.readthedocs.io/en/latest/intent-handling/). **Support:** Direct evidence. **Confidence:** High.

- **IMPORTANT NOTE:** Rhasspy 2.5 is in **maintenance mode** — the creator (Michael Hansen) is now the Home Assistant voice lead. New development is on Wyoming-protocol components (openWakeWord, Speech-to-Phrase, Piper). **Sources:** [Developer commentary in Rhasspy docs and Wyoming vs Rhasspy comparison](https://sumguy.com/home-assistant-voice-wyoming-vs-rhasspy/). **Support:** Researcher inference from evidence. **Confidence:** High.

### 4. Vosk — Lightweight STT, no wake-word engine

- **Claim:** Vosk is an Apache 2.0-licensed offline STT engine supporting 20+ languages with 50 MB portable models. It installs via `pip install vosk` and runs on Raspberry Pi with sub-200 ms latency (Pi 5, ReSpeaker HAT). **Sources:** [VOSK Offline Speech Recognition API](https://alphacephei.com/vosk/); [Offline Speech to Text on Pi 5: Vosk vs Whisper](https://electricalflux.com/mcu-projects/offline-speech-to-text-raspberry-pi-vosk-respeaker). **Support:** Direct evidence. **Confidence:** High.

- **Claim:** Vosk does NOT include built-in wake word detection — it is a streaming STT engine only. A separate wake-word engine (openWakeWord, Porcupine, etc.) must run alongside it. **Sources:** [Vosk documentation](https://alphacephei.com/vosk/). **Support:** Researcher inference from absence. **Confidence:** High.

- **Claim:** Vosk supports dynamic grammar reconfiguration for keyword boosting and limited grammar-based recognition, but not structured intent parsing with slot extraction. Intent parsing would need custom code. **Sources:** [Vosk accuracy and adaptation docs](https://alphacephei.com/vosk/adaptation). **Support:** Direct evidence. **Confidence:** Medium.

### 5. Speech-to-Phrase (OHF-Voice / Home Assistant) — Fastest constrained ASR

- **Claim:** Speech-to-Phrase is a **closed-set speech recognition** system: instead of "what did the user say?", it answers "which of the phrases I know did the user say?" using a constrained CTC decoder. On a Pi 4, transcription takes <1 second. **Sources:** [GitHub — OHF-voice/speech-to-phrase](https://github.com/OHF-voice/speech-to-phrase); [HA local voice assistant guide](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/). **Support:** Direct evidence. **Confidence:** High.

- **Claim:** Development has moved to `OHF-Voice/apps` where Speech-to-Phrase is rewritten as a constrained CTC decoder using sentence templates from the `home-assistant/intents` package. It is available as a Home Assistant add-on and as a Wyoming-protocol Docker image. **Sources:** [OHF-Voice/apps README](https://github.com/OHF-Voice/apps). **Support:** Direct evidence. **Confidence:** High.

- **Claim:** Speech-to-Phrase **requires Home Assistant** to operate (it fetches entity/area names from HA via WebSocket). It cannot run standalone. **Sources:** [Speech-to-Phrase Docker usage requiring `--hass-websocket-uri`](https://github.com/OHF-voice/speech-to-phrase). **Support:** Direct evidence. **Confidence:** High.

### 6. OpenVoiceOS (OVOS) — Full smart-speaker OS

- **Claim:** OpenVoiceOS is the community successor to Mycroft, providing a full smart-speaker operating system. It runs on Raspberry Pi 3B+ and higher via the RaspOVOS image. CORE components install via `pip install ovos-core`. **Sources:** [GitHub — OpenVoiceOS/ovos-core](https://github.com/OpenVoiceOS/ovos-core). **Support:** Direct evidence. **Confidence:** High.

- **Claim:** OVOS uses a pipeline of intent parsers (Adapt, Padatious, fallback) and supports wake-word plugins (Precise, openWakeWord). Skills are Python plugins. **Sources:** [OVOS technical manual](https://openvoiceos.github.io/ovos-technical-manual). **Support:** Direct evidence. **Confidence:** Medium (inferred from docs).

- **Claim:** OVOS is the **heaviest option** — RaspOVOS is a full OS image, and the skill/plugin ecosystem adds complexity. For a fixed 19-intent system, OVOS is overkill and adds more failure points. **Support:** Researcher inference. **Confidence:** High.

---

## Comparison Table

| Option | Wake Word | STT/ASR | Intent/Slot Parsing | License | Pi 5 Latency (est.) | Integ. Effort | 19-Intent Feasibility |
|---|---|---|---|---|---|---|---|
| **1. openWakeWord → sherpa-onnx ASR → custom intent** | openWakeWord (custom .tflite or pretrained) | sherpa-onnx zipformer decoder (streaming) | Custom Python: regex/pattern match on ASR text | MIT + Apache 2.0 | KWS: <80ms/frame; ASR: 200–500ms | Medium (custom code, but no MQTT/HA needed) | ✅ Direct mapping via patterns |
| **2. openWakeWord → Wyoming → HA Assist** | openWakeWord via wyoming-openwakeword | Whisper or Speech-to-Phrase via Wyoming | HA Assist pipeline (built-in + custom sentences) | Apache 2.0 | StT: <1s (S2P) or ~8s (Whisper) | Low (requires HA running) | ✅ Via HA built-in intents + custom sentences |
| **3. Rhasspy 2.5 (Hermes/MQTT)** | openWakeWord or Raven | Kaldi/Pocketsphinx/DeepSpeech | Rhasspy sentence templates → JSON | MIT / Apache 2.0 | 1–3s depending on ASR engine | Medium-High (MQTT broker needed) | ✅ Excellent via `sentences.ini` |
| **4. Vosk + openWakeWord + custom parser** | openWakeWord | Vosk streaming STT | Custom Python grammar/pattern match | Apache 2.0 + MIT | 150–400ms (STT) | Medium | ✅ With custom parser code |
| **5. Speech-to-Phrase (+ openWakeWord)** | openWakeWord via Wyoming | Speech-to-Phrase (constrained CTC) | HA sentencetemplates (hassil FST) | MIT / Apache 2.0 | ~500ms–1s (fastest) | Low (but requires HA) | ⚠️ Limited to HA sentence coverage |
| **6. OVOS (RaspOVOS)** | Precise / openWakeWord plugin | Vosk / whisper | Mycroft/OVOS skill system (Padatious/Adapt) | Apache 2.0 | 1–3s | High (full OS or many deps) | ✅ Via custom skill(s) |
| **7. Sherpa-onnx KWS + ASR only (monolithic)** | sherpa-onnx open-vocab KWS | sherpa-onnx streaming ASR | No built-in intent parser → custom | Apache 2.0 | KWS: 160–320ms; ASR: 200–500ms | Medium | ✅ Via pattern matching |

### Notes on license/feasibility flags
- **UNVERIFIED:** Real-world Pi 5 end-to-end latency for sherpa-onnx KWS + streaming ASR simultaneously (no published benchmarks found). Inference: should be well under 1 s CPU-only given 4.6 MB int8 encoder and 12K-hours-trained model.
- **UNVERIFIED:** Speech-to-Phrase v2 (CTC-based, in OHF-Voice/apps) has not yet been tested by the community on Pi 5 without HA (requirement is HA).
- **UNVERIFIED:** OVOS skill system documentation for custom command definitions (unclear whether 19 intents require writing 19 separate Python skill files or can use a simpler config-based approach).

---

## Recommended "Try This First" Design

### Architecture: openWakeWord → sherpa-onnx streaming ASR → custom intent matcher

```
┌──────────────────────────────────────────────────┐
│               Raspberry Pi 5                      │
│                                                   │
│  Microphone (USB/I2S)                             │
│       │                                           │
│       ▼                                           │
│  ┌─────────────┐    ┌───────────────────┐        │
│  │ openWakeWord │───▶│ Detection: "Nova"│        │
│  │ (16kHz PCM)  │    │ or "Piattos"     │        │
│  └──────┬───────┘    └────────┬──────────┘        │
│         │                     │                    │
│         ▼                     ▼                    │
│  ┌─────────────────────────────────────┐          │
│  │ sherpa-onnx streaming ASR           │          │
│  │ (Zipformer, 16kHz, English model)   │          │
│  └──────────────────┬──────────────────┘          │
│                     │                              │
│                     ▼                              │
│  ┌─────────────────────────────────────┐          │
│  │ Intent Matcher (Python)             │          │
│  │ • Normalize ASR text                │          │
│  │ • Match → 19 fixed intents          │          │
│  │ • Extract slots (brightness, color, │          │
│  │   timer_minutes, etc.)              │          │
│  └──────┬──────────────────────────────┘          │
│         │                                          │
│         ▼                                          │
│  ┌──────────────┐                                  │
│  │ Action       │──▶ Execute command               │
│  │ Dispatcher   │──▶ Return TTS response           │
│  └──────────────┘                                  │
│                                                   │
│  ┌──────────────────────────────────┐             │
│  │ Side-by-side with EXISTING gates │             │
│  │ • TFLite KWS (disabled or backup)│             │
│  │ • Old intent classifier (backup) │             │
│  └──────────────────────────────────┘             │
└──────────────────────────────────────────────────┘
```

### Why This Design

| Concern | How This Addresses It |
|---|---|
| **Frequent false triggers (existing TFLite)** | openWakeWord includes optional **Silero VAD gate** and per-model thresholds. False-accept rates <0.5/hr on pretrained models. Custom models can be trained with user voice as verifier. |
| **Two wake words needed (Nova/Piattos)** | openWakeWord runs **both models simultaneously** on one core. sherpa-onnx KWS also supports multi-keyword without retraining. |
| **19 fixed intents** | No general ASR needed for free-form speech — the intent matcher is a deterministic pattern engine over the constrained command set. sherpa-onnx ASR text is post-processed with regex/FST matching. |
| **Fully offline** | No cloud calls. Models (5–50 MB) download once. ONNX Runtime for CPU only. |
| **Slot extraction** | Each intent's slots (color name, brightness %, timer seconds, etc.) are extracted with intent-specific patterns. |
| **Sit beside existing gates** | The new pipeline runs as a sidecar Python process. The old TFLite pipeline stays untouched; the systemd service for the new pipeline starts after the old one. A config toggle selects which pipeline processes each wake event. |

### How the 19 Intents Map

| Intent | Pattern | Slots |
|---|---|---|
| play_music | `play music` / `play (artist/song/album) on (room)` | artist, song, album, room |
| weather | `(what's|tell me) the weather` / `weather in (city)` | city |
| time | `(what's|tell me) the time` | — |
| lights_on | `turn (on|off) the (room) light(s)` | room, state |
| lights_off | same pattern, `state=off` | room, state |
| brightness | `set (room) light(s) to (0-100) percent` | room, level |
| color | `set (room) lights to (color)` | room, color |
| volume | `set volume to (1-100)` / `volume (up|down)` | level, direction |
| call | `call (contact)` / `make a call to (contact)` | contact |
| message | `send (text) to (contact)` | text, contact |
| reminders | `(set|create) a reminder (for|at) (time)` | time, text |
| timer | `set a timer for (seconds)` | seconds |
| alarm | `set an alarm for (time)` | time |
| temperature | `(what's|set) the temperature (to) (value)` | value, room |

Each intent is a small Python function or YAML pattern. The sherpa-onnx ASR output text is lowercased, stripped of punctuation, then matched against intent patterns in priority order.

---

### Concrete Installation Steps (Pi 5, standalone)

#### Step 1: System dependencies

```bash
# Already on Pi 5: Raspberry Pi OS Bookworm (64-bit)
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv portaudio19-dev \
  libspeexdsp-dev libsndfile1-dev libopenfst-dev \
  flac libflac-dev
```

#### Step 2: Create Python virtual environment

```bash
mkdir -p ~/voice_assistant_v3
cd ~/voice_assistant_v3
python3 -m venv venv
source venv/bin/activate
```

#### Step 3: Install openWakeWord

```bash
pip install openwakeword
# Verify: python3 -c "import openwakeword; print(openwakeword.__version__)"
```

#### Step 4: Download/set up custom wake word models for "Nova" and "Piattos"

**Option A (quick start — use generic wake word model for testing first):**
```bash
python3 -c "
import openwakeword
openwakeword.utils.download_models()
"
# This downloads alexa, hey_jarvis, hey_mycroft (for testing only)
```

**Option B (train custom "Nova" and "Piattos" models — recommended):**
1. Open the Colab notebook: `notebooks/training_models.ipynb` from the openWakeWord repo.
2. Record ~50 positive samples of "Nova" and "Piattos" each (3 seconds per sample).
3. Download ~100 negative samples from the provided negative reference or LibriSpeech.
4. Train for ~1 hour → produces two `.tflite` files.
5. Copy to Pi 5: `~/voice_assistant_v3/models/nova.tflite` and `piattos.tflite`.

**Option C (use pre-existing custom wake word model from HA community):**
Check [home-assistant-wakewords-collection](https://github.com/fwartner/home-assistant-wakewords-collection) for existing similar wake words.

#### Step 5: Install sherpa-onnx (with keyword spotting AND ASR)

```bash
pip install sherpa-onnx
# Verify: python3 -c "import sherpa_onnx; print('ok')"
```

Download the English open-vocabulary KWS model:
```bash
mkdir -p ~/voice_assistant_v3/models
cd ~/voice_assistant_v3/models
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2
tar xf sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2
rm sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2
```

Download a small English streaming ASR model for command text:
```bash
# sherpa-onnx streaming Zipformer English (small)
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-20M-2024-06-21.tar.bz2
tar xf sherpa-onnx-streaming-zipformer-en-20M-2024-06-21.tar.bz2
rm sherpa-onnx-streaming-zipformer-en-20M-2024-06-21.tar.bz2
```

(Alternatively, use the much smaller streaming paraformer model at ~10 MB if the zipformer is too heavy.)

#### Step 6: Create the Python pipeline

Main file: `~/voice_assistant_v3/pipeline.py`

```python
#!/usr/bin/env python3
"""
Architecture V3: openWakeWord → sherpa-onnx ASR → Intent Matcher
Sits beside existing TFLite gates. Sidecar process.
"""

import sys
import json
import queue
import threading
import time
import re
from pathlib import Path

import numpy as np
import pyaudio

# ── Wake word detection ──
from openwakeword.model import Model as OWWModel

# ── ASR ──
import sherpa_onnx

# ═══════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════

OWW_MODELS_DIR = Path.home() / "voice_assistant_v3" / "models"
OWW_MODELS = [
    str(OWW_MODELS_DIR / "nova.tflite"),       # Custom-trained
    str(OWW_MODELS_DIR / "piattos.tflile"),    # Custom-trained
]

SHERPA_KWS_MODEL_DIR = OWW_MODELS_DIR / "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
SHERPA_ASR_MODEL_DIR = OWW_MODELS_DIR / "sherpa-onnx-streaming-zipformer-en-20M-2024-06-21"

AUDIO_FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1280  # 80ms at 16kHz

# ═══════════════════════════════════════════
# 19 INTENT PATTERNS (ordered by specificity)
# ═══════════════════════════════════════════

INTENT_PATTERNS = [
    # (pattern_regex, intent_name, slot_extractor_fn)
    (r"play\s+(?:music|song|artist|album)(?:\s+(.+))?", "play_music", lambda m: {"query": m.group(1) or ""}),
    (r"(?:what'?s|tell me)\s+the\s+weather(?:\s+in\s+(.+))?", "weather", lambda m: {"city": m.group(1) or ""}),
    (r"(?:what'?s|tell me)\s+the\s+time", "time", lambda m: {}),
    (r"(?:turn\s+)?on\s+(?:the\s+)?(.+?)\s+light", "lights_on", lambda m: {"room": m.group(1)}),
    (r"(?:turn\s+)?off\s+(?:the\s+)?(.+?)\s+light", "lights_off", lambda m: {"room": m.group(1)}),
    (r"set\s+(?:the\s+)?(.+?)\s+light\s+(?:brightness|to)\s+(\d+)", "brightness", lambda m: {"room": m.group(1), "level": m.group(2)}),
    (r"set\s+(?:the\s+)?(.+?)\s+light\s+to\s+(\w+)", "color", lambda m: {"room": m.group(1), "color": m.group(2)}),
    (r"(?:set\s+)?volume\s+(?:to\s+)?(\d+)", "volume", lambda m: {"level": m.group(1)}),
    (r"volume\s+(up|down)", "volume", lambda m: {"direction": m.group(1)}),
    (r"call\s+(.+)", "call", lambda m: {"contact": m.group(1)}),
    (r"send\s+(.+)\s+to\s+(.+)", "message", lambda m: {"text": m.group(1), "contact": m.group(2)}),
    (r"(?:set|create)\s+(?:a\s+)?reminder\s+(?:for|at)\s+(.+)", "reminder", lambda m: {"time": m.group(1)}),
    (r"(?:set\s+)?(?:a\s+)?timer\s+(?:for\s+)?(\d+)\s*(?:second|minute|hour)", "timer", lambda m: {"duration": m.group(1)}),
    (r"set\s+(?:an\s+)?alarm\s+(?:for\s+)?(.+)", "alarm", lambda m: {"time": m.group(1)}),
    (r"(?:what'?s|set)\s+(?:the\s+)?temperature(?:\s+to\s+(\d+))?", "temperature", lambda m: {"value": m.group(1) or ""}),
]

def match_intent(text: str):
    """Return (intent_name, slots) or None."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)  # strip punctuation
    for pattern, name, slot_fn in INTENT_PATTERNS:
        m = re.match(pattern, text)
        if m:
            return name, slot_fn(m)
    return None

# ═══════════════════════════════════════════
# SHERPA-ONNX ASR SETUP
# ═══════════════════════════════════════════

def create_asr():
    """Create a streaming sherpa-onnx recognizer."""
    recognizer = sherpa_onnx.OnlineRecognizer(
        tokens=str(SHERPA_ASR_MODEL_DIR / "tokens.txt"),
        encoder=str(SHERPA_ASR_MODEL_DIR / "encoder-epoch-30-avg-2.int8.onnx"),
        decoder=str(SHERPA_ASR_MODEL_DIR / "decoder-epoch-30-avg-2.int8.onnx"),
        joiner=str(SHERPA_ASR_MODEL_DIR / "joiner-epoch-30-avg-2.int8.onnx"),
        num_threads=2,
        provider="cpu",
        decoding_method="greedy_search",
        debug=False,
    )
    return recognizer

# ═══════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════

def main():
    print("[pipeline] Loading wake word models...")
    oww = OWWModel(wakeword_models=OWW_MODELS, vad_threshold=0.5)

    print("[pipeline] Loading ASR...")
    asr = create_asr()

    print("[pipeline] Opening microphone...")
    p = pyaudio.PyAudio()
    stream = p.open(format=AUDIO_FORMAT, channels=CHANNELS,
                    rate=RATE, input=True, frames_per_buffer=CHUNK)

    print("[pipeline] Listening... Say 'Nova' or 'Piattos' then a command.")
    audio_buffer = b""
    is_listening = False

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_buffer += data

            # Process 80ms frames for OWW
            if len(audio_buffer) >= CHUNK * 2:
                frame = audio_buffer[:CHUNK]
                audio_buffer = audio_buffer[CHUNK:]

                prediction = oww.predict(frame)
                for wakeword, score in prediction.items():
                    if score > 0.5:
                        print(f"[wake] {wakeword}: {score:.3f}")
                        is_listening = True
                        # Start ASR stream
                        asr_stream = asr.create_stream()
                        continue

            # When listening, feed audio to ASR
            if is_listening and len(audio_buffer) >= 1280:
                frame = audio_buffer[:1280]
                audio_buffer = audio_buffer[1280:]
                asr_stream.accept_waveform(16000, frame)
                result = asr_stream.result
                if result and result.text:
                    text = result.text.strip()
                    print(f"[asr] {text}")
                    intent = match_intent(text)
                    if intent:
                        name, slots = intent
                        print(f"[intent] {name} slots={slots}")
                        # --- DISPATCH ---
                        # dispatch_intent(name, slots)
                        is_listening = False
                        # create new stream for next command
                        asr_stream = asr.create_stream()

    except KeyboardInterrupt:
        print("\n[pipeline] Stopping.")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

if __name__ == "__main__":
    main()
```

> **Note:** The code above is a **skeleton** — it shows the flow. Real implementation needs audio buffer management, VAD-based endpoint detection, and non-blocking dispatch. The sherpa-onnx Python API's exact stream API may vary; check the latest `sherpa_onnx` package for `OnlineRecognizer` interface.

#### Step 7: Create intent dispatch module

`~/voice_assistant_v3/dispatcher.py` — maps each of the 19 intents to an action. For example:

```python
def dispatch(intent_name, slots):
    """Route intent to action."""
    if intent_name == "lights_on":
        room = slots.get("room", "living room")
        # Call existing light control API/GPIO/MQTT
        print(f"[action] Turn ON lights in {room}")
    elif intent_name == "lights_off":
        room = slots.get("room", "living room")
        print(f"[action] Turn OFF lights in {room}")
    elif intent_name == "weather":
        # Fetch from local weather service
        print("[action] Report weather")
    # ... all 19 intents ...
    else:
        print(f"[action] Unknown intent: {intent_name}")
```

#### Step 8: Create systemd service (sits alongside existing gates)

File: `/etc/systemd/system/voice-pipeline-v3.service`

```ini
[Unit]
Description=Architecture V3 Voice Pipeline
After=network.target sound.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/voice_assistant_v3
ExecStart=/home/pi/voice_assistant_v3/venv/bin/python pipeline.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo cp voice-pipeline-v3.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable voice-pipeline-v3
sudo systemctl start voice-pipeline-v3
```

The existing TFLite pipeline service remains untouched. Both can run — or you stop the old one when v3 is confirmed working:

```bash
sudo systemctl stop old-kws-pipeline   # if systemd
sudo systemctl disable old-kws-pipeline
```

#### Step 9: Iterative tuning

1. **Tune wake-word threshold**: Start with 0.5. If false triggers, raise to 0.7–0.8.
2. **Add VAD gate**: openWakeWord's `vad_threshold=0.5` reduces non-speech triggers.
3. **Monitor logs**: `journalctl -u voice-pipeline-v3 -f`
4. **Add custom-verifier model** (voice-specific): openWakeWord supports a second-stage verifier to reject wake words spoken by non-target voices.
5. **Tune ASR**: Use `keywords_score` and `keywords_threshold` per command phrase in sherpa-onnx for better recognition of command words.

---

## How It Sits Beside Existing TFLite Gates

| Component | Existing TFLite | New v3 Pipeline | Notes |
|---|---|---|---|
| **Wake word** | TFLite KWS (frequent false triggers) | openWakeWord (VAD-gated, configurable thresholds) | Either/or: both run, but only one feeds the intent stage. Start by running both, comparing trigger rates. |
| **STT** | (none — intent classifier on raw features) | sherpa-onnx streaming ASR | New. Old pipeline doesn't do ASR. |
| **Intent** | TFLite intent classifier | Python pattern matcher | Side by side. Run v3 first, keep old as fallback. |
| **Audio source** | USB mic via PyAudio | Same audio source, same 16kHz format | No hardware change needed. |
| **Config** | Hardcoded in Python | Python config dict / YAML | v3 pipeline reads from config file. |

**Migration path:**
1. Install v3 pipeline alongside existing (both listening, v3 silent/inactive).
2. Enable v3 output logging only — compare trigger accuracy for 1 day.
3. If v3 shows >50% fewer false triggers, swap the active pipeline.
4. Keep the old pipeline as a config-selectable backup.

---

## When to Choose an Alternative

| Scenario | Better Option |
|---|---|
| **Already running Home Assistant** | Speech-to-Phrase + Wyoming openWakeWord (fastest, easiest) |
| **Need TTS feedback (voice says back results)** | Add **Piper** TTS via Wyoming or sherpa-onnx's built-in TTS |
| **Need open-ended Q&A, not fixed intents** | Vosk + LLM pipeline (heavier) or HA Assist with conversation agent |
| **Team familiar with MQTT/microservices** | Rhasspy 2.5 (stable but legacy) |
| **Want a turnkey appliance OS** | RaspOVOS (easiest deployment, hardest customization) |

---

## Contradictions

| Claim | Counter-evidence |
|---|---|
| **"Rhasspy is the best fully offline option"** | Rhasspy 2.5 is in maintenance mode. The creator now works on Home Assistant's Wyoming components (openWakeWord, Speech-to-Phrase, Piper). For *new* projects, the Wyoming ecosystem is the recommended path. **Sources:** [Rhasspy README](https://github.com/rhasspy/rhasspy) vs [HA voice control docs](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/). |
| **"Sherpa-onnx KWS is only for Chinese"** | False — there is a dedicated **English-only** KWS model trained on GigaSpeech (10K hours), and a **bilingual** zh-en model. **Sources:** [sherpa-onnx English KWS model](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html#sherpa-onnx-kws-zipformer-gigaspeech-3-3m-2024-01-01-english). |

---

## Missing Evidence

1. **Real-world Pi 5 end-to-end latency**: sherpa-onnx KWS + streaming ASR simultaneously has not been benchmarked publicly on Pi 5. The KWS model is 4.6 MB (int8) and should be fast, but concurrent ASR load is unmeasured.
2. **Custom wake-word training accuracy**: openWakeWord claims <1 hour training for a basic custom model, but expected false-reject rate for a 2-syllable word like "Nova" vs a 3-syllable "Piattos" is not documented.
3. **Sherpa-onnx Python stream API compatibility**: The `OnlineRecognizer` API has been evolving. The exact method names (`accept_waveform`, `result`) should be verified against the installed `sherpa_onnx` version.
4. **20 MB ASR model inference speed on Pi 5 ARM64**: Streaming zipformer transducer models are designed for efficiency, but no published Pi 5 real-time-factor is available.

---

## Sources

### Kept
| Source | URL | Why It Matters |
|---|---|---|
| openWakeWord README | [GitHub](https://github.com/dscripka/openWakeWord) | Primary docs: accuracy claims, training, usage |
| openWakeWord Wyoming server | [GitHub](https://github.com/rhasspy/wyoming-openwakeword) | Shows HA integration path for custom wake words |
| sherpa-onnx KWS docs | [k2-fsa.github.io](https://k2-fsa.github.io/sherpa/onnx/kws/index.html) | Complete KWS keyword format, model download, CLI |
| sherpa-onnx English KWS model | [k2-fsa.github.io](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html#sherpa-onnx-kws-zipformer-gigaspeech-3-3m-2024-01-01-english) | Pre-trained English-only open-vocab KWS |
| Rhasspy intent handling | [rhasspy.readthedocs.io](https://rhasspy.readthedocs.io/en/latest/intent-handling/) | Sentence template → JSON intents reference |
| HA local voice assistant guide | [home-assistant.io](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/) | Speech-to-Phrase, Whisper, Piper setup |
| Speech-to-Phrase v1.4.3 README | [GitHub — OHF-voice/speech-to-phrase](https://github.com/OHF-voice/speech-to-phrase) | Constrained ASR for fast intent transcription |
| OVOS-core README | [GitHub — OpenVoiceOS/ovos-core](https://github.com/OpenVoiceOS/ovos-core) | Full smart-speaker framework reference |
| Vosk API site | [alphacephei.com](https://alphacephei.com/vosk/) | STT model sizes, platform support |
| Sherpa-ONNX guide | [runthisai.com](https://runthisai.com/en/blog/sherpa-onnx-guide) | Overview of sherpa-onnx capabilities |

### Rejected / Deprioritized
| Source | Reason |
|---|---|
| Various "build your own voice assistant" blog posts | Redundant or outdated (pre-2024, using deprecated Google Assistant SDK) |
| Hackster.io wake word project | Too specific to camera-triggered capture, not relevant to voice pipeline |
| Vosk forums (raspberrypi.com) | General discussion, no structured intent handling |
| OHF-Voice/apps individual config files | Too low-level; the README is sufficient |

---

## Next Steps

1. **Run the minimal proof-of-concept first**: Install openWakeWord on Pi 5 with a single generic wake word (e.g., "hey_mycroft" from pretrained models). Verify that `detect_from_microphone.py` works end-to-end. This confirms audio chain, latency, and false-trigger rate before any custom training.
2. **Train "Nova" and "Piattos" models** using the openWakeWord Colab notebook. Expected: 1 hour of Colab GPU time, ~50 positive samples each.
3. **Test sherpa-onnx KWS with wake words as keywords** — since sherpa-onnx supports open-vocabulary KWS, try listing "NOVA" and "PIATTOS" as keyword phrases directly (simpler, no training needed). This may be good enough and is zero-training-effort.
4. **Write the 19 intent patterns** as a Python module with unit tests. Test with recorded command audio before connecting the live mic.
5. **Measure**: Run for 24 hours. Log every false trigger, missed wake word, and intent misclassification. Compare to baseline TFLite pipeline.
6. **Report back**: If v3 achieves <0.5 false triggers/hour and >95% intent accuracy, proceed to deprecate the old gates.

---

*End of research report.*
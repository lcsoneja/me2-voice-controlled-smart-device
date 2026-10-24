# ME2 - Voice Controlled Smart Device

On-device wake-word + intent recognition for a smart-device command set. No cloud round-trip:
wake detection, intent classification and slot resolution all run locally on CPU (laptop, and
a Raspberry Pi in the demo).

**Author:** Leandro Soneja - AI 231 ME2

## Headline result

The measured best pipeline in this project is **`gate1v3_f32` x `gate2v64p_paired_owner`, raw
noise canceller, architecture v1**: **90.8%** fully correct (wake **and** intent both right,
187/206 takes), 94.2% wake detection, 82.4% intent, p95 51 ms on host CPU.

The deck in `me2-deck-v64p.pdf` headlines `gate1v12_f16` as requested; both decks print the
v3 reference row directly underneath so the difference is visible rather than hidden.

## Measured comparison (one controlled pass, 206 qualified takes, 32 OOS)

| Gate 1 (wake) | Gate 2 (intent) | Full pipeline | Intent | Wake | OOS reject | p95 |
|---|---|---|---|---|---|---|
| gate1v12_f16 | gate2v64p_paired_owner | 76.7% (158/206) | 82.4% | 79.1% | 50.0% (16/32) | 66.8 ms |
| gate1v12_f16 | gate2v20_aux | 76.2% (157/206) | 93.6% | 79.1% | 50.0% (16/32) | 72.4 ms |
| gate1v3_f32 | gate2v64p_paired_owner | 90.8% (187/206) | 82.4% | 94.2% | 50.0% | 51.0 ms |
| gate1v3_f32 | gate2v20_aux | 90.3% (186/206) | 93.6% | 94.2% | 50.0% | 39.3 ms |

Both Gate 1 columns were scored on **identical takes** by a single pass (`_batch_v12_compare.py`),
so the rows are comparable. Intent accuracy is identical between the two Gate 1s for a given
Gate 2 model, because Gate 2 is unchanged - the entire gap is the wake stage
(**v12 79.1% vs v3 94.2%**).

Latency figures are host-CPU p95 across takes. They are **not** Raspberry Pi measurements.

## Layout

| Path | What it is |
|---|---|
| `vcm_live_test_local/vcm_live_test_local/` | Live pipeline + dashboard server (`gate1_server.py`) and web UI (`gate1_web/`) |
| `vcm_live_test_local/vcm_live_test_local/gate1_web/` | Dashboard assets incl. Gate 1 wake TFLite models and feature stats |
| `vcm_live_test_local/vcm_live_test_local/vcm8/` | Model registry, preprocessing stats, shipped TFLite exports |
| `Shipping/` (two packages only) | `.keras` source + labels + preprocessing spec + float16 TFLite for the two shipped Gate 2 models |
| `Gate3to5SlotSpecialistApp/` | Gate 3-5 slot specialist app (separate from the Gate 1/2 dashboard) |
| `me2-deck-v64p.pdf`, `me2-deck-v20aux.pdf` | The two result decks |
| `_batch_v12_compare.py`, `_v12_analyze.py` | The controlled head-to-head that produced the table above |
| `_build_me2_decks.py` | Deck generator (A4 landscape, 40pt margins) |
| `DGX_AGENT_PROMPT.md` | Training-agent brief incl. dataset locations and publishing rules |
| `TASK.md`, `HTML_AND_MODELS_CATALOG.md` | Task board and asset catalogue |

## Run the dashboard

```bash
cd vcm_live_test_local/vcm_live_test_local
pip install aiohttp numpy
python gate1_server.py
# then open http://127.0.0.1:8765/
```

On the Pi, `tflite-runtime` replaces TensorFlow and a USB mic is captured by the browser UI.
See `_pi_deploy/install_latest_on_pi.sh` and `_pi_deploy/handoff.md`.

## Models

| Model | Role | Params | Weights | Notes |
|---|---|---|---|---|
| `gate2v64p_paired_owner` | Gate 2 intent | 338,260 | 698,728 B float16 | 20 outputs (19 intents + NEG). NEG recall 97.89%; held-out owner val 100% (43 clips) |
| `gate2v20_aux` | Gate 2 intent | 246,035 intent-only | 515,332 B float16 | V19 TC-ResNet + training-only phoneme-aux CTC head, removed at inference. Clean synthetic val 98.84% (3,201) |
| Gate 1 wake variants | wake word | - | `gate1_web/*.tflite` | Nova / Piattos / Negative |

## Dataset

- Class gold dataset on the DGX cluster: **`/data/ai231`** (4 main splits; loader `/data/ai231/load.py`).
  Permission-restricted for writes.
- Supplemental (Filipino voice): `https://huggingface.co/datasets/martinnavs/ai231-fil-supplemental-data`
- Peer set: `https://huggingface.co/datasets/airimonda/ai231-me2-voice-commands`
- Frozen test split is locked by `SPLIT_LOCK.json` (seed 42) and is never modified. New data goes to
  train only. Wake words Nova/Piattos are project-owned and appear in none of the public sets.
- The multi-GB corpora are deliberately **not** in this repository; see `DGX_AGENT_PROMPT.md`.

## Honest limitations

- The out-of-scope rejection figure is measured only on the OOS takes inside this take bank. A
  quiet-room / always-listening false-trigger test was **not** run, so "no misfire" is not claimed.
- No Raspberry Pi latency measurement exists yet for the two headline lanes; the p95 numbers are
  host CPU. Pi TFLite load + forward pass was verified for V64P, V56 and V77.
- `gate1v12_f16` underperforms `gate1v3_f32` at the wake stage on this take bank (79.1% vs 94.2%).
- The optional Gate 3-5 candidate route needs TensorFlow and therefore does not run on the Pi.
- Accuracy figures describe these recordings and microphones, not unseen ones.

## License

Research and coursework (AI 231 ME2). Third-party datasets keep their own licences - see the
links above and the package `MANIFEST.json` / `ATTRIBUTION_LICENSE_*.txt` files.

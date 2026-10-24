# VCM HTML Apps & Gate 2 Model Test Catalog

**Purpose:** one index for the HTML applications, the Gate 1 wake model, and the Gate 2 models in Exercise 2b. Updated 2026-10-22 (36 new Gate2 folders reviewed; verified adapters selectable, remainder visibly disabled — and the same day's wake + reply updates below).

## Start here: live all-in-one dashboard

- **Windows laptop through the SSH tunnel:** [Open the live dashboard](http://localhost:8766/pipeline_all_in_one.html)
- **On the Raspberry Pi itself:** [Open on the Pi](http://localhost:8765/pipeline_all_in_one.html)
- **Local source page:** [pipeline_all_in_one.html](vcm_live_test_local/vcm_live_test_local/gate1_web/pipeline_all_in_one.html)
- **Alternate extension test:** [pipeline_all_in_one.thml](vcm_live_test_local/vcm_live_test_local/gate1_web/pipeline_all_in_one.thml) — served as `text/html`; it renders the same dashboard as the .html page.

The dashboard contains the **Gate 1 wake model** selector, the Gate 2 model selector, mic/pipe views, the recorded-voice scoring panel, the Gate 1/Gate 2 trigger timeline, and the embedded room simulation. Keep the default **Gate2 v21p** for the baseline unless you are deliberately comparing another version (the Gate 1 default is now **v12**, see below).

## Gate 1 wake model + assistant replies (updated 2026-10-22)

**Wake model default changed to `gate1v12_f16`** (warp + frequency masks, internal val 90.43%). On the synthetic clips it fixes two defects of the previous `gate1v8_f32` default:

| Clip | V8 f32 (previous default) | V12 f16 (default now) |
|---|---|---|
| wake "Nova" | Nova 0.879 ✓ | Nova 0.996 ✓ |
| wake "Piattos" | Nova 0.915 ✗ wrong persona | Piattos 1.000 ✓ |
| command "Call" | Negative 1.000 ✓ | Negative 0.922 ✓ |
| command "Stop" | Nova 0.943 ✗ false wake | Negative 0.815 ✓ |

- `gate1v12_f16` ships no normalization stats; it uses the V8 train-only stats. That fallback was measured across all five shipped stat sets (wake clips >0.99 for their persona, command clips Negative in every case).
- **`gate1v8c_f16` is listed but disabled**: its input is (1,49,40,1), so it needs a 49×40 wake frontend adapter. It is the strongest wake candidate in the tree (pure TC-ResNet, 224,259 params, 468 KB f16, sealed 19/20 — Nova 9/10, Piattos 10/10, BUILTINS-only, no Flex). Model staged at `gate1_web/gate1v8c_float16.tflite`.
- `gate1v8_f32`/`gate1v8_f16` stay selectable (previous default, first fallback); `gate1v10_*` stay selectable and are labelled as the failed benchmark.

**Assistant replies are one word per command** (pack [Gate2_AssistantResponses_ONEWORD_20261022](Shipping/Gate2_AssistantResponses_ONEWORD_20261022/)): 19 intents × 2 personas × 2 variants plus a **wake acknowledgement** pair — Nova says "Yes?", Piattos says "Hi". The dashboard captions exactly what the speech plays, and the Pi demo app now prefers its matching one-word pack (`DemoApp/responses/oneword-sapi`). Swap back with `VCM_ASSISTANT_PACK=Gate2_AssistantResponses_20261017`.

### Quick Gate 2 comparison workflow

1. Open the live all-in-one dashboard above.
2. Choose a value in **Gate 2 model**. Wait for the status message confirming the model was loaded; if there is an error, do not score that candidate.
3. Run **Score 280 recordings** to compare the selected model on the same offline evaluation set. Confirm the returned model name before recording the score.
4. For a live check, use the same wake phrase and command phrase for every version. The [Gate 2 Phrase Lab](vcm_live_test_local/vcm_live_test_local/gate1_web/gate2_phrase_recorder.html) is available for phrase recording/testing.
5. Keep the cadence and microphone conditions fixed across comparisons. Gate2 v16/v18/v19 variants have **19 intent outputs** and no NEGATIVE class; v21/v22 and the newer NEG variants have **20 outputs including NEGATIVE**. New single-window experiments keep the familiar one-window path; slide-window experiments build 5/9/17 shifted channels from the same window; V23 resizes to 50x30; V34a/V34b use their own frontends.
6. Restore **Gate2 v21p** after comparison if you want the existing default again.

**Scope note:** model selection changes the active Gate 2 runner on the shared live server. Use one dashboard session while comparing versions so another open dashboard does not switch the model mid-test.

## Gate 2 models selectable in the dashboard

Each package uses its package-owned labels and preprocessing statistics. The shipped float16 TFLite artifact is used where applicable. Experimental/historical status is called out rather than hidden.

| Selector value | Dashboard label | Shipping package / source | Outputs | Status / notes |
|---|---|---|---:|---|
| `gate2v2` | G2 v2 · TFLite (Pi-safe) | [Gate2V2 float16](vcm_live_test_local/vcm_live_test_local/gate1_web/gate2v2_float16.tflite) · [float32](vcm_live_test_local/vcm_live_test_local/gate1_web/gate2v2_float32.tflite) | 19 intents | Existing legacy baseline. |
| `gate2v6_keras` | G2 v6 · Keras (laptop) | [Gate2V6 package](Shipping/Gate2V6_ship_20261013/) | 19 intents | Existing Keras option; requires the Keras/TensorFlow runtime. |
| `gate2v16` | G2 v16 · historical candidate | [Gate2V16](Shipping/Gate2V16_ship_20261017/) | 19 intents | Manifest identifies it as a historical demo candidate. |
| `gate2v18` | G2 v18 · 19 intents | [Gate2V18](Shipping/Gate2V18_ship_20261017/) | 19 intents | Shipped package; older 19-intent generation. |
| `gate2v19` | G2 v19 · 19 intents | [Gate2V19](Shipping/Gate2V19_ship_20261017/) | 19 intents | Shipped package. |
| `gate2v19p` | G2 v19p · owner-finetuned · experimental | [Gate2V19P](Shipping/Gate2V19P_ship_EXPERIMENTAL_20261017/) | 19 intents | Experimental P variant; uses v19 preprocessing spec. |
| `gate2v21` | G2 v21 · NEGATIVE | [Gate2V21](Shipping/Gate2V21_ship_20261017/) | 20 (includes NEGATIVE) | Shipped package. |
| `gate2v21p` | G2 v21p · owner-finetuned · experimental (default) | [Gate2V21P](Shipping/Gate2V21P_ship_EXPERIMENTAL_20261017/) | 20 (includes NEGATIVE) | Existing dashboard default; experimental P variant; uses v21 preprocessing spec. |
| `gate2v22` | G2 v22 · experimental · NEGATIVE | [Gate2V22](Shipping/Gate2V22_ship_20261017/) · [manifest](Shipping/Gate2V22_ship_20261017/MANIFEST.json) · [labels](Shipping/Gate2V22_ship_20261017/labels.json) | 20 (includes NEGATIVE) | **Included from Shipping at your request.** Its manifest marks the package experimental. Uses the common 148×60, 16 kHz preprocessing contract. |
| `gate2v22s` | G2 v22s · experimental · SilenceNeg | [Gate2V22 SilenceNeg](Shipping/Gate2V22_SilenceNeg_ship_EXPERIMENTAL_20261017/) | 20 (includes NEGATIVE) | Experimental silence-negative variant. |
| `gate2v20_aux` | G2 v20 · phoneme-aux (intent-only) | [Gate2V20 PhonemeAux](Shipping/Gate2V20_PhonemeAux_ship_EXPERIMENTAL_20261018/) | 19 intents | Intent-only deployed path; training-only phone head removed. |
| `gate2v23_crnn50x30` | G2 v23 · CRNN 50×30 | [Gate2V23](Shipping/Gate2V23_CRNN50x30_ship_EXPERIMENTAL_20261017/) | 19 intents | Area-resized 148x60 to 50x30; same ~5.92 s coverage. |
| `gate2v24_crnn148x60` | G2 v24 · CRNN 148×60 | [Gate2V24](Shipping/Gate2V24_CRNN148x60_ship_EXPERIMENTAL_20261017/) | 19 intents | CRNN on the standard 148x60 window. |
| `gate2v25` | G2 v25 · keyword-mix | [Gate2V25](Shipping/Gate2V25_ship_EXPERIMENTAL_20261018/) | 19 intents | Same V19 CNN shape; keyword-mined data experiment. Uses v19 stats fallback. |
| `gate2v25_phraseconcat` | G2 v25 · phrase-concat | [Gate2V25 PhraseConcat](Shipping/Gate2V25_PhraseConcat_ship_EXPERIMENTAL_20261019/) | 19 intents | Phrase-concat variant. |
| `gate2v26` | G2 v26 · 20-class NEGATIVE | [Gate2V26](Shipping/Gate2V26_ship_EXPERIMENTAL_20261018/) | 20 (includes NEGATIVE) | 20-output variant. |
| `gate2v26_phraseconcat_neg` | G2 v26 · phrase-concat + NEGATIVE | [Gate2V26 PhraseConcat NEG](Shipping/Gate2V26_PhraseConcat_NEG_ship_EXPERIMENTAL_20261019/) | 20 (includes NEGATIVE) | Phrase-concat plus NEGATIVE. |
| `gate2v28a_5win` | G2 v28a · 5-window slide | [Gate2V28A](Shipping/Gate2V28A_5WinSlide_ship_EXPERIMENTAL_20261019/) | 19 intents | 5 shifted channels from one window. |
| `gate2v28b_9win` | G2 v28b · 9-window slide | [Gate2V28B](Shipping/Gate2V28B_9WinSlide05_ship_EXPERIMENTAL_20261019/) | 19 intents | 9 shifted channels; basis for later slide models. |
| `gate2v29_deep9` | G2 v29 · deep 9-window | [Gate2V29 Deep](Shipping/Gate2V29_Deep9WinSlide_ship_EXPERIMENTAL_20261019/) | 19 intents | Deep 9-window variant. |
| `gate2v29b_wide9` | G2 v29b · wide 9-window | [Gate2V29B Wide](Shipping/Gate2V29B_Wide9WinSlide_ship_EXPERIMENTAL_20261019/) | 19 intents | Wide 9-window variant. |
| `gate2v34a_std` | G2 v34a · standard frontend | [Gate2V34A](Shipping/Gate2V34A_StdFrontend_ship_EXPERIMENTAL_20261019/) | 19 intents | Own 148-frame frontend/stats. |
| `gate2v34b_finehop` | G2 v34b · fine-hop frontend | [Gate2V34B](Shipping/Gate2V34B_FineHop10ms5ms_ship_EXPERIMENTAL_20261019/) | 19 intents | Own 1184-frame fine-hop frontend/stats. |
| `gate2v36_17win` | G2 v36 · 17-window slide | [Gate2V36](Shipping/Gate2V36_17WinSlide4s_ship_EXPERIMENTAL_20261019/) | 19 intents | 17 shifted channels. |
| `gate2v37_9win_neg` | G2 v37 · 9-window + NEGATIVE | [Gate2V37](Shipping/Gate2V37_9WinSlide_NEG_ship_EXPERIMENTAL_20261019/) | 20 (includes NEGATIVE) | 9-window slide plus NEGATIVE. |
| `gate2v38_crnn9` | G2 v38 · CRNN 9-window | [Gate2V38](Shipping/Gate2V38_CRNN_9WinSlide_ship_EXPERIMENTAL_20261019/) | 19 intents | CRNN over 9-window slide. |
| `gate2v40b_9win_attention` | G2 v40b · 9-window attention | [Gate2V40B](Shipping/Gate2V40B_9WinAttention_ship_EXPERIMENTAL_20261019/) | 19 intents | 9-window slide with attention. |
| `gate2v41_specaugmix` | G2 v41 · SpecAugMix | [Gate2V41](Shipping/Gate2V41_SpecAugMix_ship_EXPERIMENTAL_20261019/) | 19 intents | 9-window slide; SpecAugment/MixUp training. |
| `gate2v42_reverb` | G2 v42 · reverb/mic simulation | [Gate2V42](Shipping/Gate2V42_ReverbMicSim_ship_EXPERIMENTAL_20261019/) | 19 intents | 9-window slide; reverb/mic-sim training. |
| `gate2v46_impwarp` | G2 v46 · ImpWarp backbone | [Gate2V46](Shipping/Gate2V46_ImpWarp_ship_EXPERIMENTAL_20261020/) | 19 intents | V46 backbone behind the champion stack. |
| `gate2v47_windrop_melwarp` | G2 v47 · window dropout + MelWarp | [Gate2V47](Shipping/Gate2V47_WinDropout_MelWarp_ship_EXPERIMENTAL_20261020/) | 19 intents | 9-window slide variant. |
| `gate2v48_audiopack` | G2 v48 · AudioPack | [Gate2V48](Shipping/Gate2V48_AudioPack_ship_EXPERIMENTAL_20261020/) | 19 intents | 9-window slide variant. |
| `gate2v49_warpdilatedneg` | G2 v49 · Warp + dilated + NEGATIVE | [Gate2V49](Shipping/Gate2V49_WarpDilatedNEG_ship_EXPERIMENTAL_20261020/) | 20 (includes NEGATIVE) | Warp plus dilated body plus NEGATIVE. |
| `gate2v50_channelshuffle` | G2 v50 · channel shuffle | [Gate2V50](Shipping/Gate2V50_ChannelShuffle_ship_EXPERIMENTAL_20261020/) | 19 intents | 9-window slide variant. |
| `gate2v52_adjswap` | G2 v52 · adjacent swap | [Gate2V52](Shipping/Gate2V52_AdjSwap_ship_EXPERIMENTAL_20261020/) | 19 intents | 9-window slide variant. |
| `gate2v53_melbin_dropout` | G2 v53 · Mel-bin dropout | [Gate2V53](Shipping/Gate2V53_MelBinDropout_ship_EXPERIMENTAL_20261020/) | 19 intents | 9-window slide variant. |
| `gate2v57_pidgate` | G2 v57 · learnable PID feature gate | [Gate2V57](Shipping/Gate2V57_PIDGate_ship_EXPERIMENTAL_20261021/) | 19 intents | Learnable PID gate before the CNN. |
| `gate2v56_v54` | G2 v56 · V46 + V54 PID (accuracy winner) | [Gate2V56 ChampionStack](Shipping/Gate2V56_ChampionStack_V46_PID_ship_EXPERIMENTAL_20261020/) | 19 intents + streaming NEGATIVE reject | V46 9-window model plus streaming V54 PID evidence integrator. |
| `gate2v56_v54b` | G2 v56 · V46 + V54b margin PID (reject winner) | [Gate2V56 ChampionStack](Shipping/Gate2V56_ChampionStack_V46_PID_ship_EXPERIMENTAL_20261020/) | 19 intents + streaming NEGATIVE reject | Same V46 backbone plus margin/consistency PID for rejection. |

The selector uses one float16 TFLite file per compatible package. Other quantized files in each package are not separate selector entries. Candidates without a verified adapter stay visible but disabled in the dashboard, with the reason shown inline. The older/reference folders below are not presented as runnable dashboard models unless they have a compatible TFLite package listed above.

### Shipped candidates visible but disabled (adapter pending)

| Selector value | Dashboard note | Shipping package | Why it is disabled |
|---|---|---|---|
| `gate2v20_phonecascade` | G2 v20 · PhoneCascade — two-stage adapter pending | [Gate2V20 PhoneCascade](Shipping/Gate2V20_PhoneCascade_ship_EXPERIMENTAL_20261018/) | Two-stage phone-posterior cascade; needs a dedicated cascade runner. |
| `gate2v27a_3winalign` | G2 v27a · 3-window alignment adapter pending | [Gate2V27A](Shipping/Gate2V27A_3WinAlign_ship_EXPERIMENTAL_20261019/) | Start/center/end alignment frontend is not implemented. |
| `gate2v27c_meldelta` | G2 v27c · Mel/delta frontend adapter pending | [Gate2V27C](Shipping/Gate2V27C_MelDelta_ship_EXPERIMENTAL_20261019/) | Mel/delta/delta-delta frontend is not implemented. |
| `gate2v39_36ch_derivcum` | G2 v39 · 36-channel derivative adapter pending | [Gate2V39](Shipping/Gate2V39_36Ch_SlideDerivCum_ship_EXPERIMENTAL_20261019/) | Needs derived-stat handling for derivative/cumulative channels. |
| `gate2v40a_18ch_deriv` | G2 v40a · 18-channel derivative adapter pending | [Gate2V40A](Shipping/Gate2V40A_18ChDeriv_ship_EXPERIMENTAL_20261019/) | Needs derived-stat handling for derivative channels. |
| `gate2v40c_18ch_deriv_attention` | G2 v40c · 18-channel derivative/attention adapter pending | [Gate2V40C](Shipping/Gate2V40C_18ChDerivAttention_ship_EXPERIMENTAL_20261019/) | Needs derived-stat handling for derivative/attention channels. |
| `gate2v45_keywordpairs` | G2 v45 · missing labels/preprocessing metadata | [Gate2V45](Shipping/Gate2V45_KeywordPairs_ship_EXPERIMENTAL_20261019/) | No labels.json or preprocessing_spec.json, so it cannot be registered safely. |
| `gate2v51_realchannel` | G2 v51 · missing preprocessing metadata | [Gate2V51](Shipping/Gate2V51_RealChannel_ship_EXPERIMENTAL_20261020/) | No preprocessing_spec.json, so the channel recipe is unverified. |

### Winning model: V56 champion stack (V46 + PID)

- Winning package: [Gate2V56 ChampionStack V46 PID](Shipping/Gate2V56_ChampionStack_V46_PID_ship_EXPERIMENTAL_20261020/).
- Accuracy winner: `gate2v56_v54` (V54 plain PID on V46). Rejection winner: `gate2v56_v54b` (V54b margin PID with consistency penalty). Both are selectable.
- The V56 TFLite file is the V46 9-window backbone; the PID evidence integration runs in the live server from the shipped `deploy/pid_stream_integrator.py` recipe. V54b tuning is read from the shipped `reports/v54b_pid_tuning.json` values.
- Live behavior: the server keeps per-connection PID state, resets it on silence/mode/reset/manual-stop/action boundaries, and reports an extra NEGATIVE output when the PID loop has not accepted an intent.

## HTML pages and apps in Exercise 2b

### Live VCM dashboard and monitors

| Page | What it is |
|---|---|
| [All-in-one pipeline dashboard](vcm_live_test_local/vcm_live_test_local/gate1_web/pipeline_all_in_one.html) | Main live dashboard; includes model selection, model scoring, room simulation, and G1/G2 trigger timeline. |
| [All-in-one .thml alias](vcm_live_test_local/vcm_live_test_local/gate1_web/pipeline_all_in_one.thml) | Same page/content, served as HTML for extension testing. |
| [VCM monitor](vcm_live_test_local/vcm_live_test_local/gate1_web/vcm_monitor.html) | Combined Gate 1 / Gate 2 monitor. |
| [Gate 1 monitor](vcm_live_test_local/vcm_live_test_local/gate1_web/gate1_monitor.html) | Legacy Gate 1 monitor page. |
| [Gate 1 monitor v2](vcm_live_test_local/vcm_live_test_local/gate1_web/gate1_monitor_v2.html) | Gate 1 v2 monitor. |
| [Gate 1 monitor v3](vcm_live_test_local/vcm_live_test_local/gate1_web/gate1_monitor_v3.html) | Gate 1 v3 monitor. |
| [Gate 1 monitor v4](vcm_live_test_local/vcm_live_test_local/gate1_web/gate1_monitor_v4.html) | Gate 1 v4 monitor. |
| [Gate 1 monitor v5](vcm_live_test_local/vcm_live_test_local/gate1_web/gate1_monitor_v5.html) | Gate 1 v5 monitor. |
| [Standalone room simulation](vcm_live_test_local/vcm_live_test_local/gate1_web/room_sim.html) | Room simulator viewer; the same simulation is embedded in the main dashboard. |

### Recording and model test tools

| Page | What it is |
|---|---|
| [Gate 2 Phrase Lab](vcm_live_test_local/vcm_live_test_local/gate1_web/gate2_phrase_recorder.html) | Record/review Gate 2 command phrases. |
| [Gate 2 dataset recorder](vcm_live_test_local/vcm_live_test_local/gate1_web/dataset_recorder.html) | Capture dataset recordings. |
| [VCM Recording Lab](vcm_live_test_local/vcm_live_test_local/gate1_web/recording_lab.html) | Capture the last 30 s from the live dashboard, replay one recording through every Gate 2 model offline, and compare saved Gate 1 / Gate 2 / Gate 3 trigger charts. |
| [Gate 2 RNNoise A/B test](vcm_live_test_local/vcm_live_test_local/gate1_web/gate2_rnnoise_test.html) | Noise-cancellation comparison page. |

### Other apps and diagnostics

| Page | What it is |
|---|---|
| [VCM DemoApp](DemoApp/web/index.html) | DemoApp command dashboard. |
| [Gate 3–5 Slot Specialist candidates](Gate3to5SlotSpecialistApp/index.html) | Specialist candidate application. |
| [Voice Studio](VoiceStudio/VoiceStudio.html) | Offline voice recorder/studio. |
| [Diagnostic root page](_diag_root.html) | Diagnostic monitor snapshot. |
| [Diagnostic root page 2](_diag_root2.html) | Second diagnostic monitor snapshot. |

## Gate 2 reference folders not exposed as a dashboard model

- [Gate2V6 float16 TFLite asset](Shipping/Gate2V6_ship_20261013/tflite/gate2v6_float16.tflite) is **not Pi-compatible in the current runner**: a local smoke test failed allocation on the FlexTensorListReserve op. It is therefore intentionally omitted from the Pi dropdown. The separate Gate2 v6 Keras option remains marked laptop-only.

- [Gate2V22 owner-280 correct-vs-incorrect diagnostic](Shipping/Gate2V22_Owner280_CorrectVsIncorrect_DIAGNOSTIC_20261017/) — diagnostic package; not a selectable runtime model.
- [Gate2V3 shipping folder](Shipping/Gate2V3_ship/) — older/reference package.
- [Gate2V6 phrase inventory](Shipping/Gate2V6_Phrase_Inventory_20261008/) — phrase/reference material.
- [Gate2V7 owner-voice review](Shipping/Gate2V7_OwnerVoice_Review_20261008/) — review material.
- [Gate2V8 explainer](Shipping/Gate2V8_Explainer_20261014/) — explainer/reference material.

## Runtime references

- Live server: `vcm_live_test_local/vcm_live_test_local/gate1_server.py`
- Gate 2 package registration: `GATE2_PACKAGE_RUNNERS` in that server.
- Model options and test controls: `gate1_web/pipeline_all_in_one.html`.
- Main page on the Pi: `http://localhost:8765/pipeline_all_in_one.html`. On the Windows tunnel: `http://localhost:8766/pipeline_all_in_one.html`.

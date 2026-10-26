# Offline VCM noise-cancellation benchmark — 2026-10-17

## Summary
**Recommendation: use a Wiener-filter variant using the current tracked noise profile** if cancellation is desired in the offline Pi-desktop pipeline. On this local run it provided nearly unchanged owner-voice RMS (median 98.96%, p10 96.37%), slightly less than the current spectral-subtraction method on real silence (3.60 vs 3.83 dB median attenuation), and lower measured CPU cost; unlike the ambient gate and fixed hum filter, it preserved low-level owner clips. This is an RMS-preservation benchmark, not a gate-recognition accuracy test.

## Findings

### Methods and protocol
- **A — current spectral subtraction + energy guard.** Ported `_nc_stft`, `_nc_noise_update`, and `_nc_apply` from `vcm_live_test_local/vcm_live_test_local/gate1_server.py`; constants kept at `_NC_STFT_N=400`, `_NC_HOP=160`, `_NC_BETA=2.0`, `_NC_FLOOR=0.08`, `_NC_EMA=0.08`, `_NC_LEAK=1.002`, `_NC_GUARD=0.55`. The only instrumentation counts entry into the unchanged guard branch.
- **B — Wiener.** Same tracker/profile, STFT and overlap-add; power gain is `max(0.08, |X|² / (|X|² + 2·profile²))`. No energy guard.
- **C — ambient-floor gate.** Simulated the existing `_track_ambient` rule from `gate1_server.py` on the 8 silent streams, then used a per-one-second soft gate (zero at/below floor, linear ramp to unity at 2× floor). Final tracked floor: **0.00782955 RMS**.
- **D — DC/hum-only.** NumPy FFT per 1-s frame: zero below 30 Hz, plus ±1-Hz notches for 50/60-Hz fundamentals and harmonics through 800 Hz.
- 16-kHz mono `float32`; 1-s ticks; 20-s ring; evaluate the newest 5.92 s (94,720 samples). A/B update their profile on each evaluation window. Shared A/B profile for voice tests was adapted from silence only, then frozen. Owner clips were placed at the end of a zero-padded 5.92-s window; gate/notch were run in 1-s chunks. Voice metric is processed/raw RMS, not intelligibility or classifier accuracy.
- Owner data: **150 WAVs** from `Shipping/real_voice_owner/audio`, cross-checked against `Shipping/real_voice_owner/manifest_150.csv`; median clip duration 1.61066 s, maximum 3.43469 s. Silent data: **8 recordings** in `Shipping/10randomMicSilentRecordings`. They are **M4A, not WAV**; local `C:/ffmpeg/bin/ffmpeg.exe` decoded them to mono 16-kHz float audio. Audio processing used NumPy only. Durations were 6.827, 4.864, 6.528, 7.829, 7.061, 10.091, 7.317, and 8.320 s. One recording (<5.92 s) was tiled once to provide a full stationary-noise evaluation window; longer files were evaluated after the ring filled. There were 24 real-noise evaluation/profile-update windows.
- Synthetic hum+hiss: 50/100/60/120-Hz sinusoidal components plus seeded white noise (0.35 relative amplitude before normalization), scaled so noise RMS equals median owner RMS / 10^(SNR/20). Thus “SNR” is an amplitude reference for noise-only samples, not a speech-mixture recognition test. Seeds: 0 dB—20261017; 5 dB—20261022; 10 dB—20261027; 20 dB—20261037. Median owner RMS reference was 0.02377144.

### Comparison
| Approach | Real silent noise median attenuation | Owner RMS retention (median / p10) | 900-Hz tone retention | Local CPU ms / eval | Pi-5 estimate ms / eval (×4) | Guard fires / blends | Approx. implementation |
|---|---:|---:|---:|---:|---:|---:|---:|
| A. Spectral subtraction + guard | 3.83 dB | 92.95% / 85.03% | 99.09% | 12.28 | 49.12 | 20/24 (83.33%) | ~65 lines including tracker/guard |
| B. Wiener, same profile | 3.60 dB | **98.96% / 96.37%** | 100.06% | **10.71** | **42.84** | n/a | ~30 additional lines plus shared tracker/STFT |
| C. Ambient-floor gate | effectively muted (reported >249 dB; numerical-floor limited) | 98.54% / 51.82% | 100.00% | 0.017 | 0.067 | n/a | ~15 lines |
| D. High-pass + hum notches | **7.00 dB** | 90.15% / 76.00% | 100.00% | 0.287 | 1.147 | n/a | ~20 lines |

Median attenuation is computed over the available 1-Hz evaluation windows; the ambient-gate attenuation is a mute, not evidence of useful graded denoising. The 900-Hz tone was scaled to the median owner-clip RMS.

### Synthetic stationary hum+hiss attenuation (dB)
| SNR reference | A. Spectral subtraction | B. Wiener | C. Ambient gate | D. High-pass/notch |
|---:|---:|---:|---:|---:|
| 0 dB | -0.68 | 2.00 | 0.00 | 8.70 |
| 5 dB | -1.01 | 1.88 | 3.01 | 8.85 |
| 10 dB | -0.73 | 2.62 | >257* | 8.85 |
| 20 dB | -0.50 | 2.27 | >247* | 8.75 |

\*Ambient-gate output falls below the 1e-15 RMS ratio floor used for dB conversion; this is effectively muting at the fixed ambient threshold, not a meaningful >247-dB denoising capability. The spectral-subtraction synthetic results are slightly negative (output RMS increased by about 6–12%); treat that as a warning about this profile/OLA setup, not as a general result for all hum/noise conditions.

### Interpretation and recommendation
1. **Wiener is the best balanced default in this test.** It retains more voice than A, costs less locally, and sacrifices only 0.23 dB of median real-silence attenuation. The 900-Hz tone is preserved. This makes it the safer candidate for listening/recognition validation before deployment.
2. **The current method’s global energy guard is frequently active on noise-only windows:** 20 of 24 (83.33%). It limits over-subtraction but often blends raw audio back, and the synthetic results did not show net suppression. Keep it only if behavioral parity is a stronger requirement than measured noise reduction; do not assume its guard is rarely used.
3. **The ambient gate is not a good substitute for cancellation.** It mutes quiet noise, but the owner p10 retention is only 51.82%, so low-energy utterances are at material risk. It behaves as a coarse activity gate.
4. **The hum filter wins on noise-only attenuation but misses the stated voice-preservation aim.** Its p10 retention is 76.00%; the fixed 30-Hz high-pass and multi-notch response can remove speech energy. It is best considered an optional narrow mains-hum cleanup, not a general canceller.
5. All Pi-5 numbers are **estimates**, calculated as 4× local Python timings, not measurements on a Pi 5. Timings include tracked-profile update plus filtering for A/B and one 1-s filter/gate pass for C/D; they are median of 20 local calls after 3 warm-ups.

## Evidence and sources
- **Direct evidence:** `vcm_live_test_local/vcm_live_test_local/gate1_server.py` — exact NC helper implementation/constants and ambient tracking rule.
- **Direct evidence:** `Shipping/real_voice_owner/manifest_150.csv` and `Shipping/real_voice_owner/audio/` — owner utterance set and file count.
- **Direct evidence:** `Shipping/10randomMicSilentRecordings/` — eight local silent recordings; actual extension is `.m4a`.
- **Reproducibility artifacts:** `vcm_live_test_local/vcm_live_test_local/research_reports/_nc_bench_scratch/benchmark.py` and `results.json` (script and machine-readable result; fixed NumPy seeds recorded above).
- **Researcher interpretation:** Wiener is recommended because it yields the best balance among the measured proxies. This does not establish voice-command recognition equivalence or Pi timing.

## Residual risks / limitations
- Voice retention is RMS-only; no listening panel, intelligibility score, gate-model score, or noisy-speech recognition result was collected. The 150 owner WAVs were processed clean rather than mixed with synthetic noise.
- The source task described the silent inputs as WAVs, but the actual files are M4A. FFmpeg was present and used only for local decoding; the samples were not altered in project storage.
- One short silence recording was tiled to fill a 5.92-s window. This is a stationarity assumption and can bias its contribution.
- Notches/high-pass were fixed and broad (±1 Hz, harmonics through 800 Hz); real electrical hum drift may not match these bins.
- Pi-5 latency ×4 is an explicit rough scaling assumption. Run the same benchmark on the intended Pi hardware before accepting real-time latency.

## Next steps
1. Listen to processed owner clips and run a paired noisy-speech gate evaluation for Wiener versus current NC.
2. Measure the full A/B path on Pi 5, including streaming ring maintenance and gate inference, then validate end-to-end command recall.

# CosyVoice Synthetic Test Set Report

## Environment Status
- **Python Environment**: `$HOME/.conda/envs/cosyvoice3/bin/python`
- **PyTorch Version**: `2.3.1+cu121`
- **CUDA Available**: `True`
- **GPU Device**: `NVIDIA A100-SXM4-40GB`
- **CosyVoice Model**: `/mnt/jfs_hpc/home/leandro.soneja/models/Fun-CosyVoice3-0.5B` (Fun-CosyVoice3-0.5B)
- **Sampling Rate**: 16000 Hz mono PCM16
- **Dataset Policy Compliance**: TEST-ONLY set, strictly isolated from `data/` and `data/raw/`. Zero training usage.

## Dataset Summary
- **Total Generated Samples**: 20
- **Total Failures**: 0
- **Wake Word Samples**: 2 (Nova, Piattos)
- **Gate 2 Command Intents**: 11 (play music, what time is it, turn on the lights, volume up, call mama, what is the weather, next song, pause, stop, show my reminders, send a message)
- **Specialist Gate Samples**: 7 (Gate 3a Timer 10s/1min, Gate 3b Alarm 6AM, Gate 3c Temp 22deg, Gate 3d Brightness 60%, Gate 4 Color Blue, Gate 5 Reminder Drink Water)
- **Speaker Demographics**: 10 Female, 10 Male across 20 distinct verified speaker references
- **Acoustic Diversity**: Varied pitch (`higher`, `normal`, `lower`), varied speed (0.9x to 1.2x), distinct instruction prompt modifiers

## Voice Configurations & Diversity Matrix
| Sample File | Speaker Reference | Gender | Pitch Modifier | Speed | Transcript |
|---|---|---|---|---|---|
| `gate1_wake_nova_f01_pitchhigh_normal.wav` | `cvref-fluent-gvKeNY2D3Rs2jRdL` | female | higher | 1.0x | "Nova" |
| `gate1_wake_piattos_m01_pitchnorm_fast.wav` | `cvref-fluent-eLQ3mNg27GHLkDej` | male | normal | 1.2x | "Piattos" |
| `gate2_PLAY_MUSIC_f02_pitchnorm_fast.wav` | `cvref-fluent-Gym5dABePPHA8mZK9` | female | normal | 1.15x | "play music" |
| `gate2_TIME_m02_pitchlow_normal.wav` | `cvref-fluent-7NqqnAOPVVSKnxyv` | male | lower | 1.0x | "what time is it" |
| `gate2_LIGHT_ON_f03_pitchhigh_fast.wav` | `cvref-fluent-kNnmb7MdArswxLYw` | female | higher | 1.2x | "turn on the lights" |
| `gate2_VOLUME_UP_m03_pitchnorm_slow.wav` | `cvref-fluent-ZebMRl5Z7dhrPKRD` | male | normal | 0.9x | "volume up" |
| `gate2_CALL_f04_pitchlow_normal.wav` | `cvref-fluent-2ojo7YRL7Gck83Z3` | female | lower | 1.0x | "call mama" |
| `gate2_WEATHER_m04_pitchhigh_normal.wav` | `cvref-fluent-eL2w4ZBD7liA85wm` | male | higher | 1.05x | "what is the weather" |
| `gate2_NEXT_f05_pitchnorm_fast.wav` | `cvref-fluent-9MX3AgZzVgCw4W4j` | female | normal | 1.2x | "next song" |
| `gate2_PAUSE_m05_pitchlow_slow.wav` | `cvref-fluent-gNYvkbx3gof2Y3V9` | male | lower | 0.95x | "pause" |
| `gate2_STOP_f06_pitchhigh_normal.wav` | `cvref-fluent-V4ZbwLm9G5irobWn` | female | higher | 1.0x | "stop" |
| `gate2_LIST_REMINDERS_m06_pitchnorm_normal.wav` | `cvref-fluent-W4XOzzNEbrtZz4dW` | male | normal | 1.0x | "show my reminders" |
| `gate2_MESSAGE_f07_pitchlow_fast.wav` | `cvref-fluent-oOK5kxoW7dskMbaK` | female | lower | 1.15x | "send a message" |
| `gate3a_TIMER_10sec_m07_pitchnorm_fast.wav` | `cvref-fluent-kxgXN97ALmHbaezp` | male | normal | 1.15x | "set a timer for 10 seconds" |
| `gate3a_TIMER_1min_f08_pitchhigh_normal.wav` | `cvref-fluent-Ze7YenyZvxiB4MYZ` | female | higher | 1.0x | "set a timer for 1 minute" |
| `gate3b_ALARM_6AM_m08_pitchlow_normal.wav` | `cvref-fluent-g2dnA9Wpvzi2WAmZ` | male | lower | 1.05x | "set an alarm for 6 AM" |
| `gate3c_TEMP_22deg_f09_pitchlow_slow.wav` | `cvref-fluent-Q4vMvpXkXBsqryvZ` | female | lower | 0.95x | "set temperature to 22 degrees" |
| `gate3d_BRIGHT_60pct_m09_pitchhigh_fast.wav` | `cvref-fluent-NgQEvO2x7Vh3xy2xz` | male | higher | 1.15x | "set brightness to 60 percent" |
| `gate4_COLOR_Blue_f10_pitchnorm_normal.wav` | `cvref-fluent-DWmlpyg93YCXAXgE` | female | normal | 1.0x | "the color blue" |
| `gate5_REMIND_DrinkWater_m10_pitchnorm_fast.wav` | `cvref-fluent-X4vEl3glp9urv4GN` | male | normal | 1.1x | "remind me to drink water" |

## Generated Sample Verification Table
| File | Gate / Target | Gate2 Intent | Specialist Value | Duration (s) | Format | Stdlib `wave` Status | SHA256 (prefix) |
|---|---|---|---|---|---|---|---|
| `gate1_wake_nova_f01_pitchhigh_normal.wav` | gate1 | `-` | `-` | 0.600 | 16kHz Mono PCM16 | PASSED | `e56d00bd2207...` |
| `gate1_wake_piattos_m01_pitchnorm_fast.wav` | gate1 | `-` | `-` | 0.860 | 16kHz Mono PCM16 | PASSED | `d922af9c3a38...` |
| `gate2_PLAY_MUSIC_f02_pitchnorm_fast.wav` | gate2 | `PLAY_MUSIC` | `-` | 1.200 | 16kHz Mono PCM16 | PASSED | `eaa7f4335760...` |
| `gate2_TIME_m02_pitchlow_normal.wav` | gate2 | `TIME` | `-` | 0.960 | 16kHz Mono PCM16 | PASSED | `5dbfbaef8402...` |
| `gate2_LIGHT_ON_f03_pitchhigh_fast.wav` | gate2 | `LIGHT_ON` | `-` | 0.860 | 16kHz Mono PCM16 | PASSED | `96614b0fd9d7...` |
| `gate2_VOLUME_UP_m03_pitchnorm_slow.wav` | gate2 | `VOLUME_UP` | `-` | 0.920 | 16kHz Mono PCM16 | PASSED | `ef838afa57d1...` |
| `gate2_CALL_f04_pitchlow_normal.wav` | gate2 | `CALL` | `-` | 0.800 | 16kHz Mono PCM16 | PASSED | `53caf82ef3f9...` |
| `gate2_WEATHER_m04_pitchhigh_normal.wav` | gate2 | `WEATHER` | `-` | 1.100 | 16kHz Mono PCM16 | PASSED | `c39066bf6456...` |
| `gate2_NEXT_f05_pitchnorm_fast.wav` | gate2 | `NEXT` | `-` | 0.600 | 16kHz Mono PCM16 | PASSED | `766ca615529c...` |
| `gate2_PAUSE_m05_pitchlow_slow.wav` | gate2 | `PAUSE` | `-` | 0.620 | 16kHz Mono PCM16 | PASSED | `b838c4d03e66...` |
| `gate2_STOP_f06_pitchhigh_normal.wav` | gate2 | `STOP` | `-` | 0.520 | 16kHz Mono PCM16 | PASSED | `417684853fe8...` |
| `gate2_LIST_REMINDERS_m06_pitchnorm_normal.wav` | gate2 | `LIST_REMINDERS` | `-` | 1.400 | 16kHz Mono PCM16 | PASSED | `0f8e156763e6...` |
| `gate2_MESSAGE_f07_pitchlow_fast.wav` | gate2 | `MESSAGE` | `-` | 0.960 | 16kHz Mono PCM16 | PASSED | `3bd49e493be4...` |
| `gate3a_TIMER_10sec_m07_pitchnorm_fast.wav` | gate3a | `TIMER` | `10 seconds` | 1.560 | 16kHz Mono PCM16 | PASSED | `0799adc35379...` |
| `gate3a_TIMER_1min_f08_pitchhigh_normal.wav` | gate3a | `TIMER` | `1 minute` | 1.640 | 16kHz Mono PCM16 | PASSED | `053fda1dfdef...` |
| `gate3b_ALARM_6AM_m08_pitchlow_normal.wav` | gate3b | `ALARM` | `6 AM` | 1.740 | 16kHz Mono PCM16 | PASSED | `08e32487addb...` |
| `gate3c_TEMP_22deg_f09_pitchlow_slow.wav` | gate3c | `TEMPERATURE` | `22 degrees` | 2.640 | 16kHz Mono PCM16 | PASSED | `8caaff51d827...` |
| `gate3d_BRIGHT_60pct_m09_pitchhigh_fast.wav` | gate3d | `BRIGHTNESS` | `60 percent` | 1.760 | 16kHz Mono PCM16 | PASSED | `0bef31889066...` |
| `gate4_COLOR_Blue_f10_pitchnorm_normal.wav` | gate4 | `COLOR` | `Blue` | 1.080 | 16kHz Mono PCM16 | PASSED | `e05f62b112be...` |
| `gate5_REMIND_DrinkWater_m10_pitchnorm_fast.wav` | gate5 | `CREATE_REMINDER` | `Drink water` | 1.340 | 16kHz Mono PCM16 | PASSED | `5d577a7e18f9...` |

## Verification & QC Details
- **Audio Format Validation**: Each WAV verified with Python's standard library `wave` module for `nchannels == 1`, `sampwidth == 2` (16-bit), and `framerate == 16000`.
- **Amplitude Normalization**: Peak amplitudes verified <= 0.999 to prevent digital clipping.
- **Integrity Hashing**: SHA256 checksums recorded for full reproducibility and artifact traceability.
- **Failures**: 0

# PI_SETUP.md - Deploy real_session.py on Raspberry Pi 5

Real-time always-on VCM: USB mic -> wake word (gate1) -> command (gate2) -> value (gateN/gate4/gate5) -> terminal dashboard (PASS/FAIL). Keyboard controlled.

## 1. One-time setup on the Pi (Raspberry Pi OS Bookworm 64-bit)

    sudo apt update && sudo apt install -y python3-pip libportaudio2
    pip3 install numpy sounddevice tflite-runtime --break-system-packages

No TensorFlow, no librosa needed - preprocessing is numpy-only (mel_fb.npz is precomputed and shipped).

## 2. Copy from the laptop

    scp -r vcm8/ mel_fb.npz real_session.py pi@<pi-ip>:~/vcm/
    # Needed files inside vcm8/: config/model_registry.json,
    # training/feature_stats.npz, training/tflite/*_float16.tflite

## 3. Verify the mic, then run

    arecord -l                                  # find USB mic
    python3 real_session.py --check             # backend + models verification
    python3 real_session.py --device 1          # always-on assistant
    # In the UI: [space] force command mode, [m] mute, [h] help, [q] quit

Backend auto-detects tflite_runtime on the Pi; on the laptop it uses Keras checkpoints.

## 4. Auto-start (systemd, optional)

    sudo tee /etc/systemd/system/vcm-real.service <<'EOF'
[Unit]
Description=VCM real-time assistant
After=multi-user.target sound.target

[Service]
User=pi
WorkingDirectory=/home/pi/vcm
ExecStart=/usr/bin/python3 real_session.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl enable --now vcm-real.service

Note: the dashboard needs a terminal; run it in a tmux session on the Pi monitor,
or attach via SSH. GPIO LED/switch hooks can be added later.

## 5. Known model caveats (from laptop validation)
- gate1 (wake) is weak out-of-domain: it may miss real-voice wake words and
  rarely false-triggers. Wake-word retraining data is being collected
  (see DGX_HANDOFF.md T2). Lower --min-conf if wakes are missed.
- gateN v1 TFLite (74-frame) is used on the Pi; the laptop can additionally use
  gateN_v2_compound (148-frame Keras) automatically when present.

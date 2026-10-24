#!/usr/bin/env bash
set -u
APP_DIR="$HOME/Exercise2/vcm_live_test_local/vcm_live_test_local"
URL="http://127.0.0.1:8765"
LOG="$APP_DIR/server.log"

check_models_api() {
    local response
    response="$(curl -fsS --max-time 3 "$URL/api/lab/models" 2>/dev/null)" || return 1
    printf '%s' "$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); n=len(d.get("models", [])); print(f"Gate2 models: {n}"); sys.exit(0 if n >= 56 else 1)' >/dev/null
}

# Reuse a healthy current server; restart stale builds whose models API is missing.
if ! check_models_api; then
    # Match only the exact app process; do not kill this launcher/SSH shell.
    pkill -f '^python3 gate1_server\.py$' 2>/dev/null || true
    sleep 1
    cd "$APP_DIR" || exit 1
    nohup python3 gate1_server.py >> "$LOG" 2>&1 </dev/null &
    started=$!
    ok=0
    for _ in $(seq 1 30); do
        if check_models_api; then ok=1; break; fi
        if ! kill -0 "$started" 2>/dev/null; then break; fi
        sleep 1
    done
    if [ "$ok" -ne 1 ]; then
        echo "VCM dashboard did not become healthy. Check: $LOG"
        command -v notify-send >/dev/null 2>&1 && notify-send "VCM Dashboard failed" "Check $LOG" || true
        exit 1
    fi
fi

if ! curl -fsS --max-time 3 "$URL/" >/dev/null; then
    echo "VCM model API is healthy, but dashboard page failed: $URL/"
    exit 1
fi
if command -v xdg-open >/dev/null 2>&1 && { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; }; then
    nohup xdg-open "$URL/" >/dev/null 2>&1 </dev/null &
fi
echo "VCM dashboard ready: $URL/"

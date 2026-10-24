#!/usr/bin/env bash
# Non-destructive deploy of the pipeline payload to the Pi.
#
# The previous installer moved $APP aside and relied on an ERR trap to put it back;
# when the trap re-entered, the app directory was left empty and the dashboard served
# 500s. This script never moves or deletes the app or the model packages: it takes a
# copy-backup and then copies files over the top. A failure restores from that copy.
set -u

ARCHIVE="$HOME/vcm_pi_latest_20261024.tar.gz"
ROOT="$HOME/Exercise2"
APP="$ROOT/vcm_live_test_local/vcm_live_test_local"
SHIPPING="$ROOT/Shipping"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
STAGE="$ROOT/.safe-stage-$STAMP"
BK="$ROOT/_backups/safe-$STAMP"
URL="http://127.0.0.1:8765"

say() { echo "$*"; }

[ -f "$ARCHIVE" ] || { say "FAIL archive missing: $ARCHIVE"; exit 2; }
[ -f "$APP/gate1_server.py" ] || { say "FAIL app missing before deploy: $APP"; exit 2; }

say "=== safe deploy $STAMP ==="
say "archive=$(wc -c < "$ARCHIVE") bytes"
say "before: app=$(wc -c < "$APP/gate1_server.py") bytes  sha=$(sha256sum "$APP/gate1_server.py" | cut -c1-16)"

# 1. copy-backup (no move, no delete)
mkdir -p "$BK" "$STAGE"
cp -a "$APP" "$BK/app-backup"
say "backup: $BK/app-backup"

# 2. extract the payload
if ! tar -xzf "$ARCHIVE" -C "$STAGE"; then say "FAIL extract"; exit 2; fi
PAYLOAD="$STAGE/Exercise2/vcm_live_test_local/vcm_live_test_local"
[ -f "$PAYLOAD/gate1_server.py" ] || { say "FAIL payload incomplete"; exit 2; }

# 3. copy over the top (existing files are overwritten; nothing is removed)
cp -a "$PAYLOAD/." "$APP/"
mkdir -p "$ROOT/Gate3to5SlotSpecialistApp"
[ -d "$STAGE/Exercise2/Gate3to5SlotSpecialistApp" ] && cp -a "$STAGE/Exercise2/Gate3to5SlotSpecialistApp/." "$ROOT/Gate3to5SlotSpecialistApp/"
mkdir -p "$SHIPPING"
[ -d "$STAGE/Exercise2/Shipping" ] && cp -a "$STAGE/Exercise2/Shipping/." "$SHIPPING/"
mkdir -p "$HOME/Desktop"
for f in restart_vcm.sh vcm-dashboard.desktop handoff.md; do
    [ -f "$STAGE/Desktop/$f" ] && cp -a "$STAGE/Desktop/$f" "$HOME/Desktop/$f"
done
chmod +x "$HOME/Desktop/restart_vcm.sh" "$HOME/Desktop/vcm-dashboard.desktop" 2>/dev/null || true
find "$APP" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
say "after copy: app=$(wc -c < "$APP/gate1_server.py") bytes  sha=$(sha256sum "$APP/gate1_server.py" | cut -c1-16)  tflite=$(find "$SHIPPING" -name '*.tflite' | wc -l)"

# 4. restart and verify
pkill -f 'python3 .*gate1_server\.py' 2>/dev/null || true
sleep 2
cd "$APP" || { say "FAIL cd app"; exit 2; }
nohup python3 gate1_server.py >> server.log 2>&1 </dev/null &
OK=0; CODE=000; N=0
for _ in $(seq 1 40); do
    CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$URL/" 2>/dev/null || echo 000)
    BODY=$(curl -fsS --max-time 3 "$URL/api/lab/models" 2>/dev/null || true)
    if [ "$CODE" = "200" ] && [ -n "$BODY" ]; then
        N=$(printf '%s' "$BODY" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("models", [])))' 2>/dev/null || echo 0)
        [ "$N" = "56" ] && { OK=1; break; }
    fi
    sleep 1
done

if [ "$OK" -eq 1 ]; then
    say "VERIFIED page=200 models=$N tflite=$(find "$SHIPPING" -name '*.tflite' | wc -l)"
    say "RESULT=DEPLOYED"
    rm -rf "$STAGE"
    exit 0
fi

# 5. roll back by copying the backup over the top (again: no moves)
say "health FAILED page=$CODE models=$N - restoring copy-backup"
cp -a "$BK/app-backup/." "$APP/"
pkill -f 'python3 .*gate1_server\.py' 2>/dev/null || true
sleep 2
cd "$APP" && nohup python3 gate1_server.py >> server.log 2>&1 </dev/null &
for _ in $(seq 1 30); do
    CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$URL/" 2>/dev/null || echo 000)
    [ "$CODE" = "200" ] && break
    sleep 1
done
say "after restore: page=$CODE app=$(wc -c < "$APP/gate1_server.py") bytes"
say "RESULT=ROLLED_BACK"
tail -12 "$APP/server.log"
exit 1

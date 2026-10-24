#!/usr/bin/env bash
# Restore the Pi dashboard app after the failed deploy left the app directory empty.
# Idempotent and read-only on the backups: it copies a validated candidate back into place.
set -u

APP_PARENT="$HOME/Exercise2/vcm_live_test_local"
APP="$APP_PARENT/vcm_live_test_local"
BK1="$HOME/Exercise2/_backups/vcm-20261024T055228Z"
BK2="$HOME/Exercise2/_backups/vcm-20261024T082212Z"
LOG="$HOME/repair_report.txt"
: > "$LOG"

say() { echo "$*" | tee -a "$LOG"; }

say "=== repair start $(date -u +%H:%M:%SZ) ==="
say "app_parent_exists=$([ -d "$APP_PARENT" ] && echo yes || echo no)  app_present=$([ -f "$APP/gate1_server.py" ] && echo yes || echo no)"

# Candidate order: the copy taken immediately before the failed deploy is the working build.
CANDIDATES="$BK2/app-before $BK2/app-old $BK1/app-old $BK1/app-before"
RESTORE_FROM=""
for cand in $CANDIDATES; do
    if [ -f "$cand/gate1_server.py" ] && [ -d "$cand/gate1_web" ]; then
        size=$(wc -c < "$cand/gate1_server.py")
        say "candidate $cand  gate1_server.py=$size bytes"
        if [ -z "$RESTORE_FROM" ]; then RESTORE_FROM="$cand"; fi
        if [ "$size" -ge 100000 ]; then RESTORE_FROM="$cand"; break; fi
    else
        say "candidate $cand  incomplete (skipped)"
    fi
done

# Also look one level deeper: the rollback may have nested the app inside app-failed.
if [ -z "$RESTORE_FROM" ]; then
    deep=$(find "$BK2" -maxdepth 4 -type f -name gate1_server.py 2>/dev/null | head -1)
    if [ -n "$deep" ]; then RESTORE_FROM=$(dirname "$deep"); say "deep candidate $RESTORE_FROM"; fi
fi

if [ -z "$RESTORE_FROM" ]; then
    say "RESULT=NO_USABLE_BACKUP - not touching the current state"
    exit 2
fi
say "restoring from: $RESTORE_FROM (gate1_server.py $(wc -c < "$RESTORE_FROM/gate1_server.py") bytes)"

mkdir -p "$APP"
cp -a "$RESTORE_FROM/." "$APP/"
# The backup also nested a stray gate1_web copy under gate1_web; drop it if present.
[ -d "$APP/gate1_web/gate1_web" ] && rm -rf "$APP/gate1_web/gate1_web"
say "restored files: $(find "$APP" -type f | wc -l)  web assets: $(find "$APP/gate1_web" -type f 2>/dev/null | wc -l)"

# Gate 3-5 specialist app must sit beside the app for the optional routes.
for cand in "$BK2/Gate3to5SlotSpecialistApp-before" "$BK2/Gate3to5SlotSpecialistApp-old" "$BK1/Gate3to5SlotSpecialistApp-before"; do
    if [ -f "$cand/app.py" ] && [ ! -f "$HOME/Exercise2/Gate3to5SlotSpecialistApp/app.py" ]; then
        cp -a "$cand" "$HOME/Exercise2/Gate3to5SlotSpecialistApp"; say "restored Gate3to5SlotSpecialistApp from $cand"; break
    fi
done

# Replace the stale server that is serving 500s from the deleted path.
pkill -f 'python3 .*gate1_server\.py' 2>/dev/null || true
sleep 2
cd "$APP" || exit 1
nohup python3 gate1_server.py >> server.log 2>&1 </dev/null &
URL="http://127.0.0.1:8765"
OK=0
for _ in $(seq 1 40); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$URL/" 2>/dev/null || true)
    body=$(curl -fsS --max-time 3 "$URL/api/lab/models" 2>/dev/null || true)
    if [ "$code" = "200" ] && [ -n "$body" ]; then
        n=$(printf '%s' "$body" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("models", [])))' 2>/dev/null || echo 0)
        if [ "$n" = "56" ]; then OK=1; say "healthy: page=200 models=$n"; break; fi
    fi
    sleep 1
done

if [ "$OK" -ne 1 ]; then
    say "RESULT=UNHEALTHY page=$code models=${n:-unknown}"
    say "last log lines:"
    tail -15 "$APP/server.log" | tee -a "$LOG"
    exit 1
fi
say "RESULT=RESTORED page=200 api=56models"
say "=== repair end ==="

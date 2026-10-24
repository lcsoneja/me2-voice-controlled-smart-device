#!/usr/bin/env bash
# DEPRECATED - superseded 2026-10-24 by deploy_safe.sh.
#
# Its move-then-restore rollback was not re-entrant: when the ERR trap fired inside
# rollback, the app directory was moved twice and left EMPTY, and the dashboard served
# 500s until it was restored from a backup. deploy_safe.sh copies over the top and never
# moves or deletes the app.
set -Eeuo pipefail

HOME_DIR="$HOME"
ROOT="$HOME_DIR/Exercise2"
APP_PARENT="$ROOT/vcm_live_test_local"
APP="$APP_PARENT/vcm_live_test_local"
SHIPPING="$ROOT/Shipping"
DESKTOP="$HOME_DIR/Desktop"
ARCHIVE="$HOME_DIR/vcm_pi_latest_20261024.tar.gz"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE="$ROOT/.vcm-stage-$STAMP"
BACKUP="$ROOT/_backups/vcm-$STAMP"
NEW_ROOT="$STAGE/new_root"
NEW_APP="$NEW_ROOT/vcm_live_test_local/vcm_live_test_local"
PAYLOAD="$STAGE/payload"
ROLLBACK_REQUIRED=0

if [ ! -f "$ARCHIVE" ] || [ ! -f "$APP/gate1_server.py" ]; then
    echo "Missing release archive or current app; refusing deployment."
    exit 2
fi
mkdir -p "$STAGE" "$PAYLOAD" "$BACKUP/Shipping" "$BACKUP/Desktop" "$NEW_ROOT/vcm_live_test_local" "$NEW_ROOT/Shipping"
tar -xzf "$ARCHIVE" -C "$PAYLOAD"

# Build a complete staged app while preserving Pi-local recordings, logs, and sessions.
cp -a "$APP" "$NEW_ROOT/vcm_live_test_local/"
cp -a "$PAYLOAD/Exercise2/vcm_live_test_local/vcm_live_test_local/." "$NEW_APP/"
cp -a "$PAYLOAD/Exercise2/Gate3to5SlotSpecialistApp" "$NEW_ROOT/"
cp -a "$PAYLOAD/Exercise2/Shipping/." "$NEW_ROOT/Shipping/"
find "$NEW_APP" "$NEW_ROOT/Gate3to5SlotSpecialistApp" -type d -name __pycache__ -prune -exec rm -rf {} +

# Reject incomplete/case-mismatched archives before interrupting the running service.
python3 -m py_compile "$NEW_APP/gate1_server.py" "$NEW_APP/recording_lab.py" "$NEW_APP/nc_dsp.py" "$NEW_APP/pipeline_frames.py" "$NEW_APP/parallel_pipeline.py" "$NEW_APP/owner_voice_eval.py" "$NEW_APP/gate1_forward_reference.py" "$NEW_ROOT/Gate3to5SlotSpecialistApp/app.py"
(
    cd "$NEW_APP"
    PYTHONPATH="$NEW_ROOT:$NEW_APP" python3 - <<'PY'
import gate1_server as server
missing = []
for name, (package, model, fallback) in server.GATE2_PACKAGE_RUNNERS.items():
    if not (package / model).is_file():
        missing.append(f"{name}: {package / model}")
    if not (package / "labels.json").is_file():
        missing.append(f"{name}: labels.json")
    spec = package / "preprocessing_spec.json"
    if not spec.is_file() and (fallback is None or not (fallback / "preprocessing_spec.json").is_file()):
        missing.append(f"{name}: preprocessing_spec.json")
if missing:
    raise SystemExit("Incomplete Gate2 release: " + "; ".join(missing))
print(f"Preflight OK: {len(server.GATE2_PACKAGE_RUNNERS)} Gate2 model IDs and Linux package paths")
PY
)

# Save the exact files that this release replaces, then cut over.
cp -a "$APP" "$BACKUP/app-before"
cp -a "$ROOT/Gate3to5SlotSpecialistApp" "$BACKUP/Gate3to5SlotSpecialistApp-before"
while IFS= read -r package; do
    [ -d "$SHIPPING/$package" ] || continue
    cp -a "$SHIPPING/$package" "$BACKUP/Shipping/"
done < <(find "$NEW_ROOT/Shipping" -mindepth 1 -maxdepth 1 -type d -printf '%f\n')
for name in vcm-dashboard.desktop restart_vcm.sh handoff.md; do
    if [ -f "$DESKTOP/$name" ]; then cp -a "$DESKTOP/$name" "$BACKUP/Desktop/"; fi
done

rollback() {
    set +e
    echo "Release health check failed; restoring previous Pi dashboard."
    pkill -f '^python3 gate1_server\.py$' 2>/dev/null || true
    if [ -d "$APP" ]; then mv "$APP" "$BACKUP/app-failed"; fi
    if [ -d "$BACKUP/app-before" ]; then mv "$BACKUP/app-before" "$APP"; fi
    if [ -d "$ROOT/Gate3to5SlotSpecialistApp" ]; then mv "$ROOT/Gate3to5SlotSpecialistApp" "$BACKUP/Gate3to5SlotSpecialistApp-failed"; fi
    if [ -d "$BACKUP/Gate3to5SlotSpecialistApp-before" ]; then mv "$BACKUP/Gate3to5SlotSpecialistApp-before" "$ROOT/Gate3to5SlotSpecialistApp"; fi
    while IFS= read -r package; do
        [ -n "$package" ] || continue
        if [ -d "$BACKUP/Shipping/$package" ]; then
            rm -rf -- "${SHIPPING:?}/${package:?}"
            cp -a "$BACKUP/Shipping/$package" "$SHIPPING/$package"
        elif [ -d "$NEW_ROOT/Shipping/$package" ]; then
            rm -rf -- "${SHIPPING:?}/${package:?}"
        fi
    done < "$STAGE/package-names.txt"
    for name in vcm-dashboard.desktop restart_vcm.sh handoff.md; do
        if [ -f "$BACKUP/Desktop/$name" ]; then cp -a "$BACKUP/Desktop/$name" "$DESKTOP/$name"; else rm -f "$DESKTOP/$name"; fi
    done
    (cd "$APP" && nohup python3 gate1_server.py >> server.log 2>&1 </dev/null &)
    ROLLBACK_REQUIRED=0
}

find "$NEW_ROOT/Shipping" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' > "$STAGE/package-names.txt"
ROLLBACK_REQUIRED=1
trap 'rc=$?; if [ "$ROLLBACK_REQUIRED" -eq 1 ]; then rollback; fi; exit "$rc"' ERR

pkill -f '^python3 gate1_server\.py$' 2>/dev/null || true
sleep 1
mv "$APP" "$BACKUP/app-old"
mv "$NEW_APP" "$APP"
if [ -d "$ROOT/Gate3to5SlotSpecialistApp" ]; then mv "$ROOT/Gate3to5SlotSpecialistApp" "$BACKUP/Gate3to5SlotSpecialistApp-deployed"; fi
cp -a "$NEW_ROOT/Gate3to5SlotSpecialistApp" "$ROOT/"
while IFS= read -r package; do
    [ -n "$package" ] || continue
    target="${SHIPPING:?}/${package:?}"
    if [ -d "$target" ]; then mv "$target" "$BACKUP/Shipping/${package}-deployed"; fi
    cp -a "$NEW_ROOT/Shipping/$package" "$target"
done < "$STAGE/package-names.txt"

# Install Linux-native desktop controls; .bat files do not run on Raspberry Pi OS.
for name in vcm-dashboard.desktop restart_vcm.sh handoff.md; do
    test -f "$PAYLOAD/Desktop/$name"
    cp -a "$PAYLOAD/Desktop/$name" "$DESKTOP/$name"
done
chmod +x "$DESKTOP/restart_vcm.sh" "$DESKTOP/vcm-dashboard.desktop"

(cd "$APP" && nohup python3 gate1_server.py >> server.log 2>&1 </dev/null &)
URL="http://127.0.0.1:8765"
HEALTHY=0
for _ in $(seq 1 40); do
    page_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "$URL/" 2>/dev/null || true)"
    api_json="$(curl -fsS --max-time 3 "$URL/api/lab/models" 2>/dev/null || true)"
    if [ "$page_code" = "200" ] && [ -n "$api_json" ]; then
        model_count="$(printf '%s' "$api_json" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("models", [])))' 2>/dev/null || true)"
        if [ "$model_count" = "56" ]; then HEALTHY=1; break; fi
    fi
    sleep 1
done
if [ "$HEALTHY" -ne 1 ]; then
    tail -40 "$APP/server.log" || true
    false
fi

# The Pi's native launcher must also recognize the API as healthy.
"$DESKTOP/restart_vcm.sh"
ROLLBACK_REQUIRED=0
mv "$ARCHIVE" "$BACKUP/vcm_pi_latest_20261024.tar.gz"
cp -a "$HOME_DIR/install_latest_on_pi.sh" "$BACKUP/" 2>/dev/null || true
rm -rf "$STAGE"
echo "DEPLOY_OK"
echo "Dashboard: $URL/"
echo "Gate2 model IDs: 56"
echo "Backup: $BACKUP"

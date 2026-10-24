#!/usr/bin/env bash
# Build the pipeline payload and deploy it to the Pi with the NON-DESTRUCTIVE installer.
#
# Usage:  bash deploy_to_pi.sh lcsoneja@<PI_IP>
# Get the address on the Pi itself with:  hostname -I
#
# The payload is built fresh by build_pi_release.py (registry-driven: it resolves the active
# Gate 2 set and fails loudly if any model file, labels.json or preprocessing spec is missing).
# deploy_safe.sh then copy-backups the app, copies files over the top, restarts, and verifies
# the page + 56-model API - rolling back by copy if the verification fails.
set -Eeuo pipefail

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
    echo "Usage: bash deploy_to_pi.sh user@host" >&2
    echo "Read the address on the Pi with:  hostname -I" >&2
    exit 2
fi

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BUILDER="$HERE/build_pi_release.py"
ARCHIVE="$HERE/vcm_pi_latest_20261024.tar.gz"

command -v py >/dev/null 2>&1 || { echo "Python launcher 'py' is required on the laptop." >&2; exit 2; }
py -3.12 "$BUILDER"
test -s "$ARCHIVE"

echo "[1/3] transferring $(du -h "$ARCHIVE" | cut -f1) payload to $TARGET ..."
scp -o BatchMode=yes -o ConnectTimeout=8 "$ARCHIVE" "$TARGET:~/vcm_pi_latest_20261024.tar.gz"
scp -o BatchMode=yes -o ConnectTimeout=8 "$HERE/deploy_safe.sh" "$TARGET:~/deploy_safe.sh"
scp -o BatchMode=yes -o ConnectTimeout=8 "$HERE/pi_restart_clean.sh" "$TARGET:~/pi_restart_clean.sh"

echo "[2/3] deploying (non-destructive) ..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "$TARGET" 'bash ~/deploy_safe.sh'

echo "[3/3] collapsing any duplicate server processes ..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "$TARGET" 'bash ~/pi_restart_clean.sh'

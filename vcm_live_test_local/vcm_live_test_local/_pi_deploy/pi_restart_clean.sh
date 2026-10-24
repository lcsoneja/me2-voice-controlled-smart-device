#!/usr/bin/env bash
# Leave exactly one dashboard server running on the Pi.
#
# Two processes matched "gate1_server.py" but only one held port 8765: an orphan that
# failed to bind and never exited. PIDs are selected with awk so this script's own shell
# (whose command line also contains the name) can never match and kill itself.
set -u

APP="$HOME/Exercise2/vcm_live_test_local/vcm_live_test_local"
URL="http://127.0.0.1:8765"
cd "$APP" || { echo "FAIL cd $APP"; exit 2; }

echo "before: $(ps -eo pid,args | awk '$2=="python3" && $3 ~ /gate1_server\.py$/ {print $1" "$3}' | tr '\n' ' ')"
for pid in $(ps -eo pid,args | awk '$2=="python3" && $3 ~ /gate1_server\.py$/ {print $1}'); do
    kill "$pid" 2>/dev/null || true
done
sleep 3

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

RUNNING=$(ps -eo pid,args | awk '$2=="python3" && $3 ~ /gate1_server\.py$/ {print $1}' | wc -l)
OWNER=$(ss -ltnp 2>/dev/null | awk '/:8765/ {print $NF}' | head -1)
echo "after: processes=$RUNNING port_owner=$OWNER page=$CODE models=$N"
if [ "$OK" -eq 1 ] && [ "$RUNNING" = "1" ]; then
    echo "RESULT=SINGLE_SERVER_OK"
    exit 0
fi
echo "RESULT=NEEDS_ATTENTION"
tail -10 server.log
exit 1

#!/bin/bash
# VCM Pipeline Dashboard launcher (Raspberry Pi)
# Starts the local server if it is down, then opens the dashboard in the browser.
cd "$(dirname "$0")/../app/core"
if ! curl -s -o /dev/null --max-time 2 http://127.0.0.1:8765/pipeline_all_in_one.html; then
    nohup python3 gate1_server.py > server.log 2>&1 &
    for i in $(seq 1 30); do
        curl -s -o /dev/null --max-time 2 http://127.0.0.1:8765/pipeline_all_in_one.html && break
        sleep 1
    done
fi
xdg-open http://127.0.0.1:8765/pipeline_all_in_one.html

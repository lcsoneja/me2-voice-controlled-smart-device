import sys
import time
import urllib.request

deadline = time.time() + 180
t0 = time.time()
last_error = ""
while time.time() < deadline:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8765/oneshot.html", timeout=2
        ) as resp:
            if resp.status == 200:
                print("READY_AFTER_" + str(round(time.time() - t0, 1)) + "s")
                sys.exit(0)
    except Exception as err:  # server not up yet; keep waiting until the deadline
        last_error = str(err)
    time.sleep(2)
print("NOT_READY last_error=" + str(last_error))

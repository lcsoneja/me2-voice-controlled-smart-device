"""Emergency rescue server: receives takes from the dataset recorder page.

The pywebview app window blocks file downloads by default, so this helper
accepts takes over HTTP and writes them to disk under collected_data/rescue/.
"""
import base64
import json
import re
from pathlib import Path

from aiohttp import web

HERE = Path(__file__).resolve().parent
DEST = HERE / "collected_data" / "rescue"
MANIFEST = DEST / "manifest_rescue.csv"


@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return response


def safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value)).strip("_")[:80] or "unknown"


async def save_take(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        raw_name = str(payload["fileName"])
        stem, dot, ext = raw_name.rpartition(".")
        if dot:
            file_name = safe_token(stem) + "." + safe_token(ext)
        else:
            file_name = safe_token(raw_name) + ".wav"
        intent = safe_token(payload["intent"])
        wav_bytes = base64.b64decode(payload["wavBase64"])
        if len(wav_bytes) < 44:
            raise ValueError("take too small")
        target_dir = DEST / intent
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / file_name
        target.write_bytes(wav_bytes)
        if not MANIFEST.exists():
            MANIFEST.write_text(
                "file_name,intent,phrase,recorded_at,duration_seconds,sample_rate\r\n",
                encoding="utf-8",
            )
        with MANIFEST.open("a", encoding="utf-8") as handle:
            handle.write(
                ",".join(
                    [
                        '"' + str(target.relative_to(DEST)).replace('"', '""') + '"',
                        '"' + safe_token(str(payload.get("intent", ""))) + '"',
                        '"' + str(payload.get("phrase", "")).replace('"', '""') + '"',
                        '"' + str(payload.get("createdAt", "")) + '"',
                        '"' + str(payload.get("durationSeconds", "")) + '"',
                        '"' + str(payload.get("sampleRate", "")) + '"',
                    ]
                )
                + "\r\n",
            )
        return web.json_response({"ok": True, "file": str(target.relative_to(DEST))})
    except Exception as exc:  # noqa: BLE001 - rescue must always answer
        return web.json_response({"ok": False, "error": str(exc)}, status=400)


async def index(_request: web.Request) -> web.Response:
    return web.json_response({"rescue": "ready", "destination": str(DEST)})


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/", index)
    app.router.add_post("/save", save_take)
    print("Rescue server on http://127.0.0.1:8767/ writing to " + str(DEST))
    web.run_app(app, host="127.0.0.1", port=8767, print=None, access_log=None)


if __name__ == "__main__":
    main()

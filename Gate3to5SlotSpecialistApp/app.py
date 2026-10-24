"""Gate3–Gate5 clip inference routes for standalone tests and the unified VCM monitor."""
from __future__ import annotations

import os
from pathlib import Path
from typing import cast

from aiohttp import web
from aiohttp.multipart import BodyPartReader, MultipartReader

if __package__:
    from .inference_service import (
        ALLOWED_GATES,
        ALLOWED_RATIOS,
        MAX_UPLOAD_BYTES,
        ClipTooLongError,
        Gate3to5InferenceService,
        InputError,
    )
else:
    from inference_service import (
        ALLOWED_GATES,
        ALLOWED_RATIOS,
        MAX_UPLOAD_BYTES,
        ClipTooLongError,
        Gate3to5InferenceService,
        InputError,
    )

APP_DIR = Path(__file__).resolve().parent
REQUEST_LIMIT = MAX_UPLOAD_BYTES + 1024 * 1024
INFERENCE_KEY = web.AppKey("gate3to5_inference", Gate3to5InferenceService)
BUNDLE_DIR_KEY = web.AppKey("gate3to5_bundle_dir", Path)


def bundle_directory() -> Path:
    configured = os.environ.get("GATE3TO5_BUNDLE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (APP_DIR.parent / "Shipping" / "Gate3to5_SlotSpecialists_Candidates_20261009").resolve()


def _service_for(app: web.Application) -> Gate3to5InferenceService:
    service = app.get(INFERENCE_KEY)
    if service is None:
        service = Gate3to5InferenceService(app[BUNDLE_DIR_KEY])
        app[INFERENCE_KEY] = service
    return service


async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(APP_DIR / "index.html", headers={"Cache-Control": "no-store"})


async def config(request: web.Request) -> web.Response:
    service = _service_for(request.app)
    return web.json_response({
        "gates": [
            {"id": gate_id, "name": title, "labels": service.labels[gate_id]}
            for gate_id, title in ALLOWED_GATES.items()
        ],
        "ratios": list(ALLOWED_RATIOS),
        "max_clip_seconds": service.max_clip_seconds,
        "input_shape": [1, 148, 60, 1],
        "score_interpretation": "uncalibrated model scores",
    })


async def infer_clip(request: web.Request) -> web.Response:
    try:
        if request.content_type != "multipart/form-data":
            raise InputError("Submit a multipart form with one WAV file.")
        reader = await request.multipart()
        gate = None
        ratio = None
        filename = None
        audio_bytes = None
        while True:
            part_data = await reader.next()
            if part_data is None:
                break
            if isinstance(part_data, MultipartReader):
                raise InputError("Nested multipart uploads are not supported.")
            part = cast(BodyPartReader, part_data)
            if part.name == "gate":
                gate = (await part.text()).strip()
            elif part.name == "ratio":
                ratio = (await part.text()).strip()
            elif part.name == "audio":
                if audio_bytes is not None:
                    raise InputError("Upload exactly one WAV clip.")
                filename = part.filename or ""
                audio_bytes = await part.read(decode=False)
                if len(audio_bytes) > MAX_UPLOAD_BYTES:
                    raise InputError("WAV is too large; maximum upload size is 12 MiB.")
        if not gate or not ratio:
            raise InputError("Select both a gate and a candidate ratio before inference.")
        if filename is None or audio_bytes is None:
            raise InputError("Choose one WAV file before inference.")
        result = _service_for(request.app).infer_wav(gate, ratio, filename, audio_bytes)
        return web.json_response(result)
    except ClipTooLongError as exc:
        return web.json_response({"error": str(exc)}, status=413)
    except InputError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except (AssertionError, ValueError, OSError, RuntimeError) as exc:
        return web.json_response({"error": str(exc)}, status=422)
    except web.HTTPRequestEntityTooLarge:
        return web.json_response({"error": "WAV is too large for this local app."}, status=413)


def register_routes(
    app: web.Application,
    prefix: str = "",
    bundle_dir: Path | str | None = None,
    service: Gate3to5InferenceService | None = None,
) -> None:
    normalized_prefix = prefix.rstrip("/")
    app[BUNDLE_DIR_KEY] = Path(bundle_dir or bundle_directory()).resolve()
    if service is not None:
        app[INFERENCE_KEY] = service

    def route(path: str) -> str:
        return normalized_prefix + path if normalized_prefix else path

    app.router.add_get(route("/"), index)
    if normalized_prefix:
        async def redirect_to_slash(_request: web.Request) -> web.HTTPPermanentRedirect:
            raise web.HTTPPermanentRedirect(normalized_prefix + "/")
        app.router.add_get(normalized_prefix, redirect_to_slash)
    app.router.add_get(route("/api/config"), config)
    app.router.add_post(route("/api/infer"), infer_clip)
    app.router.add_static(route("/static/"), path=str(APP_DIR / "static"))


def create_app(
    bundle_dir: Path | str | None = None,
    inference_service: Gate3to5InferenceService | None = None,
) -> web.Application:
    app = web.Application(client_max_size=REQUEST_LIMIT)
    register_routes(app, bundle_dir=bundle_dir, service=inference_service)
    return app

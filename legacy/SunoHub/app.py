from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services.downloader import download_audio
from services.slicer import slice_audio
from services.suno import SunoApiError, create_audio, get_audio

load_dotenv()

logging.basicConfig(
    level=os.getenv("SUNOHUB_LOG_LEVEL", "INFO").upper(),
    format="[SunoHub] %(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SunoHub")

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
JOBS_DIR = BASE_DIR / "jobs"
LOOPS_DIR = BASE_DIR / "loops"
POLL_INTERVAL_SECONDS = float(os.getenv("SUNOHUB_POLL_SECONDS", "3"))

DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR.mkdir(parents=True, exist_ok=True)
LOOPS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SunoHub")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/downloads", StaticFiles(directory=DOWNLOADS_DIR), name="downloads")
app.mount("/loops", StaticFiles(directory=LOOPS_DIR), name="loops")


class GenerateRequest(BaseModel):
    description: str
    title: Optional[str] = None
    voice_id: Optional[str] = None


def local_download_url(audio_id: str) -> str:
    return f"/downloads/{audio_id}.m4a"


def loop_url(audio_id: str, name: str) -> str:
    return f"/loops/{audio_id}/{name}"


def job_path(audio_id: str) -> Path:
    return JOBS_DIR / f"{audio_id}.json"


def read_job(audio_id: str) -> Dict[str, Any]:
    path = job_path(audio_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_job(audio_id: str, **updates: Any) -> Dict[str, Any]:
    existing = read_job(audio_id)
    job = {
        **existing,
        **updates,
        "id": audio_id,
    }
    job_path(audio_id).write_text(json.dumps(job, indent=2, sort_keys=True), encoding="utf-8")
    logger.info("job saved id=%s status=%s path=%s", audio_id, job.get("status", "unknown"), job_path(audio_id))
    return job


def suno_error_message(error: SunoApiError) -> str:
    if error.status_code == 400:
        return "Bad request sent to Suno."
    if error.status_code == 401:
        return "Suno API key/authentication failed."
    if error.status_code == 403:
        return "Suno feature is not enabled for this account."
    if error.status_code == 429:
        return "Suno rate limit or quota reached."
    if error.status_code >= 500:
        return "Suno server error."
    return str(error)


async def send_error(
    websocket: Optional[WebSocket],
    message: str,
    audio_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "type": "suno:error",
        "id": audio_id,
        "message": message,
        "details": details or {},
    }
    if audio_id:
        save_job(audio_id, status="error", error=message, error_details=details or {})
    logger.error("error id=%s message=%s details=%s", audio_id or "none", message, details or {})
    if websocket:
        await websocket.send_json(payload)
    return payload


async def complete_audio(audio_id: str, result: Dict[str, Any], websocket: Optional[WebSocket]) -> Dict[str, Any]:
    audio_url = result.get("audio_url")
    if not audio_url:
        return await send_error(websocket, "Suno completed without an audio_url.", audio_id)

    download_path = DOWNLOADS_DIR / f"{audio_id}.m4a"
    logger.info("download starting id=%s url=%s path=%s", audio_id, audio_url, download_path)
    await download_audio(audio_url, download_path)
    logger.info("download complete id=%s path=%s", audio_id, download_path)
    save_job(
        audio_id,
        status="downloaded",
        local_audio_path=str(download_path),
        local_audio_url=local_download_url(audio_id),
        source_audio_url=audio_url,
    )

    complete_payload = {
        "type": "suno:complete",
        "id": audio_id,
        "status": "complete",
        "audio_url": local_download_url(audio_id),
        "source_audio_url": audio_url,
        "title": result.get("title") or "",
        "metadata": result.get("metadata") or {},
    }
    if websocket:
        await websocket.send_json(complete_payload)
    logger.info("complete emitted id=%s local_audio=%s", audio_id, complete_payload["audio_url"])
    save_job(audio_id, status="complete", complete_payload=complete_payload)

    try:
        loop_dir = LOOPS_DIR / audio_id
        logger.info("slicing starting id=%s input=%s output_dir=%s", audio_id, download_path, loop_dir)
        loops = await asyncio.to_thread(slice_audio, download_path, loop_dir)
        loop_payload = {
            "type": "suno:loops",
            "id": audio_id,
            "loops": [
                {
                    **loop,
                    "url": loop_url(audio_id, loop["name"]),
                }
                for loop in loops
            ],
        }
        if websocket:
            await websocket.send_json(loop_payload)
        logger.info("loops ready id=%s count=%d dir=%s", audio_id, len(loop_payload["loops"]), loop_dir)
        save_job(
            audio_id,
            status="loops_ready",
            loops=loop_payload["loops"],
            loop_dir=str(loop_dir),
        )
        return {
            **complete_payload,
            "loops": loop_payload["loops"],
        }
    except Exception as error:
        await send_error(
            websocket,
            f"Slicing failed: {error}",
            audio_id,
            {"audio_url": local_download_url(audio_id)},
        )
        return complete_payload


async def generate_and_process(
    request: GenerateRequest,
    websocket: Optional[WebSocket] = None,
) -> Dict[str, Any]:
    description = request.description.strip()
    if not description:
        return await send_error(websocket, "Prompt text is required.")

    logger.info(
        "generate requested title=%s voice_id=%s prompt=%s",
        (request.title or "").strip() or "none",
        (request.voice_id or "").strip() or "none",
        description,
    )

    try:
        created = await create_audio(
            description=description,
            title=(request.title or "").strip() or None,
            voice_id=(request.voice_id or "").strip() or None,
        )
    except SunoApiError as error:
        logger.exception("Suno create failed: %s", error)
        return await send_error(websocket, suno_error_message(error), details=error.details)

    audio_id = created.get("id")
    if not audio_id:
        return await send_error(websocket, "Suno response did not include an id.", details=created)

    logger.info("submitted id=%s status=%s created_at=%s", audio_id, created.get("status"), created.get("created_at"))

    submitted_payload = {
        "type": "suno:submitted",
        "id": audio_id,
        "status": created.get("status") or "submitted",
        "created_at": created.get("created_at"),
    }
    save_job(
        audio_id,
        status=submitted_payload["status"],
        description=description,
        title=(request.title or "").strip(),
        voice_id=(request.voice_id or "").strip(),
        created_response=created,
    )
    if websocket:
        await websocket.send_json(submitted_payload)

    while True:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        try:
            result = await get_audio(audio_id)
        except SunoApiError as error:
            logger.exception("Suno poll failed id=%s: %s", audio_id, error)
            return await send_error(websocket, suno_error_message(error), audio_id, error.details)

        status = result.get("status") or "queued"
        audio_url = result.get("audio_url")
        status_payload = {
            "type": "suno:status",
            "id": result.get("id") or audio_id,
            "status": status,
            "audio_url": audio_url,
            "title": result.get("title") or "",
            "error": result.get("error"),
        }
        save_job(
            audio_id,
            status=status,
            latest_status_payload=status_payload,
            latest_suno_response=result,
        )
        logger.info("poll id=%s status=%s audio_url=%s error=%s", audio_id, status, "yes" if audio_url else "no", result.get("error"))
        if websocket:
            await websocket.send_json(status_payload)

        if status == "streaming" and audio_url and websocket:
            logger.info("preview emitted id=%s url=%s", audio_id, audio_url)
            await websocket.send_json(
                {
                    "type": "suno:preview",
                    "id": audio_id,
                    "status": "streaming",
                    "audio_url": audio_url,
                }
            )

        if status == "complete":
            return await complete_audio(audio_id, result, websocket)

        if status == "error" or result.get("error"):
            return await send_error(
                websocket,
                result.get("error") or "Suno generation failed.",
                audio_id,
                result,
            )


@app.get("/health")
async def health() -> Dict[str, bool]:
    logger.info("health check")
    return {"ok": True}


@app.post("/api/suno/generate")
async def generate_rest(request: GenerateRequest) -> Dict[str, Any]:
    logger.info("REST generate called")
    return await generate_and_process(request)


@app.websocket("/ws/suno")
async def suno_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("websocket connected client=%s", websocket.client)
    try:
        while True:
            message = await websocket.receive_json()
            logger.info("websocket message type=%s keys=%s", message.get("type"), sorted(message.keys()))
            if message.get("type") != "suno:generate":
                await send_error(websocket, "Unsupported message type.", details=message)
                continue

            request = GenerateRequest(
                description=str(message.get("description") or ""),
                title=message.get("title"),
                voice_id=message.get("voice_id"),
            )
            await generate_and_process(request, websocket)
    except WebSocketDisconnect:
        logger.info("websocket disconnected client=%s", websocket.client)
        return


if __name__ == "__main__":
    import uvicorn

    logger.info(
        "starting host=%s port=%s downloads=%s loops=%s jobs=%s",
        os.getenv("SUNOHUB_HOST", "127.0.0.1"),
        os.getenv("SUNOHUB_PORT", "8000"),
        DOWNLOADS_DIR,
        LOOPS_DIR,
        JOBS_DIR,
    )
    uvicorn.run(
        "app:app",
        host=os.getenv("SUNOHUB_HOST", "127.0.0.1"),
        port=int(os.getenv("SUNOHUB_PORT", "8000")),
        reload=False,
    )

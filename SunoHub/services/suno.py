from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

SUNO_API_BASE = "https://api.suno.com/v0/audio"


class SunoApiError(Exception):
    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


def suno_api_key() -> str:
    key = os.getenv("SUNO_API_KEY", "").strip()
    if not key:
        raise SunoApiError("SUNO_API_KEY is missing.", 401)
    return key


async def parse_response(response: httpx.Response) -> Dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        body = {"message": response.text}

    if response.is_error:
        message = body.get("error") or body.get("message") or f"Suno API returned {response.status_code}"
        raise SunoApiError(message, response.status_code, body)

    return body


async def create_audio(
    description: str,
    title: Optional[str] = None,
    voice_id: Optional[str] = None,
) -> Dict[str, Any]:
    body = {
        "description": description,
        "title": title,
        "voice_id": voice_id,
    }
    body = {key: value for key, value in body.items() if value}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            SUNO_API_BASE,
            headers={
                "Authorization": f"Bearer {suno_api_key()}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    return await parse_response(response)


async def get_audio(audio_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{SUNO_API_BASE}/{audio_id}",
            headers={"Authorization": f"Bearer {suno_api_key()}"},
        )
    return await parse_response(response)

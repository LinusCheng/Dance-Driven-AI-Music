from __future__ import annotations

from pathlib import Path

import httpx


async def download_audio(audio_url: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
        response = await client.get(audio_url)
        response.raise_for_status()

    output_path.write_bytes(response.content)
    return output_path

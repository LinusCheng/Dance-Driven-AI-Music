from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydub import AudioSegment


def slice_audio(
    input_path: Path,
    output_dir: Path,
    seconds: float | None = None,
    max_loops: int | None = None,
) -> list[dict[str, Any]]:
    loop_seconds = float(seconds or os.getenv("SUNOHUB_LOOP_SECONDS", "8"))
    loop_ms = int(loop_seconds * 1000)
    max_loop_count = int(max_loops or os.getenv("SUNOHUB_MAX_LOOPS", "12"))

    if loop_ms <= 0:
        raise ValueError("Loop length must be greater than zero.")

    output_dir.mkdir(parents=True, exist_ok=True)
    for old_loop in output_dir.glob("loop_*.wav"):
        old_loop.unlink()

    audio = AudioSegment.from_file(input_path)
    loops: list[dict[str, Any]] = []

    for index, start_ms in enumerate(range(0, len(audio), loop_ms), start=1):
        if len(loops) >= max_loop_count:
            break

        end_ms = min(start_ms + loop_ms, len(audio))
        clip = audio[start_ms:end_ms]
        if len(clip) < loop_ms * 0.6:
            continue

        name = f"loop_{index:02d}.wav"
        clip.export(output_dir / name, format="wav")
        loops.append(
            {
                "name": name,
                "duration": round(len(clip) / 1000, 2),
                "start_seconds": round(start_ms / 1000, 2),
                "end_seconds": round(end_ms / 1000, 2),
            }
        )

    return loops

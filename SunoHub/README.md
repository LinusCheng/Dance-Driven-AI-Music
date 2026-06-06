# SunoHub

SunoHub is a Python-only FastAPI backend for prompt-based Suno generation. It does not consume continuous motion data. It only reacts to explicit text prompt events from the frontend.

## Setup

```bash
cd SunoHub
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

```text
SUNO_API_KEY=...
```

You also need `ffmpeg` available on your system path.

## Run

```bash
cd SunoHub
source .venv/bin/activate
python app.py
```

Default server:

```text
http://127.0.0.1:8000
```

Static output:

```text
/downloads
/loops
```

Local job metadata is written to:

```text
SunoHub/jobs/{audio_id}.json
```

Those JSON files record the prompt, Suno audio id, latest status, source URL, local downloaded audio path, and loop metadata when slicing succeeds.

## WebSocket Events

Main endpoint:

```text
ws://localhost:8000/ws/suno
```

Frontend to SunoHub:

Payload:

```json
{
  "type": "suno:generate",
  "description": "bright house groove with strings",
  "title": "optional title",
  "voice_id": "optional voice id"
}
```

SunoHub to frontend:

```text
suno:submitted
suno:status
suno:preview
suno:complete
suno:loops
suno:error
```

SunoHub polls Suno every 3 seconds. Streaming URLs are emitted only for preview playback. Audio is downloaded and sliced only after Suno returns `complete`.

## Test Endpoints

```text
GET /health
POST /api/suno/generate
```

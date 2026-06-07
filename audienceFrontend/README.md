# Audience Frontend

Small control surface for blending the active live prompt nodes sent to the Python
backend and native GenMusicEngine.

## Start

```bash
cd audienceFrontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5174
```

The app connects to the backend WebSocket at:

```text
ws://localhost:8765
```

Start the backend first:

```bash
cd backend
source .venv/bin/activate
python main.py
```

The audience page sends numeric prompt-node weights only. Prompt text is fixed
inside the Python backend.

```json
{
  "type": "setPromptWeights",
  "weights": {
    "node_1": 1,
    "node_2": 0.4
  }
}
```

This is separate from the existing `frontend` camera UI.

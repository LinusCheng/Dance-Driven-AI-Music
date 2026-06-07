# Audience Frontend

Small control surface for blending the six live prompt nodes sent to the Python
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
ws://127.0.0.1:8766
```

Start the backend first:

```bash
cd backend
source .venv/bin/activate
python main.py
```

The audience page sends structured prompt-node data:

```json
{
  "type": "setPromptNodes",
  "promptTexts": {
    "node_1": "warm piano pulse",
    "node_2": "bright disco house groove"
  },
  "weights": {
    "node_1": 1,
    "node_2": 0.4
  }
}
```

This is separate from the existing `frontend` camera UI.

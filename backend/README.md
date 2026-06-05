# Dance-Driven AI Music Backend

A small local Python bridge for receiving realtime dance features from the frontend and converting them into a music state for later Magenta RealTime 2 integration.

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

The backend starts a WebSocket server on `ws://localhost:8765`.

## What it does

- Accepts WebSocket connections from the frontend
- Validates and normalizes incoming dance state JSON
- Applies lightweight exponential smoothing to numeric features
- Converts the dance state into a clean `musicState`
- Logs the latest dance and music state to the terminal
- Includes a placeholder `MagentaController` for future Magenta integration

## Incoming JSON schema

```json
{
  "energy": 0.72,
  "openness": 0.61,
  "rotation": -0.2,
  "smile": 0.5,
  "mouthOpen": 0.1,
  "leftArmHeight": "HIGH",
  "rightArmHeight": "MID",
  "gestureLeft": "openPalm",
  "gestureRight": "fist",
  "timestamp": 1710000000000
}
```

## Notes

- The frontend sends updates every 250ms.
- Malformed messages are ignored without crashing the server.
- The WebSocket connection will accept reconnects when the frontend is restarted or the backend is not available yet.

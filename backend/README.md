# Dance-Driven AI Music Backend

A local Python control hub that receives real-time movement data from the frontend, transforms it into a higher-level dance state and music state, and distributes those signals to music generation systems such as Magenta RealTime 2, Max/MSP, TouchDesigner, or future audio engines.

The backend acts as the central intelligence layer between motion tracking and music generation.

## Architecture

```text
Frontend (MediaPipe)
        ↓
    Dance State
        ↓
   WebSocket
        ↓
     Backend
        ↓
    Music State
        ↓
 ┌───────────────┬───────────────┬───────────────┐
 │               │               │
Magenta RT2   Max/MSP     TouchDesigner
 │               │               │
Audio        MIDI/Audio      Visuals
```

## Setup

Recommended environment:

* Apple Silicon Mac
* Python 3.12+

Create a virtual environment:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

Start the backend normally:

```bash
python main.py
```

Run in forced mock mode:

```bash
python main.py --mock-magenta
```

Run a short Magenta integration test using the backend's MRT2 wrapper:

```bash
python main.py --test-magenta
```

For a direct MRT2 runtime validation script, use:

```bash
python test_mrt2.py
```

The backend starts a WebSocket server on:

```text
ws://localhost:8765
```

## Responsibilities

The backend is responsible for:

* Receiving dance state updates from the frontend
* Validating and normalizing incoming data
* Applying smoothing and temporal filtering
* Converting dance state into music state
* Serving as the integration layer for music engines
* Managing Magenta RT2 integration
* Broadcasting future OSC outputs
* Maintaining stable real-time control signals

The backend is intentionally designed to be independent of any specific music engine.

## Incoming Dance State

Example payload:

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

## Music State

Example generated music state:

```json
{
  "rawEnergy": 18.2,
  "normalizedEnergy": 0.67,
  "density": 0.67,
  "brightness": 0.61,
  "tension": 0.35,
  "rhythmicActivity": 0.67,
  "harmonyWidth": 0.61,
  "gestureEvent": "right_fist",
  "promptHints": [
    "energetic rhythm",
    "bright open harmony"
  ]
}
```

## Current Mapping

Current prototype mappings:

| Dance Feature  | Music Feature              |
| -------------- | -------------------------- |
| energy         | density, rhythmic activity |
| openness       | brightness, harmony width  |
| torso rotation | tension                    |
| smile          | brightness boost           |
| mouth open     | expression/accent signal   |
| gestures       | symbolic musical events    |

These mappings are expected to evolve throughout development and experimentation.

## Magenta RT2

Magenta integration is currently experimental.

The backend attempts to load Magenta RT2 when available and falls back to mock mode if:

* Magenta is not installed
* Models are missing
* Initialization fails

The system should remain functional even without Magenta.

## Future Outputs

Planned integrations include:

* Magenta RealTime 2
* Google Lyria RealTime
* OSC output
* Max/MSP
* TouchDesigner
* Ableton Live
* MIDI controllers
* Performance visualization systems

## Development Notes

* Frontend sends updates every 250ms
* Music engine updates are throttled to avoid instability
* Numeric features are smoothed before conversion
* The backend is designed as a reusable real-time control layer
* Movement tracking and music generation remain decoupled
* The architecture supports swapping music engines without changing the frontend

## Current Status

✅ Frontend → Backend WebSocket communication

✅ Dance State generation

✅ Music State generation

🚧 Magenta RT2 integration

🚧 OSC output

🚧 Max/MSP integration

🚧 TouchDesigner integration

🚧 Live performance tooling

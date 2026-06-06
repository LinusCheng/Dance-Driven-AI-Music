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

From the project root, enter the backend folder:

```bash
cd backend
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies once:

```bash
pip install -r requirements.txt
```

After setup, start the backend from the same `backend` folder:

```bash
python main.py
```

## Run

For normal development, use:

```bash
cd backend
source .venv/bin/activate
python main.py
```

The backend starts a WebSocket server on:

```text
ws://localhost:8765
```

Backend logs print to the terminal. They are not written to a log file unless you manually redirect output.

Default logs are intentionally concise. When the frontend is connected, the backend prints a compact feature summary about once per second:

```text
features energy=0.42 openness=0.58 rotation=-0.11 smile=0.22 mouth=0.04 arms=MID/HIGH gestures=none/fist -> music density=0.47 brightness=0.61 tension=0.10 event=right_fist
```

Use verbose mode only when you need full payloads and detailed audio-engine diagnostics:

```bash
python main.py --verbose
```

Run in forced mock mode:

```bash
python main.py --mock-magenta
```

Run a short Magenta integration test using the backend's MRT2 wrapper:

```bash
python main.py --test-magenta
```

Realtime MRT2 streaming

To enable the realtime streaming engine (streams directly to mac speakers via `sounddevice`), start:

```bash
python main.py --engine mrt2
```

If you experience audio issues on macOS, see `backend/MAGENTA_SETUP.md` for device selection and troubleshooting notes.

For a direct MRT2 runtime validation script, use:

```bash
python test_mrt2.py
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

## Gesture Sequence Controls

The backend includes an experimental three-gesture sequence detector. A gesture must be stable briefly before it is accepted, and controls have cooldowns so the style does not flicker.

You only need to remember one genre sequence and two two-hand BPM controls:

| Gesture control | Action |
| --- | --- |
| `openPalm -> peace -> fist` | Cycle to the next genre |
| one hand `openPalm` + other hand `point` | Increase BPM by 5 |
| one hand `openPalm` + other hand `fist` | Decrease BPM by 5 |

The genre cycle currently includes house, disco/funk, techno, ambient, cinematic, garage, drum and bass, trap, lofi, and afro house. The current genre and BPM add stronger style phrases to the Magenta prompt while the continuous movement controls still shape density, brightness, tension, rhythm, and harmony width.

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

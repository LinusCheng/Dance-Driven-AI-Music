# Dance-Driven AI Music

Combined frontend and GenMusicHub service for a real-time dance-driven AI music system.

Quick overview
- Frontend: browser-based MediaPipe tracking + UI that streams dance state to GenMusicHub via WebSocket.
- GenMusicHub: Python service that converts dance state → music state and drives music engines (Magenta RT2 realtime streaming included).

Quick start (dev)
1. Start GenMusicHub (from project root):
```bash
cd GenMusicHub
source .venv/bin/activate
python main.py --engine mrt2
```

2. Start frontend (from project root):
```bash
cd frontend
npm install
npm start
```

Notes
- The GenMusicHub WebSocket is ws://localhost:8765 by default.
- Use `python main.py --engine mrt2` to enable realtime MRT2 streaming (streams to mac speakers).
- If Magenta is not installed or the model is missing, GenMusicHub can run in mock/batch mode; see `GenMusicHub/README.md` for details.

Where to look next
- GenMusicHub docs and troubleshooting: GenMusicHub/README.md and GenMusicHub/MAGENTA_SETUP.md
- Frontend usage and dev: frontend/README.md

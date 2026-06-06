# Dance-Driven AI Music

Combined frontend and RealTimeHub service for a real-time dance-driven AI music system.

Quick overview
- Frontend: browser-based MediaPipe tracking + UI that streams dance state to RealTimeHub via WebSocket.
- RealTimeHub: Python service that converts dance state → music state and drives music engines (Magenta RT2 realtime streaming included).

Quick start (dev)
1. Start RealTimeHub (from project root):
```bash
cd RealTimeHub
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
- The RealTimeHub WebSocket is ws://localhost:8765 by default.
- Use `python main.py --engine mrt2` to enable realtime MRT2 streaming (streams to mac speakers).
- If Magenta is not installed or the model is missing, RealTimeHub can run in mock/batch mode; see `RealTimeHub/README.md` for details.

Where to look next
- RealTimeHub docs and troubleshooting: RealTimeHub/README.md and RealTimeHub/MAGENTA_SETUP.md
- Frontend usage and dev: frontend/README.md

# Dance-Driven AI Music

Combined frontend and backend for a real-time dance-driven AI music system.

Quick overview
- Frontend: browser-based MediaPipe tracking + UI that streams dance state to the backend via WebSocket.
- Backend: Python service that converts dance state → music state and drives music engines (Magenta RT2 realtime streaming included).

Quick start (dev)
1. Start backend (from project root):
```bash
cd backend
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
- The backend WebSocket is ws://localhost:8765 by default.
- Use `python main.py --engine mrt2` to enable realtime MRT2 streaming (streams to mac speakers).
- If Magenta is not installed or the model is missing, the backend can run in mock/batch mode; see `backend/README.md` for details.

Where to look next
- Backend docs and troubleshooting: backend/README.md and backend/MAGENTA_SETUP.md
- Frontend usage and dev: frontend/README.md

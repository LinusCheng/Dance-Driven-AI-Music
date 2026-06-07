# Backend

Python 3.12 WebSocket control hub for the C++ `GenMusicEngine` process.

This module is now a small audience-control bridge:

```text
audienceFrontend weight JSON
        ↓
backend/main.py
        ↓
mapping/ prompt weights + backend-owned prompt text
        ↓
music_engines/cpp_engine_portal.py
        ↓
GenMusicEngine C++ process
```

Old dance, gesture, smoothing, and motion-mapping modules were removed from this backend.

## Language Version

Use Python 3.12.

## Start

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Default WebSocket:

```text
ws://localhost:8765
```

## C++ Engine Portal

By default, `Backend` tries to start:

```text
GenMusicEngine/ninja-build/gen_music_engine
```

If you build from PyCharm/CLion and it creates `GenMusicEngine/cmake-build-debug/gen_music_engine`,
the portal will also find that automatically.

Override it:

```bash
python main.py --engine-executable GenMusicEngine/ninja-build/gen_music_engine
```

The portal sends newline-delimited JSON messages to the C++ process over stdin and reads JSON status messages from stdout.

Prompt text and live parameters are separate. The backend sends controls such as
`temperature`, `top_k`, `cfg_musiccoca`, `cfg_notes`, and `cfg_drums` as numeric fields,
not as prompt text.

It also sends hardcoded backend prompt-node labels plus normalized numeric
weights, matching the native Magenta RT prompt blending API used by Collider.

## Prompt Weights

Prompt-node weights are ready in:

```text
mapping/prompt_weights.py
```

Current placeholder node names:

```text
node_1, node_2, node_3
```

Future frontend or controller message:

```json
{
  "type": "setPromptWeights",
  "weights": {
    "node_1": 0.2,
    "node_2": 0.8,
    "node_3": 0.0
  }
}
```

The backend clamps each value to `0..1`, then normalizes active weights so the
active weights sum to `1.0`.

Prompt text is currently owned by the backend in `mapping/prompt_weights.py`.
The future frontend payload can add `promptTexts`, but that route is intentionally
commented/parked in `main.py` for now.

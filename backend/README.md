# Backend

Python 3.12 WebSocket control hub for the C++ `GenMusicEngine` process.

This module keeps the same broad shape as `GenMusicHub`:

```text
frontend motion JSON
        ↓
backend/main.py
        ↓
core/ validation + smoothing
        ↓
mapping/ dance-to-music + gesture controls + prompt weights
        ↓
music_engines/cpp_engine_portal.py
        ↓
GenMusicEngine C++ process
```

`GenMusicHub` is intentionally not imported or modified. This folder is a separate backend prototype.

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
ws://127.0.0.1:8766
```

Use `--port 8765` when you want this module to replace `GenMusicHub` for the existing frontend.

## C++ Engine Portal

By default, `Backend` tries to start:

```text
GenMusicEngine/build/gen_music_engine
```

If you build from PyCharm/CLion and it creates `GenMusicEngine/cmake-build-debug/gen_music_engine`,
the portal will also find that automatically.

Override it:

```bash
python main.py --engine-executable GenMusicEngine/build/gen_music_engine
```

The portal sends newline-delimited JSON messages to the C++ process over stdin and reads JSON status messages from stdout.

Prompt text and live parameters are separate. The backend sends controls such as
`temperature`, `top_k`, `cfg_musiccoca`, `cfg_notes`, and `cfg_drums` as numeric fields,
not as prompt text.

It also sends six prompt-node labels plus six weights, matching the native
Magenta RT prompt blending API used by Collider.

## Prompt Weights

Six prompt-node weights are ready in:

```text
mapping/prompt_weights.py
```

Current placeholder node names:

```text
node_1, node_2, node_3, node_4, node_5, node_6
```

Future frontend or controller message:

```json
{
  "type": "setPromptWeights",
  "weights": {
    "node_1": 0.2,
    "node_2": 0.8,
    "node_3": 0.0,
    "node_4": 0.5,
    "node_5": 1.0,
    "node_6": 0.3
  }
}
```

# GenMusicEngine

C++20/Objective-C++ process that owns the engine boundary for Magenta generation.

`GenMusicEngine` links directly against the official Magenta RT C++ inference engine:

```cpp
#include <magentart/realtime_runner.h>
```

It uses `magentart::core::RealtimeRunner` for generation and `AVAudioEngine` for live audio output.
From `backend`'s point of view, it talks to one process: `GenMusicEngine`.

## Audio Output

Live audio is handled inside `src/main.mm`:

```text
AVAudioEngine
  -> AVAudioSourceNode render callback
  -> RealtimeRunner::read_audio_stereo(...)
  -> default macOS output device
```

The file is `.mm` because Apple's realtime audio APIs are Objective-C/Objective-C++.
The Magenta generation itself still uses the C++ `magentart::core::RealtimeRunner`.

## Language Version

Use C++20/Objective-C++ with CMake 3.27+.

This expects the official Magenta RT source checkout at:

```text
../magenta-realtime
```

Override it with:

```bash
cmake -S . -B build -DMAGENTART_ROOT=/path/to/magenta-realtime
```

## Build

```bash
cd GenMusicEngine
cmake -S . -B build
cmake --build build
```

Executable:

```text
GenMusicEngine/build/gen_music_engine
```

PyCharm/CLion may build this instead:

```text
GenMusicEngine/cmake-build-debug/gen_music_engine
```

## Build Troubleshooting

Use Ninja for this target. The Xcode generator can fail inside TensorFlow Lite
because of duplicate generated protobuf files.

```bash
cmake -S . -B build -G Ninja \
  -DCMAKE_MAKE_PROGRAM=/Applications/CLion.app/Contents/bin/ninja/mac/aarch64/ninja
cmake --build build --target gen_music_engine -j4
```

If CMake prints this:

```text
cannot execute tool 'metal' due to missing Metal Toolchain
```

install the Xcode Metal component:

```bash
xcodebuild -downloadComponent MetalToolchain
xcrun -f metal
```

The many `FetchContent_Populate(...) is deprecated` warnings come from MLX /
TensorFlow Lite dependencies and are not the app failing.

## Protocol

Backend sends one JSON object per line.

Music update:

```json
{
  "type": "updateMusicState",
  "prompt": "bright house groove",
  "controls": {
    "density": 0.5,
    "brightness": 0.7,
    "tension": 0.1,
    "temperature": 1.2,
    "top_k": 120,
    "cfg_musiccoca": 2.5,
    "cfg_notes": 1.4,
    "cfg_drums": 1.2
  },
  "promptTexts": {
    "node_1": "dynamic music control",
    "node_2": "bright disco house groove",
    "node_3": "minimal ambient texture",
    "node_4": "driving techno industrial pulse",
    "node_5": "cinematic experimental motion",
    "node_6": "funky syncopated bass and drums"
  },
  "weights": {
    "node_1": 0.0,
    "node_2": 0.2,
    "node_3": 0.4,
    "node_4": 0.6,
    "node_5": 0.8,
    "node_6": 1.0
  }
}
```

The C++ engine sends those six prompt texts and normalized weights into:

```cpp
engine.set_text_prompts(texts, weights);
engine.set_blend_weights(weights.data(), weights.size());
```

Live parameters are applied directly:

```cpp
engine.set_temperature(...);
engine.set_top_k(...);
engine.set_cfg_musiccoca(...);
engine.set_cfg_notes(...);
engine.set_cfg_drums(...);
```

Status response:

```json
{
  "type": "engineStatus",
  "ok": true,
  "engine": "GenMusicEngine",
  "message": "music state accepted"
}
```

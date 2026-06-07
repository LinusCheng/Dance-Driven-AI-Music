# Magenta RealTime 2 Setup

GenMusicHub uses `magenta-rt[mlx]` to interface with Magenta RealTime 2.

## Requirements

* Python 3.12+
* Apple Silicon Mac (M1/M2) or compatible macOS environment
* Local Magenta model assets in `~/Documents/Magenta/magenta-rt-v2`
* `mrt2_small` for real-time use on Apple Silicon Air models

## Install

1. Create and activate a virtual environment:

```bash
cd GenMusicHub
python3 -m venv .venv
source .venv/bin/activate
```

2. Upgrade packaging tools:

```bash
pip install --upgrade pip setuptools wheel
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Download Magenta RT2 resources and models:

```bash
mrt models init
mrt models download mrt2_small
```

Optional, higher-quality but much heavier model:

```bash
mrt models download mrt2_base
```

## Known path conventions

The installed `magenta_rt` package resolves assets under the `MAGENTA_HOME` directory.
By default:

```bash
~/Documents/Magenta/magenta-rt-v2
```

The package exposes these helper paths:

* `magenta_rt.paths.magenta_home()`
* `magenta_rt.paths.models_dir()`
* `magenta_rt.paths.outputs_dir()`

If you want to change the root location, set the environment variable:

```bash
export MAGENTA_HOME="$HOME/Documents/Magenta"
```

## Verifying installation

Run the local MRT2 integration test:

```bash
cd GenMusicHub
source .venv/bin/activate
python main.py --test-magenta
```

A successful run should create a test audio file under `~/Documents/Magenta/magenta-rt-v2/outputs/`.

## GenMusicHub integration test

Run GenMusicHub in Magenta test mode:

```bash
python main.py --test-magenta
```

This will instantiate the available MRT2 runtime and generate a short test snippet.

## Troubleshooting

* If `magenta_rt` fails to import, make sure the virtual environment is activated and the package is installed.
* If the default model directory is not found, verify that `~/Documents/Magenta/magenta-rt-v2/models/mrt2_small` exists.
* The UI can switch between `small` (`mrt2_small`) and `base` (`mrt2_base`). `small` is the default because it is the practical real-time model for Air-class Apple Silicon machines.
* If you need to override the Magenta root, use `MAGENTA_HOME` before starting GenMusicHub.

## Notes

This repository now uses the `MagentaRT2Mlxfn` runtime automatically when available, with fallback to `MagentaRT2Mlx` or `MagentaRT2Jax`.

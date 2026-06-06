# Magenta RealTime 2 Setup

RealTimeHub uses `magenta-rt[mlx]` to interface with Magenta RealTime 2.

## Requirements

* Python 3.12+
* Apple Silicon Mac (M1/M2) or compatible macOS environment
* Local Magenta model assets in `~/Documents/Magenta/magenta-rt-v2`

## Install

1. Create and activate a virtual environment:

```bash
cd RealTimeHub
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

Run the local MRT2 test script:

```bash
cd RealTimeHub
source .venv/bin/activate
python test_mrt2.py
```

A successful run should create `~/Documents/Magenta/magenta-rt-v2/outputs/test_mrt2.wav`.

## RealTimeHub integration test

Run RealTimeHub in Magenta test mode:

```bash
python main.py --test-magenta
```

This will instantiate the available MRT2 runtime and generate a short test snippet.

## Troubleshooting

* If `magenta_rt` fails to import, make sure the virtual environment is activated and the package is installed.
* If the model directory is not found, verify that `~/Documents/Magenta/magenta-rt-v2/models/mrt2_base` exists.
* If you need to override the Magenta root, use `MAGENTA_HOME` before starting RealTimeHub.

## Notes

This repository now uses the `MagentaRT2Mlxfn` runtime automatically when available, with fallback to `MagentaRT2Mlx` or `MagentaRT2Jax`.

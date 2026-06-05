#!/usr/bin/env bash
set -euo pipefail

# backend/bootstrap.sh
# Usage:
#  ./bootstrap.sh            # setup venv and install deps
#  ./bootstrap.sh --test     # run Magenta MRT2 test after setup
#  ./bootstrap.sh --start    # start backend server after setup
#  ./bootstrap.sh --test --start

cd "$(dirname "$0")"
VENV_DIR=".venv"
PY="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

TEST=0
START=0
NOACT=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [--test] [--start] [--no-activate]

Options:
  --test        Run test_mrt2.py after installing dependencies
  --start       Start the backend server (runs in foreground)
  --no-activate Do not source the venv activate script; use venv python directly
  -h, --help    Show this help
EOF
}

# parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --test) TEST=1; shift ;;
    --start) START=1; shift ;;
    --no-activate) NOACT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 1 ;;
  esac
done

# create venv if missing
if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtualenv in $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
fi

# prefer to source activate for shell helpers, but it's okay to skip
if [[ "$NOACT" -eq 0 && -f "$VENV_DIR/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
else
  echo "Using $PY directly (no activate)."
fi

# upgrade packaging tools and install requirements
echo "Upgrading pip/setuptools/wheel..."
"${PIP}" install --upgrade pip setuptools wheel

echo "Installing requirements.txt..."
"${PIP}" install -r requirements.txt

# optional Magenta test
if [[ "$TEST" -eq 1 ]]; then
  echo "Running Magenta RT2 validation test..."
  "${PY}" test_mrt2.py
fi

# optionally start the backend server
if [[ "$START" -eq 1 ]]; then
  echo "Starting backend server (press Ctrl-C to stop)..."
  exec "${PY}" main.py
else
  cat <<EOF
Done. To activate the venv in your shell and start the backend manually:

  source ${VENV_DIR}/bin/activate
  python main.py

Or run this script to start everything in one command:

  ./bootstrap.sh --test --start

EOF
fi

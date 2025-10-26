#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# create venv if missing
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

# activate
# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# run the demo
python3 main.py

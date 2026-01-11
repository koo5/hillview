#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r ../api/app/requirements-dev.txt
pip install -q -r requirements.txt 2>/dev/null || true

if [ $# -eq 0 ]; then
    python -m pytest integration/ -v
else
    python -m pytest "$@"
fi

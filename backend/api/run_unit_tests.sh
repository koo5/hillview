#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")/app"

TEST_VENV="../../tests/venv"

if [ ! -d "$TEST_VENV" ]; then
    python3 -m venv "$TEST_VENV"
fi

source "$TEST_VENV/bin/activate"
pip install -q -r requirements-dev.txt

if [ $# -eq 0 ]; then
    python -m pytest tests/unit/ -v
else
    python -m pytest "$@"
fi

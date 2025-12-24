#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")"

TEST_VENV="../tests/venv"

if [ ! -d "$TEST_VENV" ]; then
    python3 -m venv "$TEST_VENV"
fi

source "$TEST_VENV/bin/activate"
pip install -q -r requirements.txt
pip install -q pytest

export PYTHONPATH="$(pwd):$(pwd)/.."

if [ $# -eq 0 ]; then
    python -m pytest tests/unit/ -v
else
    python -m pytest "$@"
fi

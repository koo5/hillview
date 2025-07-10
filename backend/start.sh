#!/usr/bin/env fish

. venv/bin/activate.fish
cd api;
MAPILLARY_CLIENT_TOKEN_FILE=../secrets/MAPILLARY_CLIENT_TOKEN uvicorn app.api:app --host 0.0.0.0 --port 8089 --reload

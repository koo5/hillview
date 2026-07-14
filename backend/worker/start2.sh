#!/usr/bin/env bash


PORT=${WORKER_PORT:-8056}
echo "WORKER_PORT: $WORKER_PORT, port: $PORT"
# bind_first binds :$PORT in ~0.1s and execs uvicorn on the inherited fd, so
# health checks / proxy wakes during the slow app import queue in the accept
# backlog instead of getting connection-refused (see bind_first.py).
YOLOv8_DIR=/tmp exec python3 ./bind_first.py
# previously: uvicorn app:app --host 0.0.0.0 --port $PORT --loop uvloop
# --log-level debug

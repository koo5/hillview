#!/usr/bin/env bash


PORT=${WORKER_PORT:-8056}
echo "WORKER_PORT: $WORKER_PORT, port: $PORT, inherited fd: ${WORKER_SOCKET_FD:-none}"
# The listen socket is bound as early as possible so health checks / proxy
# wakes during the slow app import queue in the accept backlog instead of
# getting connection-refused. Normally boot.py (the image entrypoint) bound it
# before even the privilege drop and passed it down as WORKER_SOCKET_FD; when
# run without boot.py, fall back to bind_first.py (binds, then execs uvicorn).
if [ -n "$WORKER_SOCKET_FD" ]; then
	YOLOv8_DIR=/tmp exec uvicorn app:app --fd "$WORKER_SOCKET_FD" --loop uvloop
else
	YOLOv8_DIR=/tmp exec python3 ./bind_first.py
fi
# previously: uvicorn app:app --host 0.0.0.0 --port $PORT --loop uvloop
# --log-level debug

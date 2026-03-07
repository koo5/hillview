#!/usr/bin/env bash


PORT=${WORKER_PORT:-8056}
echo "WORKER_PORT: $WORKER_PORT, port: $PORT"
YOLOv8_DIR=/tmp uvicorn app:app --host 0.0.0.0 --port $PORT --loop uvloop --log-level debug

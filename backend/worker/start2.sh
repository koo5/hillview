#!/usr/bin/env bash


set PORT=${WORKER_PORT:-8056}
YOLOv8_DIR=/tmp uvicorn app:app --host 0.0.0.0 --port 8056 --loop uvloop --log-level debug

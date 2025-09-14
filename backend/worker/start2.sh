#!/usr/bin/env bash

YOLOv8_DIR=/tmp uvicorn app:app --host 0.0.0.0 --port 8056 --log-level debug

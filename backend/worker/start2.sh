#!/usr/bin/env bash

uvicorn app:app --host 0.0.0.0 --port 8056 --log-level debug

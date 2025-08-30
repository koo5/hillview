#!/bin/bash

if [ "$DEV_MODE" = "1" ] || [ "$DEV_MODE" = "true" ]; then
    echo "Starting worker in development mode with auto-reload"
    uvicorn app:app --host 0.0.0.0 --port 8056 --reload
else
    echo "Starting worker in production mode"
    uvicorn app:app --host 0.0.0.0 --port 8056
fi
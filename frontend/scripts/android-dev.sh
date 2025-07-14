#!/bin/bash

# Get the local IP address
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo "Starting Tauri Android dev with host IP: $LOCAL_IP"

# Export the environment variable for Tauri
export TAURI_DEV_HOST=$LOCAL_IP

# Run the Tauri Android dev command
bun run tauri android dev "$@"
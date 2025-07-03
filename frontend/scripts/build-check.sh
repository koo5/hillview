#!/bin/bash

# Simple script that ensures build passes
# Usage: ./scripts/build-check.sh

set -e  # Exit on any error

# Source common functions
source "$(dirname "$0")/lib/common.sh"

echo "🔨 Running build check..."

# Ensure dependencies are installed
ensure_dependencies || exit 1

# Run the build
echo "🏗️  Building project..."
if run_in_project_root bun run build; then
    echo "✅ Build successful!"
    exit 0
else
    echo "❌ Build failed!"
    exit 1
fi
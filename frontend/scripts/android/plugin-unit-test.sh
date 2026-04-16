#!/bin/bash
#
# Run JVM-level (local, no emulator/device) unit tests for the
# tauri-plugin-hillview Android plugin via gradle. Used from package.json
# and scripts/validate.sh.
#
# Requires src-tauri/gen/android/ to have been generated at least once
# (happens automatically after any `tauri android *` invocation).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ANDROID_DIR="$PROJECT_ROOT/src-tauri/gen/android"

if [ ! -x "$ANDROID_DIR/gradlew" ]; then
    echo "❌ Tauri Android project not generated at: $ANDROID_DIR"
    echo "   Run 'bun run android:debug:init' (or any android:* command) first"
    echo "   to have Tauri generate the gradle project."
    exit 1
fi

cd "$ANDROID_DIR"
exec ./gradlew :tauri-plugin-hillview:testDebugUnitTest "$@"

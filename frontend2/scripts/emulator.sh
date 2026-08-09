#!/usr/bin/env bash
# Headless emulator for frontend2 testing, CPU- and RAM-capped.
#
#   ./scripts/emulator.sh start     boot it (waits for sys.boot_completed)
#   ./scripts/emulator.sh stop      shut it down
#   ./scripts/emulator.sh status    running? which AVD? current CPU%
#
# Why the caps: an unguarded headless emulator with software rendering sat at
# ~830% CPU (8 cores) on this box while merely idling at a Compose screen.
# The guest gets few cores and the scope gets a hard quota, so a forgotten
# emulator can't eat the machine. Override with EMU_CPUS / EMU_QUOTA / EMU_RAM.
set -euo pipefail

AVD="${EMU_AVD:-Medium_Phone_API_36}"
CORES="${EMU_CORES:-2}"
QUOTA="${EMU_QUOTA:-200%}"
RAM="${EMU_RAM:-8G}"
SDK="${ANDROID_HOME:-$HOME/Android/Sdk}"
ADB="$SDK/platform-tools/adb"

case "${1:-status}" in
start)
    if pgrep -f "qemu-system.*$AVD" >/dev/null 2>&1; then
        echo "already running"; exit 0
    fi
    # A crashed emulator leaves this behind and the next boot silently dies.
    rm -f "$HOME/.android/avd/${AVD}.avd"/*.lock \
          "$HOME/.android/avd"/*.avd/*.lock 2>/dev/null || true

    echo "starting $AVD (cores=$CORES quota=$QUOTA ram=$RAM)"
    systemd-run --user --scope --collect \
        -p "CPUQuota=$QUOTA" -p "MemoryMax=$RAM" \
        "$SDK/emulator/emulator" -avd "$AVD" \
        -no-window -gpu swiftshader_indirect -no-audio -no-boot-anim \
        -no-snapshot -cores "$CORES" \
        >/tmp/emulator-$AVD.log 2>&1 &

    for _ in $(seq 1 60); do
        if [ "$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then
            # SystemUI ANR dialogs otherwise steal focus from UI driving.
            "$ADB" shell settings put global hide_error_dialogs 1 >/dev/null 2>&1 || true
            echo "booted"; exit 0
        fi
        sleep 5
    done
    echo "did not boot in time; see /tmp/emulator-$AVD.log" >&2
    exit 1
    ;;
stop)
    "$ADB" emu kill 2>/dev/null || true
    sleep 3
    pkill -f "qemu-system.*$AVD" 2>/dev/null || true
    echo "stopped"
    ;;
status)
    if pgrep -f "qemu-system.*$AVD" >/dev/null 2>&1; then
        # top already suffixes RES (e.g. "2.8g") — print it as-is.
        top -bn1 | awk '/qemu-sy/ {print "running, CPU " $9 "%, RES " $6; exit}'
    else
        echo "not running"
    fi
    ;;
*)
    echo "usage: $0 {start|stop|status}" >&2; exit 2
    ;;
esac

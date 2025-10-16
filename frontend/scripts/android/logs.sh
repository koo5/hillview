#!/usr/bin/env fish

# View Android logs with filtering for Hillview app
source (dirname (status --current-filename))/../env/android-debug.env

set ADB_PATH "$ANDROID_HOME/platform-tools/adb"

if not test -f $ADB_PATH
    echo "❌ ADB not found at: $ADB_PATH"
    echo "💡 Check ANDROID_HOME in scripts/env/android-base.env"
    exit 1
end

# Define filter chain for noise reduction
function apply_log_filters
    v adbd | v ClipboardService | v ClipboardListener | v getHotwordActive::active | v pollMessages | v WifiThroughputPredictor: | v WifiScoreCard: | v WifiClientModeImpl | v Wifi | v InetDiagMessage: | v ActivityManager: | v ranchu | v EGL_emulation: |v PlayCommon: | v GLSUser | v Dialer | v cr_CronetUrlRequestContext: | v GMS_MM_Logger: | v BoundBrokerSvc: | v ProcessStats: | v TapAndPay: | v KernelCpuUidUserSysTimeReader: | v Finsky | v ConnectivityService: | v libprocessgroup: | v androidtc: | v  CompatibilityChangeReporter: | v Zygote | v Volley | v gearhead:share: | v getEnergyData | v 'RustStdoutStderr: \[INFO:CONSOLE'  | v ThreadPoolForeg: | v HostConnection: | v ProtoDataStoreFlagStore: | v AsyncOperation:  | v PhBaseOp: | v libEGL | v cn_CronetLibraryLoader: | v FusedLocation: | v LocationTracker: | v NetworkMonitor | v AlarmManager: | v 'W Settings: Setting' | v GnssUtilsJni: | v FrewleTileCacheManagerV: | v s_glBindAttribLocation: | v UriGrantsManagerService: | v ActivityScheduler: | v .gms.persisten: | v NetworkScheduler.Stats:  | v AAudio
end

# Check for --no-follow, --once, or -1 flag
set FOLLOW_MODE true
for arg in $argv
    if test "$arg" = "--no-follow" -o "$arg" = "--once" -o "$arg" = "-1"
        set FOLLOW_MODE false
        break
    end
end

if test "$FOLLOW_MODE" = "true"
    echo "📱 Starting Android logs (filtered for Hillview)..."
    echo "🔍 Press Ctrl+C to stop"
    echo ""

    # Filter for Hillview-specific logs (continuous)
    $ADB_PATH logcat | apply_log_filters
else
    echo "📱 Showing recent Android logs (filtered for Hillview)..."
    echo ""

    # Get recent logs and exit (last 500 lines, filtered)
    $ADB_PATH logcat -d | tail -500 | apply_log_filters
end

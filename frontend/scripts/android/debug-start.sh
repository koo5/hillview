#!/usr/bin/env fish

# Android Debug Environment Startup Script
# Sets up everything needed for Android Appium testing

echo "🚀 Starting Android Debug Environment..."

# Load environment configurations
source (dirname (status --current-filename))/../env/android-debug.env
source (dirname (status --current-filename))/../env/android-base.env

# Ensure correct Node.js version
source (dirname (status --current-filename))/ensure-node-version.sh

# Add Android platform-tools to PATH if not already there
if not string match -q -- '*platform-tools*' $PATH
    set -gx PATH $PATH $ANDROID_HOME/platform-tools
end

echo "📱 Checking Android emulator..."
if not adb devices | grep -q "emulator-"
    echo "❌ No Android emulator connected"
    echo "Start emulator first"
    exit 1
end
echo "✅ Emulator connected"

echo "🔍 Checking backend connectivity..."
if not curl -f http://localhost:8055/api/debug >/dev/null 2>&1
    echo "❌ Backend not reachable at localhost:8055"
    echo "Start with: cd backend && docker compose up -d api"
    exit 1
end
echo "✅ Backend is running"

echo "📦 Checking Hillview app installation..."
if not adb shell pm list packages | grep -q "cz.hillviedev"
    echo "⚠️ Hillview app not found, building and installing..."

    # Build app
    echo "🔨 Building Android app..."
    ./scripts/android/debug-build.sh

    # Install app
    echo "📲 Installing app on emulator..."
    adb install -r ./src-tauri/gen/android/app/build/outputs/apk/x86_64/debug/app-x86_64-debug.apk
    echo "✅ App installed"
else
    echo "✅ Hillview app is installed"
end

echo "🌐 Checking ChromeDriver..."
if not test -f "./chromedriver"
    echo "⚠️ ChromeDriver not found, downloading..."
    curl -L https://chromedriver.storage.googleapis.com/91.0.4472.101/chromedriver_linux64.zip -o chromedriver_91.zip
    unzip -o chromedriver_91.zip
    chmod +x chromedriver
    rm chromedriver_91.zip
    echo "✅ ChromeDriver installed"
else
    echo "✅ ChromeDriver is available"
end

echo ""
echo "🎉 Android Debug Environment Ready!"
echo ""

# Start the Hillview app
echo "🚀 Starting Hillview app..."
adb shell am start -n cz.hillviedev/.MainActivity

echo ""
echo "📱 App started successfully!"
echo ""
echo "🧪 Available test commands:"
echo "  ./scripts/android/test.sh android-photo-simple.test0.ts    # Menu click test"
echo "  ./scripts/android/test.sh android-photo-import.test.ts     # Photo import test"
echo "  ./scripts/android/test.sh --spec android-login.test.ts     # Login test"
echo ""
echo "📱 App info:"
echo "  Package: cz.hillviedev"
echo "  Backend: $VITE_BACKEND_ANDROID"
echo "  Device: "(adb devices | grep "emulator" | cut -f1)
echo ""
echo "🛠️ Debug commands:"
echo "  adb logcat | grep -i hillview                       # View app logs"
echo "  ./scripts/android/logs.sh                           # Structured logs"
echo ""
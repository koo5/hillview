#!/bin/bash

# Appium Setup Script for Hillview Android Testing

set -e

echo "🔧 Setting up Appium testing environment..."

# Check Node.js version
if ! node --version | grep -q "v2[2-9]"; then
    echo "❌ Node.js 22+ required. Current: $(node --version)"
    echo "Run: nvm use v22.18.0"
    exit 1
fi

# Check Android SDK
if [ -z "$ANDROID_HOME" ]; then
    echo "❌ ANDROID_HOME not set"
    echo "Export: export ANDROID_HOME=/home/koom/Android/Sdk"
    exit 1
fi

# Check ADB
if ! command -v adb &> /dev/null; then
    echo "❌ ADB not found in PATH"
    echo "Add to PATH: export PATH=\$PATH:\$ANDROID_HOME/platform-tools"
    exit 1
fi

# Check emulator
if ! adb devices | grep -q "emulator-"; then
    echo "❌ No Android emulator connected"
    echo "Start emulator first"
    exit 1
fi

# Install dependencies
echo "📦 Installing Node.js dependencies..."
npm install

# Download ChromeDriver for Chrome 91 if not exists
if [ ! -f "./chromedriver" ]; then
    echo "🌐 Downloading ChromeDriver 91..."
    curl -L https://chromedriver.storage.googleapis.com/91.0.4472.101/chromedriver_linux64.zip -o chromedriver_91.zip
    unzip -o chromedriver_91.zip
    chmod +x chromedriver
    rm chromedriver_91.zip
    echo "✅ ChromeDriver installed"
else
    echo "✅ ChromeDriver already exists"
fi

# Check if app is installed
if ! adb shell pm list packages | grep -q "cz.hillviedev"; then
    echo "📱 Hillview app not found, building and installing..."

    # Build app
    echo "🔨 Building Android app..."
    ./scripts/android/debug-build.sh

    # Install app
    echo "📲 Installing app on emulator..."
    adb install -r ./src-tauri/gen/android/app/build/outputs/apk/x86_64/debug/app-x86_64-debug.apk
    echo "✅ App installed"
else
    echo "✅ Hillview app already installed"
fi

# Check backend
echo "🔍 Checking backend connectivity..."
if ! curl -f http://localhost:8055/api/debug &>/dev/null; then
    echo "❌ Backend not reachable at localhost:8055"
    echo "Start with: cd backend && docker compose up -d api"
    exit 1
fi
echo "✅ Backend is running"

echo ""
echo "🎉 Appium setup complete!"
echo ""
echo "To run tests:"
echo "  source .env"
echo "  export ANDROID_HOME=/home/koom/Android/Sdk"
echo "  export PATH=\$PATH:\$ANDROID_HOME/platform-tools"
echo "  npx @wdio/cli run wdio.conf.ts --spec './tests-appium/specs/android-photo-simple.test0.ts'"
echo ""
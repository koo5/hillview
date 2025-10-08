# Appium Testing Setup

## Prerequisites

1. **Node.js 22+**
   ```bash
   nvm use v22.18.0
   ```

2. **Android SDK**
   ```bash
   export ANDROID_HOME=/home/koom/Android/Sdk
   export PATH=$PATH:$ANDROID_HOME/platform-tools
   ```

3. **Backend running**
   ```bash
   cd backend && docker compose up -d api
   ```

## Setup Commands

```bash
# Install dependencies
cd frontend
npm install

# Download ChromeDriver for Chrome 91
curl -L https://chromedriver.storage.googleapis.com/91.0.4472.101/chromedriver_linux64.zip -o chromedriver_91.zip
unzip -o chromedriver_91.zip
chmod +x chromedriver

# Verify emulator
adb devices  # Should show emulator-5554

# Build and install app
./scripts/android/debug-build.sh
adb install -r ./src-tauri/gen/android/app/build/outputs/apk/x86_64/debug/app-x86_64-debug.apk
```

## Run Tests

```bash
# Set environment
source .env
export ANDROID_HOME=/home/koom/Android/Sdk
export PATH=$PATH:$ANDROID_HOME/platform-tools

# Run working test
npx @wdio/cli run wdio.conf.ts --spec './tests-appium/specs/android-photo-simple.test0.ts'
```

## Key Files

- `wdio.conf.ts` - Test configuration
- `tests-appium/specs/android-photo-simple.test0.ts` - Working menu click test
- `tests-appium/helpers/TestWorkflows.ts` - Test utilities
- `chromedriver` - Chrome 91 compatible driver

## Test Pattern

```typescript
// Switch to WebView
await driver.switchContext('WEBVIEW_cz.hillviedev');

// Find element by data-testid
const element = await $('[data-testid="hamburger-menu"]');

// Interact
await element.click();

// Switch back
await driver.switchContext('NATIVE_APP');
```
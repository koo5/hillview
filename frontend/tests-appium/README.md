# Appium Test Setup

This directory contains the Appium test suite for the Hillview mobile app.

## Prerequisites

1. Android SDK and build tools installed
2. Android emulator or physical device connected
3. Environment variables configured (see `.env` file)

## Initial Setup

1. Generate the signing keystore (first time only):
   ```bash
   ./generate-keystore.sh
   ```

## Running Tests - Step by Step

1. **Build the Android APK**:
   ```bash
   ./build-test-apk.sh
   ```
   Or manually:
   ```bash
   bun run test:android:build
   ```
   
   **Note**: First build may take 10-20 minutes as it compiles all Rust dependencies.
   
   This creates the APK at: `src-tauri/gen/android/app/build/outputs/apk/universal/debug/app-universal-debug.apk`

2. **Start Android emulator or connect physical device**:
   - **Emulator**: Open Android Studio → AVD Manager → Start your emulator
   - **Physical device**: 
     - Enable Developer Mode (Settings → About → Tap Build Number 7 times)
     - Enable USB Debugging (Settings → Developer Options → USB Debugging)
     - Connect device via USB

3. **Verify device connection**:
   ```bash
   adb devices
   ```
   You should see your device/emulator listed

4. **Check Appium setup** (optional but recommended):
   ```bash
   bun run appium:doctor
   ```
   This verifies all dependencies are correctly installed

5. **Run the tests**:
   ```bash
   bun run test:android
   ```
   This will:
   - Start Appium server automatically
   - Install the APK on the device/emulator
   - Launch the app
   - Execute all test specs

## Troubleshooting

If tests fail to start:
- Check APK exists: `ls src-tauri/gen/android/app/build/outputs/apk/universal/release/`
- Verify device is connected: `adb devices`
- Check Android environment variables in `.env` file
- Review Appium logs in `logs/appium.log`

## Test Structure

- `specs/` - Test specifications
- `pageobjects/` - Page Object Model classes
- `helpers/` - Utility functions and helpers
- `logs/` - Appium logs (gitignored)

## Writing Tests

Tests use WebdriverIO with Mocha framework. Add `data-testid` attributes to your Svelte components for reliable element selection:

```svelte
<button data-testid="camera-button">Take Photo</button>
```
# Hillview Frontend Scripts

This directory contains build and validation scripts for the Hillview frontend project. The scripts have been refactored to eliminate code duplication by using a common library.

## Structure

```
scripts/
├── lib/
│   └── common.sh       # Shared functions and variables
├── build-apk.sh        # Build Android APKs (universal or architecture-specific)
├── build-check.sh      # Simple build validation
├── clean-android.sh    # Clean Android device/emulator storage
├── generate-keystore.sh # Generate Android keystore for APK signing
├── setup-hooks.sh      # Setup Git hooks with Husky
├── tauri-android.sh    # Wrapper for Tauri Android commands
├── validate.sh         # Full validation (build + tests)
└── validate-android.sh # Android-specific validation
```

## Common Functions (lib/common.sh)

The common library provides:
- Color codes for terminal output
- Common paths and variables
- `run_check()` - Run a command and check its status
- `ensure_dependencies()` - Check and install npm dependencies
- `check_android_device()` - Verify Android device/emulator connection
- `check_device_storage()` - Check available storage on device
- `install_apk()` - Uninstall old APK and install new one
- `clean_app_from_device()` - Remove app from device/emulator
- `run_code_quality_checks()` - Check for console.log and TODOs
- `print_final_status()` - Display final validation result
- `run_in_project_root()` - Execute commands in project root

## Script Usage

### Validation Scripts

```bash
# Full validation (TypeScript, build, tests, Android)
./scripts/validate.sh

# Quick validation (skip Android tests)
./scripts/validate.sh --skip-android

# Android-specific validation
./scripts/validate-android.sh
```

### Build Scripts

```bash
# Simple build check
./scripts/build-check.sh

# Build universal APK
./scripts/build-apk.sh

# Build architecture-specific APK
./scripts/build-apk.sh x86_64
./scripts/build-apk.sh arm64
./scripts/build-apk.sh x86

# Build APKs for all architectures
./scripts/build-apk.sh all
```

### Setup Scripts

```bash
# Setup Git hooks
./scripts/setup-hooks.sh

# Generate Android keystore
./scripts/generate-keystore.sh
```

### Cleanup Scripts

```bash
# Interactive Android cleanup
./scripts/clean-android.sh

# Deep clean (removes app, test artifacts, and caches)
./scripts/clean-android.sh --deep
```

## Android Testing Notes

The test configuration has been updated to handle app launching more robustly:
- Uses `startActivity` to launch the app directly instead of relying on home screen icons
- Includes retry logic for app launching
- Verifies WebView is present before proceeding with tests
- Supports both universal and x86_64 APKs (check wdio.conf.ts)

If tests fail to launch the app:
1. Check that the APK path in wdio.conf.ts matches your build output
2. Ensure the emulator has enough storage (use clean-android.sh)
3. Verify the app package and activity names are correct

## Makefile Integration

The scripts are integrated with the project Makefile for convenience:

```bash
make validate         # Run full validation
make validate-quick   # Skip Android tests
make validate-android # Android-specific validation
make build           # Run build check
make clean           # Clean build artifacts
make clean-android   # Clean Android device storage
make setup           # Setup project with hooks
```

## Environment Variables

Scripts automatically detect:
- Project root directory
- Node modules location
- APK output path
- Android package ID

## Error Handling

All scripts:
- Exit on first error (`set -e`)
- Provide colored output for better visibility
- Track overall status and report at the end
- Give helpful error messages and suggestions
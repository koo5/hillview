# Hillview Frontend - Project Instructions

## Android App Development

### App Package Identifiers
- **Development**: `cz.hillviedev` (used by `./scripts/android/dev.sh`)
- **Production**: `cz.hillview` (release builds)
- **Important**: Always use the correct package ID for development testing

### Android Development Commands
```bash
# Start Android development server with proper environment
./scripts/android/dev.sh

# View Android app logs (essential for debugging)
./scripts/android/logs.sh

# Build debug APK
./scripts/android/debug-build.sh
```

### Android App Architecture
- **Framework**: Tauri v2 hybrid app (Rust + WebView)
- **WebView**: Uses Android WebView to render Svelte frontend
- **Deep Links**: Configured for `cz.hillview://auth` OAuth callbacks
- **Configuration**: `src-tauri/tauri.conf.json` (prod) and `src-tauri/tauri.android-dev.conf.json` (dev)

### Network Configuration
- **Emulator Host Mapping**: `localhost` becomes `10.0.2.2` in Android emulator
- **Backend URL**: App uses `VITE_BACKEND_ANDROID` env var for emulator networking
- **Browser Testing**: Chrome in emulator can reach `http://10.0.2.2:8055/api/debug` to verify backend connectivity

### Authentication Flow
- **Browser-Based OAuth**: App redirects to system browser for OAuth (Google/GitHub)
- **Deep Link Return**: Browser redirects back via `cz.hillview://auth?token=...&expires_at=...`
- **Error States**: "error sending request" typically indicates:
  - Backend not reachable from emulator
  - Authentication required (normal state before login)
  - Network configuration issues

### App State Management
- **WebView Ready**: Look for 2 WebView elements in UI hierarchy
- **MainActivity**: App runs in `.MainActivity` activity
- **App States**: 0=not installed, 1=not running, 2=background, 3=background suspended, 4=foreground
- **Normal Behavior**: App consistently maintains state 4 when working properly

### Testing Limitations
- **Deep Links**: Don't work reliably in emulator test environment
- **OAuth Flow**: Full browser OAuth can't be automated (use simulation)
- **UI Elements**: May need WebView context switching for HTML elements

## Android Testing

Android/Appium tests live in `tests-appium/` which is its own package with its own
`package.json` and `bun.lock`. Dependencies are NOT installed by the main
`frontend/` package to keep its dependency tree small.

### Installing Android test dependencies
```bash
cd tests-appium && bun install
```

### Running tests
```bash
# Run all Android tests
bun run test:appium

# Run without clean state (faster development)
bun run test:appium:fast

# Run a single spec by name
bun run test:appium -- --spec android-photo-simple.test0.ts
```

The `test:appium*` scripts in `frontend/package.json` wrap
`./scripts/android/test.sh`, which `cd`s into `tests-appium/` and runs wdio
there.

### Test Configuration Notes
- **App restarts**: Minimized to single startup only
- **Retries**: Disabled for fast failure (`retries: 0`)
- **Error handling**: "error sending request" fails tests immediately (indicates backend connectivity issues)
- **Fail-fast**: Tests stop on first failure (`bail: 1`)

### Camera Permission Testing
Tests automatically handle:
- "Enable Camera" button clicks
- Android permission dialogs ("Allow", "While using the app")
- Camera initialization and photo capture workflow

## Development Guidelines

### Testing Best Practices
- Use `data-testid` attributes in HTML templates for reliable element selection
- Prefer the optimized test commands for faster development cycles
- Check test screenshots in `./test-results/` for debugging failures

### Backend Connectivity
- Tests expect backend service to be running
- "error sending request" indicates backend is unavailable
- Start backend service before running integration tests

## File Structure
- `tests-appium/` - Isolated package for Android/Appium tests (own package.json and lockfile)
  - `tests-appium/specs/` - Android test files
  - `tests-appium/helpers/` - Test utilities and selectors
  - `tests-appium/wdio.conf.ts` - WebDriverIO configuration
- `tests-playwright/` - Playwright web tests
- `scripts/android/test.sh` - Entry point that cds into tests-appium/ and runs wdio

## Key Optimizations Applied
- Removed cascade restart loops from network errors
- Eliminated retry mechanisms for faster feedback
- Implemented fail-fast error detection
- Centralized app lifecycle management
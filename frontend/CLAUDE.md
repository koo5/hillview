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

### Running Specific Test Files
To run a single Android test file, use:
```bash
# Method 1: Using --spec flag (discovered method)
bun run test:android --spec android-photo-simple.test0.ts

# Method 2: Using pre-configured command
bun run test:android:test0
```

### Available Android Test Commands
```bash
# Run all Android tests
bun run test:android

# Run with clean app state (full isolation)
bun run test:android:clean

# Run without data clearing (faster development)
bun run test:android:fast

# Run specific test categories
bun run test:android:auth      # Authentication tests
bun run test:android:camera    # Camera tests
bun run test:android:simple    # Simple photo workflow

# Run optimized single test (no restarts)
bun run test:android:test0     # Runs android-photo-simple.test0.ts
```

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
- `/test/specs/` - Android test files
- `/test/helpers/` - Test utilities and page objects
- `/test/pageobjects/` - Page object model implementations
- `wdio.conf.ts` - WebDriverIO configuration
- `android-photo-simple.test0.ts` - Optimized single test file

## Key Optimizations Applied
- Removed cascade restart loops from network errors
- Eliminated retry mechanisms for faster feedback
- Implemented fail-fast error detection
- Centralized app lifecycle management
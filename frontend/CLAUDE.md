# Hillview Frontend - Project Instructions

## Docs

- **[Photo sources: independent loading](../docs/sources-loading.md)**: the one contract all three marker pipelines follow — concurrent per-source loads, publish-on-arrival, deterministic cross-source cull, throttle policy — and how to test it (manual streams in the worker harness, the `hillview_stream`/`mapillary_stream` debug delay, the Panoramax route mock)
- **[SSR auth ticket](../docs/ssr-auth-ticket.md)**: how the web server renders a signed-in visitor's own view — the read-only `ssr_read` token, the `hv_ssr` cookie the browser mirrors it into, the two allowlisted backend dependencies, `viewer_id` + `createSsrBackedLoad`, the `SSR_AUTH` runtime switch
- **[Native Android Auth](../docs/native-auth.md)**: Credential Manager + Google ID-token login — concepts, security reasoning, and where everything lives
- **[Zoom view print view](../docs/zoomview-print.md)**: ⋮ → Print view + Ctrl+P — share-link QR in the middle, why the viewer freezes instead of re-rendering at print time, the replaced-element canvas gotcha
- **[Android test infra](../docs/android-test-infra.md)**: the non-obvious parts of the Appium suite — capabilities, what resets between sessions, helpers — that you would otherwise re-discover by grepping
- **[Auth state machine](../docs/auth-state-machine.md)**: who holds auth state on Android/Tauri, how the copies stay consistent, and the invariants any auth change must preserve
- **[Push notifications](../docs/push-notifications.md)**: the FCM / UnifiedPush flow end to end — what the backend sends, how Android displays it, and the knobs that control both
- **[Photo upload workflow](../docs/photo-upload-workflow.md)**: the whole upload flow across the Android client, the API and the worker — states, transitions, error handling, known edge cases (written 2026-02; check it against the code)
- **[Stream auth credential TODO](../docs/stream-auth-client-signed-credential-todo.md)**: replacing `?token=<access_token>` on stream endpoints with a client-signed credential — backend done, client wiring pending
- **[App behaviour scenarios](../docs/app-behaviour-scenarios.md)**: what the app is *supposed* to do, as the Appium and Playwright suites assert it — including rules that exist only as an assertion plus a comment about the bug it was written for
- **[Terrain mode](../docs/terrain-mode.md)**: design record for terrain in the main app — the mode, marker states, selection, enqueue and status polling
- **[Terrain overlay graduation](../docs/terrain-overlay-graduation.md)**: the per-photo horizon line + peak labels in the zoom view, and the depth buffer that answers "what am I looking at?" for any pixel
- **[Clock-calibration video TODO](../docs/clock-video-calibration-todo.md)**: the clock video recorder here and the solver in the sibling `pics` repo — validated end to end, with what is left

## Web Development

```bash
# Start the dev server (backend first — see the root CLAUDE.md)
bun run dev
```

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
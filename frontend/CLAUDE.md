# Hillview Frontend - Project Instructions

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
# Test Isolation and Clean App State

## Overview

Each test now starts with a completely clean app state to ensure proper test isolation and prevent flaky tests caused by leftover data from previous tests.

## How It Works

### 1. App Data Clearing
- **WebView cache and data**: Cleared between tests
- **Shared preferences**: Reset to defaults
- **Database files**: Cleared
- **Cached files**: Removed
- **App-specific directories**: Cleaned

### 2. App Restart Process
1. **Terminate** running app instance
2. **Clear app data** using multiple methods:
   - `mobile: clearApp` (Appium built-in)
   - `pm clear` (ADB command)
   - Manual directory cleanup (fallback)
3. **Start fresh** app instance
4. **Verify health** before test proceeds

## Usage

### Running Tests with Clean State (Default)
```bash
# Clean mode (default) - full test isolation
bun run test:android:simple:clean

# Or explicitly set the environment variable
WDIO_CLEAN_STATE=true bun run test:android:simple
```

### Running Tests in Fast Mode (Development)
```bash
# Fast mode - skips data clearing for faster development
bun run test:android:simple:fast

# Or set environment variable
WDIO_CLEAN_STATE=false bun run test:android:simple
```

## Available Scripts

| Script | Description |
|--------|-------------|
| `test:android:simple:clean` | Run Simple Android Photo Upload with clean state |
| `test:android:simple:fast` | Run Simple Android Photo Upload in fast mode |
| `test:android:clean` | Run all Android tests with clean state |
| `test:android:fast` | Run all Android tests in fast mode |

## Configuration

The behavior is controlled by the `WDIO_CLEAN_STATE` environment variable:

- `true` (default): Full test isolation with data clearing
- `false`: Fast mode that only restarts if app appears broken

## Test Structure

### Before Each Test
```typescript
// In wdio.conf.ts beforeTest hook:
if (TEST_CONFIG.CLEAN_APP_STATE) {
    // Clean mode: terminate → clear data → restart
    await prepareAppForTest(true);
} else {
    // Fast mode: health check → restart only if needed
    await prepareAppForTestFast();
}
```

### Individual Test Files
```typescript
beforeEach(async function () {
    // Clean app state is automatically provided by framework
    console.log('🢄🧪 Starting test with clean app state');
    
    // Optional: Additional test-specific setup
});
```

## Benefits

### Clean Mode Benefits
- ✅ **True test isolation** - no data contamination between tests
- ✅ **Consistent results** - each test starts from known state
- ✅ **Better debugging** - easier to reproduce issues
- ✅ **Reduced flakiness** - eliminates state-dependent failures

### Fast Mode Benefits
- ⚡ **Faster execution** - skips data clearing
- ⚡ **Better for development** - quick iteration cycle
- ⚡ **Still reliable** - restarts if app appears broken

## When to Use Each Mode

### Use Clean Mode When:
- Running CI/CD tests
- Investigating flaky tests
- Need guaranteed clean state
- Testing authentication flows
- Testing first-time user experience

### Use Fast Mode When:
- Developing new tests
- Quick debugging
- Iterating on test logic
- Performance is critical

## Troubleshooting

### If Data Clearing Fails
The system tries multiple approaches:
1. Appium's `mobile: clearApp`
2. ADB `pm clear` command
3. Manual directory cleanup
4. Fallback to simple restart

### App Won't Start After Clearing
- Check app installation
- Verify emulator health
- Check appium logs in `./logs/appium.log`
- Look for debug screenshots in `./test-results/`

## Implementation Details

### Key Functions
- `clearAppData()`: Handles app data clearing with multiple fallback methods
- `prepareAppForTest(clearData: boolean)`: Main clean restart function
- `prepareAppForTestFast()`: Quick health-check based preparation
- `ensureAppIsRunning(forceRestart: boolean)`: Core app launch logic

### Error Handling
- Multiple fallback methods for data clearing
- Comprehensive logging for debugging
- Screenshot capture on failures
- Graceful degradation if cleaning fails
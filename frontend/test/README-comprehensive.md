# Comprehensive Photo Capture and Upload Test

This comprehensive Appium test verifies the complete photo capture and upload workflow in the Hillview app.

## What the Test Does

The test performs the following comprehensive workflow:

1. **Backend Setup**
   - Calls the API debug function to reset test users (`POST /api/debug/recreate-test-users`)
   - Logs in with test user credentials (`test/test123`)

2. **App Navigation**
   - Ensures the app is running and in the foreground
   - Navigates to the photos settings page (not sources settings)
   - Enables automatic upload functionality (simplified toggle without folder path)

3. **Camera Permissions**
   - Navigates to camera capture mode
   - Handles camera permission requests (grants permissions)
   - Handles location permission requests (grants permissions)

4. **Photo Capture**
   - Takes a photo using the camera interface
   - Generates unique photo identifiers for tracking
   - Captures photo metadata including timestamp

5. **Gallery Navigation and Source Toggling**
   - Navigates to gallery mode
   - Ensures HillViewSource is enabled
   - Toggles HillViewSource on/off at 20-second intervals
   - Continues toggling until the captured photo appears in the gallery

6. **Photo Detection**
   - Searches for the captured photo using multiple detection methods:
     - Original filename data attributes
     - Timestamp-based matching
     - Content description attributes
     - DOM element inspection

7. **Upload Verification**
   - Verifies photo metadata and location data
   - Uses API authentication to check upload status
   - Confirms photo appears in user's account via API

## Test User Credentials

The test uses hardcoded test user credentials defined in the backend:
- **Username**: `test`
- **Password**: `test123`

These credentials are automatically reset before each test run via the API endpoint.

## Running the Test

### Prerequisites

1. **Backend API running** on `http://localhost:8055`
2. **Android emulator or device** connected
3. **Appium server** running on port 4723
4. **App APK** built and available at the configured path

### Run Commands

```bash
# Run only the comprehensive test
npm run test:android:comprehensive

# Run all Android tests (includes comprehensive test)
npm run test:android

# Run permissions tests
npm run test:android:permissions
```

### Before Running Tests

1. **Build the Android APK**:
   ```bash
   npm run test:android:build
   ```

2. **Start the backend API**:
   ```bash
   cd ../backend
   uvicorn app.api:app --reload --port 8055
   ```

3. **Start Appium server**:
   ```bash
   npm run appium
   ```

## Test Configuration

The test is configured in `wdio.conf.ts` with:
- **Platform**: Android
- **Automation**: UiAutomator2
- **Permissions**: Manual permission handling (no auto-grant)
- **Reset**: No reset between tests to maintain state
- **Timeout**: 60 seconds for various operations

## Key Features

### Robust Element Detection
- Multiple selector strategies for finding UI elements
- Retry mechanisms for unreliable elements
- Fallback selectors for different Android versions

### Permission Handling
- Uses the existing `PermissionHelper` class
- Handles multiple permission dialogs sequentially
- Supports both camera and location permissions

### API Integration
- Resets test users before each run
- Authenticates with the backend API
- Verifies photo upload status via API calls

### Photo Tracking
- Generates unique identifiers for captured photos
- Uses timestamp-based tracking
- Searches for photos using data attributes
- Supports original filename detection

### Gallery Source Toggling
- Implements the requested 20-second interval toggling
- Continues until photo is detected
- Maximum of 10 toggle attempts to prevent infinite loops

## Debugging

### Common Issues

1. **Permission dialogs not appearing**
   - Ensure `appium:autoGrantPermissions: false` in config
   - Check Android version compatibility

2. **Photo not detected in gallery**
   - Verify data-testid attributes are set in the app
   - Check if HillViewSource requires manual enabling
   - Increase toggle interval if network is slow

3. **API calls failing**
   - Verify backend is running on correct port
   - Check if test user creation is enabled
   - Ensure CORS is configured properly

### Debug Mode

Add additional logging by modifying the test:

```typescript
// Enable more verbose logging
console.log('Debug info:', await browser.getPageSource());

// Take screenshots at key points
await browser.saveScreenshot('./debug-screenshot.png');
```

## Expected Results

The test should:
- ✅ Successfully reset test users
- ✅ Navigate through all app screens
- ✅ Handle all permission requests
- ✅ Capture a photo with location data
- ✅ Find the photo in gallery after source toggling
- ✅ Verify photo upload via API

Total test duration: ~5-10 minutes (depending on toggle intervals)

## Troubleshooting

If the test fails:

1. **Check Appium logs**: `./logs/appium.log`
2. **Verify app state**: Ensure app is installed and permissions are reset
3. **Backend connectivity**: Test API endpoints manually
4. **Android version**: Ensure selectors match your Android version
5. **Timing issues**: Increase pause durations if needed

For more detailed debugging, run with WebDriver.io debug mode:
```bash
npx wdio run wdio.conf.ts --spec ./test/specs/comprehensive-photo-capture.test.ts --debug
```
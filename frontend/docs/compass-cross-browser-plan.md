# Cross-Browser Compass Implementation Plan

## Current Issues
- `deviceorientationabsolute` only fires once on some browsers
- No permission request handling for iOS 13+
- Mixed support for absolute vs magnetic north across browsers

## Goal
Reliable compass functionality across all modern browsers with proper fallbacks and permission handling.

## Implementation Plan

### 1. Permission Handling (Priority: HIGH)
**Issue**: iOS 13+ and some Android browsers require explicit permission for motion/orientation events.

```typescript
async function requestCompassPermission(): Promise<boolean> {
    // iOS 13+ requires explicit permission request
    if (typeof DeviceOrientationEvent.requestPermission === 'function') {
        try {
            const permissionState = await DeviceOrientationEvent.requestPermission();
            return permissionState === 'granted';
        } catch (error) {
            console.error('🧭 Permission request failed:', error);
            return false;
        }
    }
    // Other browsers don't need permission
    return true;
}
```

**Requirements**:
- Must be triggered from user gesture (button click)
- Add UI button for "Enable Compass" on iOS
- Store permission state in localStorage to avoid repeated requests

### 2. Event Listener Strategy (Priority: HIGH)
**Current**: We try `deviceorientationabsolute` first, fall back to `deviceorientation`
**Problem**: `deviceorientationabsolute` may only fire once

**Proposed Solution**:
```typescript
// Strategy 1: Primary listener for regular deviceorientation
window.addEventListener('deviceorientation', handleOrientation);

// Strategy 2: Check if absolute is available and continuously firing
let absoluteEventCount = 0;
let absoluteCheckTimeout: number;

window.addEventListener('deviceorientationabsolute', (event) => {
    absoluteEventCount++;
    clearTimeout(absoluteCheckTimeout);

    // If we get multiple absolute events, prefer them
    if (absoluteEventCount > 2) {
        // Remove regular listener, use absolute only
        window.removeEventListener('deviceorientation', regularOrientationListener);
        useAbsoluteOrientation = true;
    }

    handleOrientation(event, true);

    // Check if absolute events stop coming
    absoluteCheckTimeout = setTimeout(() => {
        if (absoluteEventCount < 3) {
            // Absolute isn't reliable, keep using regular
            useAbsoluteOrientation = false;
        }
    }, 1000);
});
```

### 3. Compass Heading Calculation (Priority: MEDIUM)
**Current**: Using tilt-compensated heading calculation
**Enhancement**: Add fallback for extreme tilt angles

```typescript
function computeHeading(event: DeviceOrientationEvent): number | null {
    // 1. Prefer webkitCompassHeading (iOS)
    if (event.webkitCompassHeading !== undefined && event.webkitCompassHeading !== null) {
        return event.webkitCompassHeading;
    }

    // 2. Use alpha with tilt compensation
    if (event.alpha !== null && event.beta !== null && event.gamma !== null) {
        // Check if device is too tilted (beta > 45° or < -45°)
        if (Math.abs(event.beta) > 45) {
            // Use simple alpha when heavily tilted
            return (360 - event.alpha) % 360;
        }
        // Use full tilt compensation
        return computeTiltCompensatedHeading(event.alpha, event.beta, event.gamma);
    }

    return null;
}
```

### 4. Browser-Specific Handling (Priority: MEDIUM)

#### iOS Safari
- Requires permission via DeviceOrientationEvent.requestPermission()
- Provides webkitCompassHeading (true north)
- Generally reliable once permission granted

#### Chrome Android
- No permission required (usually)
- deviceorientationabsolute may be unreliable
- Prefer regular deviceorientation with event.absolute check

#### Firefox
- Limited support for deviceorientationabsolute
- Use regular deviceorientation
- May need compass calibration

### 5. Fallback Chain (Priority: HIGH)
```
1. Try deviceorientationabsolute (with timeout check)
   ↓ (if not continuously firing)
2. Use deviceorientation with event.absolute flag
   ↓ (if no events)
3. Show "Compass not available" with instructions
```

### 6. User Experience Improvements (Priority: MEDIUM)

#### Calibration Hint
Show calibration hint when:
- Accuracy is low (webkitCompassAccuracy > 25)
- Heading jumps erratically
- No updates for > 5 seconds

#### Permission UI
```svelte
{#if needsCompassPermission}
    <button on:click={requestCompassPermission}>
        Enable Compass
    </button>
{/if}
```

### 7. Testing Strategy (Priority: LOW)

#### Real Device Testing Matrix
- [ ] iPhone 12+ with iOS 15+ (Safari)
- [ ] iPhone with iOS 13-14 (Safari)
- [ ] Android 10+ (Chrome)
- [ ] Android 10+ (Firefox)
- [ ] iPad (Safari)

#### DevTools Testing
- Chrome DevTools → Sensors panel for orientation simulation
- Test permission denied scenario
- Test background tab behavior

### 8. Future: Generic Sensor API (Priority: LOW)
Monitor adoption of AbsoluteOrientationSensor API:
```typescript
if ('AbsoluteOrientationSensor' in window) {
    const sensor = new AbsoluteOrientationSensor({ frequency: 60 });
    sensor.addEventListener('reading', () => {
        // Convert quaternion to Euler angles
        const heading = quaternionToEuler(sensor.quaternion);
    });
    sensor.start();
}
```

Currently limited browser support (Chrome only, behind flag).

## Implementation Priority

### Phase 1 (Immediate)
1. Add iOS permission request handling
2. Fix the absolute-once issue (✅ DONE - removed early return)
3. Add permission request UI

### Phase 2 (Next Sprint)
1. Implement smart absolute vs regular detection
2. Add calibration hints
3. Improve tilt compensation edge cases

### Phase 3 (Future)
1. Generic Sensor API support
2. Advanced filtering/smoothing
3. Offline compass calibration storage

## Success Metrics
- Compass works on 95% of modern mobile browsers
- Permission flow completion rate > 80%
- Heading accuracy within 5° of native apps
- No "stuck" compass after device rotation

## Notes
- Always test on real devices - emulators are unreliable for compass
- HTTPS required (localhost OK for dev)
- Background tabs may throttle events
- Some Android devices need physical rotation to start compass
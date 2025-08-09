# Enhanced Sensor Modes for Accurate Compass

The enhanced sensor service provides multiple modes to get accurate compass bearings, especially when the phone is held upright.

## Available Sensor Modes

1. **GAME_ROTATION_VECTOR** (Default - Best for upright phone)
   - Uses gyroscope and accelerometer only (no magnetometer)
   - More accurate when phone is upright
   - Not affected by magnetic interference
   - Best for AR/gaming applications

2. **MADGWICK_AHRS** (Advanced sensor fusion)
   - Implements Madgwick's gradient descent algorithm
   - Fuses accelerometer, gyroscope, and magnetometer data
   - Excellent accuracy in all orientations
   - Handles sensor drift well

3. **ROTATION_VECTOR** (Standard Android sensor)
   - Uses Android's built-in sensor fusion
   - Good general-purpose accuracy
   - May be less accurate when phone is upright

4. **COMPLEMENTARY_FILTER** (Simple fusion)
   - Combines magnetometer and gyroscope data
   - 98% gyroscope + 2% magnetometer
   - Good for reducing magnetic noise

## Usage Examples

### Starting with a specific mode

```typescript
import { startCompass, SensorMode } from '$lib/compass.svelte';

// Start with Game Rotation Vector (best for upright phone)
await startCompass(SensorMode.GAME_ROTATION_VECTOR);

// Or use Madgwick AHRS for advanced fusion
await startCompass(SensorMode.MADGWICK_AHRS);
```

### Switching modes on the fly

```typescript
import { switchSensorMode, SensorMode } from '$lib/compass.svelte';

// Switch to a different mode while running
await switchSensorMode(SensorMode.MADGWICK_AHRS);
```

### Checking current mode

```typescript
import { currentSensorMode } from '$lib/compass.svelte';
import { get } from 'svelte/store';

const mode = get(currentSensorMode);
console.log('Current sensor mode:', SensorMode[mode]);
```

## Recommendations

- **For upright phone use**: Use `GAME_ROTATION_VECTOR` or `MADGWICK_AHRS`
- **For general use**: Use `ROTATION_VECTOR` or `MADGWICK_AHRS`
- **In magnetically noisy environments**: Use `GAME_ROTATION_VECTOR`
- **For highest accuracy**: Use `MADGWICK_AHRS` with good magnetometer calibration

## Implementation Details

The enhanced sensor service (`EnhancedSensorService.kt`) automatically:
- Detects available sensors on the device
- Falls back gracefully if requested sensors aren't available
- Provides accuracy estimates based on device orientation
- Handles magnetic declination for true north calculation
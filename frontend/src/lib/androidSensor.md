# Android Native Sensor Implementation

## Overview

This implementation provides a native Android sensor interface that uses the Android Rotation Vector sensor (TYPE_ROTATION_VECTOR) to provide accurate compass bearing regardless of phone orientation.

## Key Features

1. **Rotation Vector Sensor**: Uses Android's fused sensor that combines accelerometer, gyroscope, and magnetometer data
2. **Works in any orientation**: Unlike the web DeviceOrientation API, this provides accurate bearing when the phone is held vertically or at any angle
3. **True North Support**: Automatically calculates magnetic declination based on GPS location to provide true north bearing
4. **Fallback Support**: Falls back to magnetometer + accelerometer if rotation vector sensor is unavailable

## Architecture

### Android Side (Kotlin)
- `SensorService.kt`: Native Android service that interfaces with the sensor hardware
- Exposed to JavaScript via `window.AndroidSensor` interface
- Handles sensor fusion and magnetic declination calculation

### JavaScript Side (TypeScript)
- `androidSensor.ts`: TypeScript wrapper for the native interface
- `compass.svelte.ts`: Updated to use Android sensor when available
- Automatically falls back to DeviceOrientation API on non-Android devices

## Usage

The system automatically detects and uses the Android sensor when available. No code changes required in the application - it works transparently through the existing compass store.

## Benefits

1. **Accuracy**: More accurate bearing when phone is not flat
2. **Stability**: Less jittery than raw magnetometer readings
3. **True North**: Automatic true north calculation using GPS location
4. **Performance**: Native implementation is more efficient than JavaScript sensor fusion
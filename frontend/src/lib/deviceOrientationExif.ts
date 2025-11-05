

// device orientation represented as exif Orientation value 1 | 3 | 6 | 8
import {writable, type Writable} from "svelte/store";

// Valid EXIF orientation values
export type ExifOrientation = 1 | 3 | 6 | 8;

export let deviceOrientationExif: Writable<ExifOrientation> = writable(1); // Default to 1 (normal orientation)

/**
 * Validate EXIF orientation value
 * Ensures only valid EXIF orientation values (1, 3, 6, 8) are used
 */
export function validateExifOrientation(value: number): ExifOrientation {
	switch (value) {
		case 1:
		case 3:
		case 6:
		case 8:
			return value as ExifOrientation;
		default:
			console.warn(`Invalid EXIF orientation: ${value}, defaulting to 1`);
			return 1;
	}
}

/**
 * Convert EXIF orientation code to CSS rotation degrees
 * @param orientationCode EXIF orientation value (1, 3, 6, 8)
 * @returns CSS rotation degrees
 */
export function getRotationFromOrientation(orientationCode: number): number {
	switch (orientationCode) {
		case 1: return 0;   // Normal portrait
		case 3: return 180; // Upside-down portrait
		case 6: return 90;  // Landscape right (90° clockwise)
		case 8: return -90; // Landscape left (90° counter-clockwise)
		default: return 0;  // Default to normal
	}
}

/**
 * Get current webview orientation in degrees
 * @returns 0 (portrait), 90 (landscape-primary), 180 (portrait-secondary), 270 (landscape-secondary)
 */
function getWebviewOrientation(): number {
	// Modern browsers
	if (screen.orientation) {
		return screen.orientation.angle;
	}

	// Fallback using CSS media queries
	if (window.matchMedia('(orientation: landscape)').matches) {
		// In landscape mode, but we need to determine which landscape
		// This is a simplified fallback - might need device-specific logic
		return window.innerWidth > window.innerHeight ? 90 : 270;
	}

	return 0; // Default to portrait
}

/**
 * Calculate EXIF orientation relative to webview orientation
 * This ensures photos appear correctly oriented within the current webview orientation
 */
export function calculateWebviewRelativeOrientation(alpha: number | null, beta: number | null, gamma: number | null): ExifOrientation {
	// Get device orientation relative to its natural position
	const deviceOrientation = getDeviceOrientationFromAngles(alpha, beta, gamma);

	// Get webview orientation
	const webviewOrientation = getWebviewOrientation();

	// Calculate relative rotation: how much is the device rotated relative to the webview?
	const relativeRotation = (deviceOrientation - webviewOrientation + 360) % 360;

	// Map relative rotation to EXIF orientation values
	switch (relativeRotation) {
		case 0: return 1;   // Normal (device and webview aligned)
		case 90: return 6;  // Device rotated 90° clockwise relative to webview
		case 180: return 3; // Device rotated 180° relative to webview
		case 270: return 8; // Device rotated 90° counter-clockwise relative to webview
		default: return validateExifOrientation(1);  // Default to normal for intermediate angles
	}
}

/**
 * Get device orientation in degrees from device motion angles
 * @param alpha Rotation around z-axis (compass direction)
 * @param beta Rotation around x-axis (front-to-back tilt)
 * @param gamma Rotation around y-axis (left-to-right tilt)
 * @returns Device orientation in degrees (0, 90, 180, 270)
 */
function getDeviceOrientationFromAngles(alpha: number | null, beta: number | null, gamma: number | null): number {
	if (beta === null || gamma === null) {
		return 0; // Default to portrait if we can't determine orientation
	}

	// Determine device orientation based on tilt angles
	// This logic matches the original exifOrientationFromAngles but returns degrees instead of EXIF codes
	if (Math.abs(gamma) > Math.abs(beta)) {
		// Landscape orientation
		if (gamma > 45) {
			return 270; // Landscape left (device rotated 90° counter-clockwise)
		} else if (gamma < -45) {
			return 90;  // Landscape right (device rotated 90° clockwise)
		}
	} else {
		// Portrait orientation
		if (Math.abs(beta) > 45 && beta < 0) {
			return 180; // Upside-down portrait
		}
	}

	return 0; // Normal portrait
}

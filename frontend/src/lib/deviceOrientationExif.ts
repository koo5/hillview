 // device orientation represented as exif Orientation value 1 | 3 | 6 | 8
import {writable, type Writable} from "svelte/store";
// Valid EXIF orientation values
// http://sylvana.net/jpegcrop/exif_orientation.html
 export type ExifOrientation = 1 | 3 | 6 | 8;

export let deviceOrientationExif: Writable<ExifOrientation> = writable(1); // Default to 1 (normal orientation)

 /**
 * Convert EXIF orientation code to CSS rotation degrees
 * @param orientationCode EXIF orientation value (1, 3, 6, 8)
 * @returns CSS rotation degrees
 */
export function getRotationFromOrientation(orientationCode: number): number {
	switch (orientationCode) {
		case 1: return 0;   // Normal portrait
		case 3: return 180; // Upside-down portrait
		case 6: return -90;  // Landscape right (90° clockwise)
		case 8: return 90; // Landscape left (90° counter-clockwise)
		default: return 0;  // Default to normal
	}
}

/**
 * Calculate EXIF orientation relative to webview orientation
 * This ensures photos appear correctly oriented within the current webview orientation
 */
/*export function calculateWebviewRelativeOrientation(alpha: number | null, beta: number | null, gamma: number | null): ExifOrientation {
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
*/

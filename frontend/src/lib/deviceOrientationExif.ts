

// device orientation represented as exif Orientation value 1 | 3 | 6 | 8
import {writable, type Writable} from "svelte/store";
import Quaternion from "quaternion";

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
 * Extract device screen orientation from quaternion using rotation matrix
 * This calculates the rotation in the device's screen plane
 * @param quaternion Quaternion representing device orientation
 * @returns Device orientation in degrees (0, 90, 180, 270)
 */
function quaternionToDeviceOrientation(quaternion: Quaternion): number {
	// Convert quaternion to rotation matrix (3x3 flattened to array in row-major order)
	const matrix = quaternion.toMatrix();
	// Matrix layout: [r11, r12, r13, r21, r22, r23, r31, r32, r33]
	//                [ 0,   1,   2,   3,   4,   5,   6,   7,   8 ]

	// Calculate rotation angle in the screen plane (XY plane)
	// matrix[0] = r11, matrix[3] = r21
	const rotationAngle = Math.atan2(matrix[3], matrix[0]) * (180 / Math.PI);

	// Normalize to 0-360 range
	const normalizedAngle = ((rotationAngle % 360) + 360) % 360;

	// Map to discrete device orientations with 45-degree tolerance zones
	if (normalizedAngle < 45 || normalizedAngle >= 315) {
		return 0;   // Portrait (0°)
	} else if (normalizedAngle >= 45 && normalizedAngle < 135) {
		return 90;  // Landscape right (90°)
	} else if (normalizedAngle >= 135 && normalizedAngle < 225) {
		return 180; // Upside-down portrait (180°)
	} else {
		return 270; // Landscape left (270°)
	}
}

/**
 * 90° rotation around X axis = correction for upright phone
 * This accounts for the fact that device coordinates assume the phone is lying flat,
 * but we hold it upright
 */
const uprightCorrection = new Quaternion({
	w: Math.cos(Math.PI / 4),
	x: Math.sin(Math.PI / 4),
	y: 0,
	z: 0
});

/**
 * Rotate gravity vector (0, -1, 0) by quaternion to find orientation
 * @param q Quaternion representing device orientation
 * @returns Gravity vector components in device coordinate system
 */
function gravityVector(q: Quaternion): { x: number; y: number; z: number } {
	const g = q.rotateVector([0, -1, 0]);
	return { x: g[0], y: g[1], z: g[2] };
}

/**
 * Map quaternion to EXIF orientation (1,3,6,8) using gravity vector
 * @param q Quaternion representing device orientation
 * @returns EXIF orientation code
 */
function quaternionToEXIF(q: Quaternion): ExifOrientation {
	const g = gravityVector(q);

	// Portrait orientations: gravity primarily affects Y-axis
	if (Math.abs(g.y) > Math.abs(g.x)) {
		return g.y > 0 ? 1 : 3;   // upright or upside-down
	}

	// Landscape orientations: gravity primarily affects X-axis
	return g.x > 0 ? 6 : 8;     // rotate clockwise or counter-clockwise
}

/**
 * Convert quaternion to Euler angles (yaw, pitch, roll)
 * @param q Array of 4 numbers [x, y, z, w] from AbsoluteOrientationSensor
 * @returns Euler angles in radians
 */
function quaternionToEuler(q: number[]) {
    const [x, y, z, w] = q; // AbsoluteOrientationSensor format: [x, y, z, w]

    // yaw (z-axis rotation)
    const ys = 2 * (w*z + x*y);
    const yc = 1 - 2 * (y*y + z*z);
    const yaw = Math.atan2(ys, yc);

    // pitch (x-axis rotation)
    const ps = 2 * (w*x - y*z);
    let pitch;
    if (Math.abs(ps) >= 1) {
        pitch = Math.sign(ps) * Math.PI / 2;
    } else {
        pitch = Math.asin(ps);
    }

    // roll (y-axis rotation)
    const rs = 2 * (w*y + x*z);
    const rc = 1 - 2 * (x*x + y*y);
    const roll = Math.atan2(rs, rc);

    return { yaw, pitch, roll };
}

/**
 * Get EXIF orientation from Euler angles after upright correction
 * @param pitch Pitch angle in radians
 * @param roll Roll angle in radians
 * @returns EXIF orientation code (1, 3, 6, 8)
 */
function getOrientationFromEuler({ pitch, roll }: { pitch: number, roll: number }): ExifOrientation {
    const deg = (r: number) => r * 180 / Math.PI;

    const r = deg(roll);
    const p = deg(pitch);

    // Divide roll into 4 quadrants (0°, 90°, 180°, 270°)
    // Normalize roll to 0-360° range
    const normalizedRoll = ((r % 360) + 360) % 360;

    // Quadrant-based classification:
    if (normalizedRoll >= 315 || normalizedRoll < 45) {
        // 315° to 45° (around 0°) - need to determine what this represents
        return 3; // Placeholder - might be upside-down
    } else if (normalizedRoll >= 45 && normalizedRoll < 135) {
        // 45° to 135° (around 90°) - this is where we see landscape
        // Right landscape has pitch >75°, left landscape has variable pitch
        if (p > 70) {
            return 6; // Right landscape (high pitch >70°)
        } else {
            return 8; // Left landscape (lower pitch ≤70°)
        }
    } else if (normalizedRoll >= 135 && normalizedRoll < 225) {
        // 135° to 225° (around 180°) - this is where we see portrait
        return 1; // Portrait
    } else {
        // 225° to 315° (around 270°) - fourth quadrant
        return 3; // Upside-down
    }
}

/**
 * Get EXIF orientation from AbsoluteOrientationSensor quaternion data
 * @param quaternionArray Array of 4 numbers [x, y, z, w] from AbsoluteOrientationSensor
 * @returns EXIF orientation code (1, 3, 6, 8)
 */
export function getExifOrientationFromQuaternion(quaternionArray: number[]): ExifOrientation {
	const [x, y, z, w] = quaternionArray;

	// Create quaternion from sensor data
	const q_device = new Quaternion(w, x, y, z);

	// Apply upright correction (90° rotation around X axis)
	const q_corrected = q_device.mul(uprightCorrection);

	// Convert corrected quaternion to Euler angles
	const correctedArray = [q_corrected.x, q_corrected.y, q_corrected.z, q_corrected.w];
	const euler = quaternionToEuler(correctedArray);

	// Get EXIF orientation from Euler angles
	return getOrientationFromEuler(euler);
}

/**
 * Get device orientation in degrees from device motion angles using quaternion-based approach
 * @param alpha Rotation around z-axis (compass direction) in degrees
 * @param beta Rotation around x-axis (front-to-back tilt) in degrees
 * @param gamma Rotation around y-axis (left-to-right tilt) in degrees
 * @returns Device orientation in degrees (0, 90, 180, 270)
 */
function getDeviceOrientationFromAngles(alpha: number | null, beta: number | null, gamma: number | null): number {
	if (alpha === null || beta === null || gamma === null) {
		return 0; // Default to portrait if we can't determine orientation
	}

	// Convert DeviceOrientation Euler angles to quaternion (Z-X-Y order)
	const q_device = Quaternion.fromEuler(
		alpha * Math.PI / 180,  // Z
		beta * Math.PI / 180,   // X
		gamma * Math.PI / 180,  // Y
		"ZXY"
	);

	// Apply upright correction
	const q = q_device.mul(uprightCorrection);

	// Get EXIF orientation using gravity vector approach
	const exifOrientation = quaternionToEXIF(q);

	// Convert EXIF orientation to degrees
	return getRotationFromOrientation(exifOrientation);
}

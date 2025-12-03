 // device orientation represented as exif Orientation value 1 | 3 | 6 | 8
import {derived, writable, type Writable} from "svelte/store";
// Valid EXIF orientation values
// http://sylvana.net/jpegcrop/exif_orientation.html
export type ExifOrientation = 1 | 3 | 6 | 8;

export let deviceOrientationExif: Writable<ExifOrientation> = writable(1);
export let screenOrientationAngle: Writable<number> = writable(0);
export let relativeOrientationExif = derived([deviceOrientationExif, screenOrientationAngle], ([$deviceOrientationExif, $screenOrientationAngle]) => {
	   let r = calculateWebviewRelativeOrientation($deviceOrientationExif, $screenOrientationAngle);
	   console.log(`🢄🔍📱 Calculated relativeOrientationExif: ${r} from deviceOrientationExif: ${$deviceOrientationExif} and screenOrientationAngle: ${$screenOrientationAngle}`);
	   return r;
});



 /**
 * Convert EXIF orientation code to CSS rotation degrees
 * @param orientationCode EXIF orientation value (1, 3, 6, 8)
 * @returns CSS rotation degrees
 */
export function getCssRotationFromOrientation(orientationCode: number): number {
	switch (orientationCode) {
		case 1: return 0;   // Normal portrait
		case 3: return 180; // Upside-down portrait
		case 6: return -90;  // Landscape right (90° clockwise)
		case 8: return 90; // Landscape left (90° counter-clockwise)
		default: return 0;  // Default to normal
	}
}

export function getRotationFromOrientation(orientationCode: number): number {
	switch (orientationCode) {
		case 1: return 0;   // Normal portrait
		case 3: return 180; // Upside-down portrait
		case 6: return 270;  // Landscape right (90° clockwise)
		case 8: return 90; // Landscape left (90° counter-clockwise)
		default: return 0;  // Default to normal
	}
}

export function getWebviewOrientation(): number {
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

export function calculateWebviewRelativeOrientation(
	deviceOrientationExif: ExifOrientation,
	screenOrientationAngle: number
	): ExifOrientation {


       // Calculate relative rotation: how much is the device rotated relative to the webview?
	   //const r = getRotationFromOrientation(deviceOrientationExif);
       /*const relativeRotation = (r + screenOrientationAngle + 360) % 360;

       // Map relative rotation to EXIF orientation values
       switch (relativeRotation) {
               case 0: return 1;   // Normal (device and webview aligned)
               case 90: return 6;  // Device rotated 90° clockwise relative to webview
               case 180: return 3; // Device rotated 180° relative to webview
               case 270: return 8; // Device rotated 90° counter-clockwise relative to webview
               default: {console.warn(`Unexpected relative rotation: ${relativeRotation}, defaulting to 1`); return 1; }
       }*/

	switch (deviceOrientationExif) {
		case 1: // Normal portrait
			switch (screenOrientationAngle) {
				case 0: return 1;
				case 90: return 6;
				case 180: return 3;
				case 270: return 8;
				default: {console.warn(`Unexpected screen orientation angle: ${screenOrientationAngle}, defaulting to 1`); return 1; }
			}
		case 3: // Upside-down portrait
			switch (screenOrientationAngle) {
				case 0: return 3;
				case 90: return 8;
				case 180: return 1;
				case 270: return 6;
				default: {console.warn(`Unexpected screen orientation angle: ${screenOrientationAngle}, defaulting to 1`); return 1; }
			}
		case 6: // Landscape right
			switch (screenOrientationAngle) {
				case 0: return 6;
				case 90: return 3;
				case 180: return 8;
				case 270: return 1;
				default: {console.warn(`Unexpected screen orientation angle: ${screenOrientationAngle}, defaulting to 1`); return 1; }
			}
		case 8: // Landscape left
			switch (screenOrientationAngle) {
				case 0: return 8;
				case 90: return 1;
				case 180: return 6;
				case 270: return 3;
				default: {console.warn(`Unexpected screen orientation angle: ${screenOrientationAngle}, defaulting to 1`); return 1; }
			}
		default: {console.warn(`Unexpected device orientation EXIF: ${deviceOrientationExif}, defaulting to 1`); return 1; }
	}
}


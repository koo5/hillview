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

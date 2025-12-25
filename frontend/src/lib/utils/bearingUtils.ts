import Angles from 'angles';

/**
 * Calculate the bearing color based on the absolute bearing difference
 * @param abs_bearing_diff - Absolute difference in bearing (0-180 degrees)
 * @returns HSL color string
 */
export function getBearingColor(abs_bearing_diff: number | null): string {
    if (abs_bearing_diff === null || abs_bearing_diff === undefined) return '#9E9E9E'; // grey
    return 'hsl(' + Math.round(100 - abs_bearing_diff / 2) + ', 100%, 70%)';
}

/**
 * Calculate the absolute bearing difference between two bearings
 * @param bearing1 - First bearing in degrees
 * @param bearing2 - Second bearing in degrees
 * @returns Absolute bearing difference (0-180 degrees)
 */
export function getAbsBearingDiff(bearing1: number, bearing2: number): number {
    return Math.abs(Angles.distance(bearing1, bearing2));
}

/**
 * Calculate bearing data for a photo
 * @param photoBearing - Photo's bearing in degrees
 * @param currentBearing - Current view bearing in degrees
 * @returns Object with abs_bearing_diff and bearing_color
 */
export function calculateBearingData(photoBearing: number, currentBearing: number) {
    const abs_bearing_diff = getAbsBearingDiff(currentBearing, photoBearing);
    const bearing_color = getBearingColor(abs_bearing_diff);
    return { abs_bearing_diff, bearing_color };
}

/**
 * Normalize a bearing to 0-360 degrees
 * @param bearing - Bearing in degrees
 * @returns Normalized bearing (0-360)
 */
export function normalizeBearing(bearing: number): number {
    bearing = bearing % 360;
    if (bearing < 0) bearing += 360;
    return bearing || 0; // Ensure +0, not -0 (JavaScript quirk: -360 % 360 === -0)
}

/**
 * Get the shortest angular distance between two bearings
 * @param from - Starting bearing in degrees
 * @param to - Target bearing in degrees
 * @returns Signed angular distance (-180 to 180)
 */
export function getAngularDistance(from: number, to: number): number {
    const diff = (to - from + 180) % 360 - 180;
    return diff < -180 ? diff + 360 : diff;
}

/**
 * Calculate absolute angular distance for sorting
 * @param bearing1 - First bearing in degrees
 * @param bearing2 - Second bearing in degrees
 * @returns Absolute angular distance (0-180)
 */
export function calculateAngularDistance(bearing1: number, bearing2: number): number {
    return Math.abs(Angles.distance(bearing1, bearing2));
}

/**
 * Update photo with bearing-related data
 * @param photo - Photo object
 * @param currentBearing - Current view bearing
 * @returns Photo with updated bearing data
 */
export function updatePhotoBearingDiffData<T extends { bearing: number }>(
    photo: T,
    currentBearing: number
): T & { abs_bearing_diff: number; bearing_color: string; angular_distance_abs?: number } {
    const bearingData = calculateBearingData(photo.bearing, currentBearing);
    return {
        ...photo,
        ...bearingData
    };
}
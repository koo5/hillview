import {bearingBetween, distanceBetween} from '../geo';

interface Position {
	lat: number;
	lng: number;
	speed: number | null;
	timestamp: number;
}

export interface HeadingFilterOptions {
	minSpeed?: number;       // m/s — hard floor to reject stationary jitter (default: 1.5)
	minDistance?: number;     // meters — minimum distance for a valid measurement (default: 10)
}

/**
 * Heading estimator from GPS positions with speed/distance gating.
 *
 * Instead of trusting GPS-reported heading (which is itself derived from
 * position differences by the chip), we compute heading from position pairs
 * ourselves, with smart reference point management.
 *
 * Key behaviors:
 * - Low speed: no updates, reference position held
 * - Speed picks up: bearing computed from old reference to new position (bridges the gap)
 * - No smoothing — bearing is computed directly from reference → current position
 */
export class HeadingFilter {
	// Reference position (anchor for bearing computation)
	private refPosition: Position | null = null;

	// Tuning
	private readonly minSpeed: number;
	private readonly minDistance: number;

	constructor(options?: HeadingFilterOptions) {
		this.minSpeed = options?.minSpeed ?? 1.5;
		this.minDistance = options?.minDistance ?? 10;
	}

	/**
	 * Process a new GPS position.
	 * Returns the computed heading (absolute, 0-360°), or null if the position
	 * was rejected (low speed, insufficient distance, or first position).
	 *
	 * The caller is responsible for computing diffs and applying them to the map.
	 */
	update(position: Position): number | null {
		const {lat, lng, speed} = position;

		// Gate on speed — reject stationary GPS jitter
		if (speed === null || speed < this.minSpeed) {
			// Don't update reference.
			return null;
		}

		// First valid position — store as reference anchor
		if (this.refPosition === null) {
			this.refPosition = position;
			return null;
		}

		// Distance from reference to current position (km → m)
		const distKm = distanceBetween(this.refPosition.lat, this.refPosition.lng, lat, lng);
		const distM = distKm * 1000;

		// Distance gate — positions too close, bearing would be noisy
		if (distM < this.minDistance) {
			return null;
		}

		// Compute bearing from reference → current position
		const heading = bearingBetween(
			this.refPosition.lat, this.refPosition.lng,
			lat, lng
		);

		// Update reference position
		this.refPosition = position;

		return heading;
	}

	reset() {
		this.refPosition = null;
	}
}

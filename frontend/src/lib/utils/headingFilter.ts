import {bearingBetween, distanceBetween} from '../geo';
import {normalizeBearing} from './bearingUtils';

interface Position {
	lat: number;
	lng: number;
	speed: number | null;
	timestamp: number;
}

export interface HeadingFilterOptions {
	processNoise?: number;   // deg²/s — how fast heading can change (default: 1.0)
	minSpeed?: number;       // m/s — hard floor to reject stationary jitter (default: 1.5)
	minDistance?: number;     // meters — minimum distance for a valid measurement (default: 10)
}

/**
 * 1D Kalman filter for heading estimation from GPS positions.
 *
 * Instead of trusting GPS-reported heading (which is itself derived from
 * position differences by the chip), we compute heading from position pairs
 * ourselves, with smart reference point management.
 *
 * Key behaviors:
 * - Low speed: no updates, reference position held, uncertainty grows
 * - Speed picks up: bearing computed from old reference to new position (bridges the gap)
 * - After long stop: high uncertainty → high Kalman gain → snaps to new direction
 * - Highway speed: frequent updates, low noise, smooth tracking
 */
export class HeadingFilter {
	// Kalman state
	private heading: number | null = null;
	private P: number = 180 * 180; // variance — start with max uncertainty

	// Reference position (anchor for bearing computation)
	private refPosition: Position | null = null;

	// Tuning
	private readonly Q: number;
	private readonly minSpeed: number;
	private readonly minDistance: number;

	constructor(options?: HeadingFilterOptions) {
		this.Q = options?.processNoise ?? 1.0;
		this.minSpeed = options?.minSpeed ?? 1.5;
		this.minDistance = options?.minDistance ?? 10;
	}

	/**
	 * Process a new GPS position.
	 * Returns the Kalman-filtered heading estimate (absolute, 0-360°), or null
	 * if the filter doesn't have enough data yet or the position was rejected.
	 *
	 * The caller is responsible for computing diffs and applying them to the map.
	 */
	update(position: Position): number | null {
		const {lat, lng, speed, timestamp} = position;

		// Gate on speed — reject stationary GPS jitter
		if (speed === null || speed < this.minSpeed) {
			// Don't update reference, don't update heading.
			// Uncertainty will grow when we next get a valid measurement (via dt).
			return null;
		}

		// First valid position — store as reference anchor
		if (this.refPosition === null) {
			this.refPosition = {lat, lng, speed, timestamp};
			return null;
		}

		// Distance from reference to current position (km → m)
		const distKm = distanceBetween(this.refPosition.lat, this.refPosition.lng, lat, lng);
		const distM = distKm * 1000;

		// Time since reference
		const dt = Math.max(0.001, (timestamp - this.refPosition.timestamp) / 1000);

		// Distance gate — positions too close, bearing would be noisy
		if (distM < this.minDistance) {
			// Prediction only: increase uncertainty over time
			if (this.heading !== null) {
				this.P += this.Q * dt;
			}
			return null;
		}

		// Compute measured bearing from reference → current position
		const measuredBearing = bearingBetween(
			this.refPosition.lat, this.refPosition.lng,
			lat, lng
		);

		// Measurement noise: inversely proportional to distance²
		// At minDistance (10m): R ≈ 100 deg²
		// At 50m: R ≈ 4 deg²
		// At 100m: R ≈ 1 deg²
		const R = Math.max(1, (this.minDistance * this.minDistance) / (distM * distM) * 100);

		// First measurement — initialize heading
		if (this.heading === null) {
			this.heading = measuredBearing;
			this.P = R;
			this.refPosition = {lat, lng, speed, timestamp};
			return this.heading;
		}

		// --- Kalman predict ---
		// Heading prediction: constant heading model (heading stays same)
		// Variance grows with time
		this.P += this.Q * dt;

		// --- Kalman update ---
		// Innovation: shortest angular difference (wrapped to ±180°)
		let innovation = measuredBearing - this.heading;
		innovation = ((innovation % 360) + 540) % 360 - 180;

		// Kalman gain
		const K = this.P / (this.P + R);

		// Update heading estimate
		this.heading = normalizeBearing(this.heading + K * innovation);
		this.P = (1 - K) * this.P;

		// Update reference position
		this.refPosition = {lat, lng, speed, timestamp};

		return this.heading;
	}

	reset() {
		this.heading = null;
		this.P = 180 * 180;
		this.refPosition = null;
	}
}

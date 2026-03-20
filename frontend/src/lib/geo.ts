/**
 * Compute a destination point given a start, bearing (degrees), and distance (km).
 * Uses the Haversine-based forward formula on a spherical Earth (R = 6371 km).
 */
export function destinationPoint(
	lat: number,
	lng: number,
	bearing: number,
	distanceKm: number
): { lat: number; lng: number } {
	const R = 6371;
	const d = distanceKm / R;
	const brng = (bearing * Math.PI) / 180;
	const lat1 = (lat * Math.PI) / 180;
	const lng1 = (lng * Math.PI) / 180;
	const lat2 = Math.asin(
		Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(brng)
	);
	const lng2 =
		lng1 +
		Math.atan2(
			Math.sin(brng) * Math.sin(d) * Math.cos(lat1),
			Math.cos(d) - Math.sin(lat1) * Math.sin(lat2)
		);
	return { lat: (lat2 * 180) / Math.PI, lng: (lng2 * 180) / Math.PI };
}

/**
 * Compute the initial bearing (degrees, 0-360) from point 1 to point 2.
 */
export function bearingBetween(
	lat1: number, lng1: number,
	lat2: number, lng2: number
): number {
	const φ1 = (lat1 * Math.PI) / 180;
	const φ2 = (lat2 * Math.PI) / 180;
	const Δλ = ((lng2 - lng1) * Math.PI) / 180;
	const y = Math.sin(Δλ) * Math.cos(φ2);
	const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
	return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

/**
 * Compute the great-circle distance (km) between two points using the Haversine formula.
 */
export function distanceBetween(
	lat1: number, lng1: number,
	lat2: number, lng2: number
): number {
	const R = 6371;
	const φ1 = (lat1 * Math.PI) / 180;
	const φ2 = (lat2 * Math.PI) / 180;
	const Δφ = ((lat2 - lat1) * Math.PI) / 180;
	const Δλ = ((lng2 - lng1) * Math.PI) / 180;
	const a = Math.sin(Δφ / 2) ** 2 + Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) ** 2;
	return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

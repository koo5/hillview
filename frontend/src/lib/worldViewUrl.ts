import type { WorldView } from '$world/worldView';

/** Absolute altitude uses the scene's WGS84 ellipsoidal metres. Missing fields keep the usual initial view. */
export function parseWorldViewParams(params: URLSearchParams): { altitude?: number; pitch: number; fov: number } {
	function finite(key: string): number | undefined {
		const value = params.get(key);
		if (value === null || value.trim() === '') return undefined;
		const n = Number(value);
		return Number.isFinite(n) ? n : undefined;
	}
	const pitch = finite('pitch'), fov = finite('fov');
	return {
		altitude: finite('altitude'),
		pitch: pitch !== undefined && pitch >= -90 && pitch <= 90 ? pitch : -5,
		fov: fov !== undefined && fov >= 0.1 && fov <= 120 ? fov : 55
	};
}

/** Start a fresh map link: an incidental selected photo or photo/terrain zoom must not redirect the camera. */
export function constructWorldShareUrl(baseUrl: string, zoom: number, view: WorldView): string {
	const url = new URL('/', baseUrl);
	url.search = new URLSearchParams({
		activity: '3d',
		lat: view.lat.toFixed(8),
		lon: view.lon.toFixed(8),
		zoom: String(zoom),
		altitude: view.altitude.toFixed(2),
		bearing: view.bearing.toFixed(4),
		pitch: view.pitch.toFixed(4),
		fov: view.fov.toFixed(4)
	}).toString();
	return url.toString();
}

import { execFileSync } from 'child_process';

/**
 * Emulator geo-location helper. Wraps `adb emu geo fix|nmea|gnss` so specs
 * can inject position (and, via NMEA, speed) into the running emulator.
 *
 * `emu geo fix` takes longitude/latitude/altitude/satellites — no speed, so
 * the app's Kalman filter (which has a 1.5 m/s speed gate) never fires.
 * NMEA $GPRMC carries speed-over-ground in knots, so use `emuGeoNmea` +
 * `buildGprmc` when driving the car-mode flow.
 */

let cachedSerial: string | null = null;

export function findEmulatorSerial(): string {
	if (cachedSerial) return cachedSerial;
	const out = execFileSync('adb', ['devices'], { encoding: 'utf8' });
	const line = out.split('\n').find(l => /^emulator-\d+\s+device/.test(l));
	if (!line) {
		throw new Error(`No emulator device in 'adb devices' output:\n${out}`);
	}
	cachedSerial = line.split(/\s+/)[0];
	return cachedSerial;
}

function adbEmu(args: string[], serial = findEmulatorSerial()): void {
	execFileSync('adb', ['-s', serial, 'emu', ...args], { stdio: 'pipe' });
}

export function emuGeoFix(lat: number, lng: number, alt = 100, sats = 8): void {
	adbEmu(['geo', 'fix', String(lng), String(lat), String(alt), String(sats)]);
}

export function emuGeoNmea(sentence: string): void {
	// `adb emu geo nmea ...` — the sentence must include the leading `$` and
	// trailing `*<checksum>`. `buildGprmc` produces a well-formed one.
	adbEmu(['geo', 'nmea', sentence]);
}

const MS_TO_KNOTS = 1.9438444924406046;

export function metersPerSecondToKnots(mps: number): number {
	return mps * MS_TO_KNOTS;
}

/**
 * Build a well-formed `$GPRMC` NMEA sentence including the XOR checksum.
 *
 * Format: `$GPRMC,hhmmss.ss,A,ddmm.mmmm,N,dddmm.mmmm,E,speed_kn,course_deg,ddmmyy,,*CS`
 *
 * - `speedKnots` is speed-over-ground in knots (use `metersPerSecondToKnots`).
 * - `courseDeg` is the course over ground (not required to match heading of
 *   travel; our Kotlin filter derives heading from position deltas anyway).
 * - `date` defaults to the current wall-clock time.
 */
export function buildGprmc(opts: {
	lat: number;
	lng: number;
	speedKnots: number;
	courseDeg: number;
	date?: Date;
}): string {
	const { lat, lng, speedKnots, courseDeg, date = new Date() } = opts;
	const hhmmss = utcTime(date);
	const ddmmyy = utcDate(date);
	const [latStr, ns] = formatLat(lat);
	const [lngStr, ew] = formatLng(lng);
	const body = `GPRMC,${hhmmss},A,${latStr},${ns},${lngStr},${ew},${speedKnots.toFixed(2)},${courseDeg.toFixed(1)},${ddmmyy},,`;
	const checksum = nmeaChecksum(body);
	return `$${body}*${checksum}`;
}

function utcTime(d: Date): string {
	const hh = String(d.getUTCHours()).padStart(2, '0');
	const mm = String(d.getUTCMinutes()).padStart(2, '0');
	const ss = String(d.getUTCSeconds()).padStart(2, '0');
	const hundredths = String(Math.floor(d.getUTCMilliseconds() / 10)).padStart(2, '0');
	return `${hh}${mm}${ss}.${hundredths}`;
}

function utcDate(d: Date): string {
	const dd = String(d.getUTCDate()).padStart(2, '0');
	const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
	const yy = String(d.getUTCFullYear() % 100).padStart(2, '0');
	return `${dd}${mm}${yy}`;
}

function formatLat(lat: number): [string, 'N' | 'S'] {
	const ns = lat >= 0 ? 'N' : 'S';
	const abs = Math.abs(lat);
	const deg = Math.floor(abs);
	const min = (abs - deg) * 60;
	return [`${String(deg).padStart(2, '0')}${min.toFixed(4).padStart(7, '0')}`, ns];
}

function formatLng(lng: number): [string, 'E' | 'W'] {
	const ew = lng >= 0 ? 'E' : 'W';
	const abs = Math.abs(lng);
	const deg = Math.floor(abs);
	const min = (abs - deg) * 60;
	return [`${String(deg).padStart(3, '0')}${min.toFixed(4).padStart(7, '0')}`, ew];
}

function nmeaChecksum(body: string): string {
	let cs = 0;
	for (let i = 0; i < body.length; i++) cs ^= body.charCodeAt(i);
	return cs.toString(16).toUpperCase().padStart(2, '0');
}

export interface Waypoint {
	lat: number;
	lng: number;
	/** Speed-over-ground in m/s. Defaults to 5 m/s. */
	speedMps?: number;
	/** Course over ground in degrees. Defaults to 0. */
	courseDeg?: number;
}

export async function streamWaypoints(
	waypoints: Waypoint[],
	options: { intervalMs?: number } = {}
): Promise<void> {
	const intervalMs = options.intervalMs ?? 1100;
	for (const wp of waypoints) {
		const sentence = buildGprmc({
			lat: wp.lat,
			lng: wp.lng,
			speedKnots: metersPerSecondToKnots(wp.speedMps ?? 5),
			courseDeg: wp.courseDeg ?? 0,
		});
		emuGeoNmea(sentence);
		await new Promise(r => setTimeout(r, intervalMs));
	}
}

/**
 * Build a list of waypoints moving in a straight line from a start point
 * along a compass heading, with fixed spacing in meters. Useful for
 * exercising the car-mode heading filter (which needs >10 m spacing and
 * >1.5 m/s speed to produce a bearing).
 */
export function linearPath(opts: {
	startLat: number;
	startLng: number;
	headingDeg: number;
	stepMeters: number;
	steps: number;
	speedMps?: number;
}): Waypoint[] {
	const { startLat, startLng, headingDeg, stepMeters, steps, speedMps = 5 } = opts;
	const out: Waypoint[] = [];
	// Approximate: 1 deg lat ≈ 111,320 m; 1 deg lng ≈ 111,320 * cos(lat)
	const latRad = startLat * Math.PI / 180;
	const hdgRad = headingDeg * Math.PI / 180;
	const dLatPerStep = (stepMeters * Math.cos(hdgRad)) / 111320;
	const dLngPerStep = (stepMeters * Math.sin(hdgRad)) / (111320 * Math.cos(latRad));
	for (let i = 0; i <= steps; i++) {
		out.push({
			lat: startLat + dLatPerStep * i,
			lng: startLng + dLngPerStep * i,
			speedMps,
			courseDeg: headingDeg,
		});
	}
	return out;
}

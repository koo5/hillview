/**
 * Which way is down at the shutter: the maths behind the web capture's gravity
 * stamp and its level indicator. Pure, with no DOM, so vitest reaches all of it;
 * capturePose.ts owns the sensors and the one state.
 *
 * Vectors are the UP vector in DEVICE coordinates, the way Android's
 * TYPE_GRAVITY reports it at rest: x to the screen's right, y to its top, z out
 * of the screen, |g| = 9.81. Upright portrait is [0, g, 0] and flat on a table
 * is [0, 0, g]. Chromium's GravitySensor({referenceFrame: 'device'}) is that
 * sensor; elsewhere the vector is converted from deviceorientation's beta/gamma.
 *
 * pitch and roll are a port of the gravity branch of backend/common/capture_pose.py,
 * in GPano conventions: pitch positive UP, roll measured from the nearest quarter
 * turn and positive when the horizon rotates counterclockwise in the image, NULL
 * within ROLL_FLOOR of flat. backend/common/capture_pose_cases.json holds the
 * cases both must agree on. See docs/todo/photo-pose-and-level-gates.md for the
 * conventions and docs/todo/web-capture-level-stamp.md for this module's plan.
 */

import { MAX_PITCH_DEG, MAX_ROLL_DEG } from './panoramaxStatus';
import type { ExifOrientation } from './deviceOrientationExif';

export const STANDARD_GRAVITY = 9.80665;

/** sin(15°): the share of gravity in the image plane below which roll is not a
 * horizon tilt. ROLL_FLOOR in capture_pose.py, GRAVITY_ROLL_FLOOR in frontend2. */
export const ROLL_FLOOR = 0.26;

/** What the shutter stamps: the samples of the last 300 ms. */
export const STAMP_WINDOW_MS = 300;
/** What the indicator draws: a shorter, display-only average, so it keeps up. */
export const DISPLAY_WINDOW_MS = 150;
/** How much the ring keeps. */
export const RING_MS = 1000;

export type Vec3 = [number, number, number];
export type GravitySource = 'gravity-sensor' | 'deviceorientation';
export type LevelState = 'level' | 'tilted' | 'flat' | 'unmeasured';

export interface GravitySample {
	/** performance.now() when it arrived */
	t: number;
	g: Vec3;
	source: GravitySource;
}

/** The `inertial` object a web capture stamps. Sent as is; the worker folds it
 * into the synthesized UserComment, where capture_pose reads `gravity`. */
export interface InertialStamp {
	gravity: Vec3;
	/** how old the newest sample was at the shutter */
	age_ms: number;
	gravity_source: GravitySource;
	sample_count: number;
	window_ms: number;
	/** the largest angle between a sample and the mean: diagnostic, never gated on */
	gravity_spread_deg: number;
}

export interface Pose {
	pitch: number;
	roll: number | null;
}

const DEG = 180 / Math.PI;

function length(v: readonly number[]): number {
	return Math.hypot(v[0], v[1], v[2]);
}

/** Three finite numbers of non-zero length: what capture_pose accepts. */
export function isUsableGravity(g: unknown): g is Vec3 {
	if (!Array.isArray(g) || g.length !== 3) return false;
	if (!g.every((v) => typeof v === 'number' && Number.isFinite(v))) return false;
	const n = length(g);
	return n > 0 && Number.isFinite(n);
}

/**
 * The up vector from deviceorientation's beta and gamma, degrees.
 *
 * The spec's rotation matrix is R = Rz(alpha)·Rx(beta)·Ry(gamma), device to
 * earth; the earth's up in device coordinates is its bottom row, which does not
 * involve alpha. It is the same row WebKit derives beta/gamma from. Near upright
 * portrait the angles jump (beta crosses 90° and gamma swings through ±90°)
 * while this vector does not, so samples are averaged as vectors, never as angles.
 */
export function gravityFromBetaGamma(betaDeg: number | null, gammaDeg: number | null): Vec3 | null {
	if (betaDeg == null || gammaDeg == null || !Number.isFinite(betaDeg) || !Number.isFinite(gammaDeg)) {
		return null;
	}
	const b = betaDeg / DEG;
	const g = gammaDeg / DEG;
	return [
		-STANDARD_GRAVITY * Math.cos(b) * Math.sin(g),
		STANDARD_GRAVITY * Math.sin(b),
		STANDARD_GRAVITY * Math.cos(b) * Math.cos(g),
	];
}

/** GPano roll from a stamp-style roll (atan2(g_x, g_y), degrees): its residual
 * from the nearest quarter turn, negated, in (-45, 45]. level_roll in capture_pose.py. */
export function levelRoll(rollDeg: number): number {
	const residual = rollDeg - 90 * Math.floor(rollDeg / 90 + 0.5);
	return -residual + 0; // + 0 turns -0 into 0
}

/** pitch and roll in GPano conventions; null for a vector capture_pose would reject. */
export function poseFromGravity(g: Vec3 | null): Pose | null {
	if (!isUsableGravity(g)) return null;
	const [x, y, z] = g;
	const n = length(g);
	const pitch = -Math.asin(Math.max(-1, Math.min(1, z / n))) * DEG + 0;
	if (Math.hypot(x, y) / n < ROLL_FLOOR) return { pitch, roll: null };
	return { pitch, roll: levelRoll(Math.atan2(x, y) * DEG) };
}

/** Device quarter turn, matching the native OrientationEventListener/EXIF map.
 * Keep the previous orientation near flat: gravity cannot say which edge is up.
 * Screen rotation is applied separately by relativeOrientationExif. */
export function exifOrientationFromGravity(g: Vec3 | null): ExifOrientation | null {
	if (!isUsableGravity(g) || Math.hypot(g[0], g[1]) / length(g) < ROLL_FLOOR) return null;
	const angle = (Math.atan2(-g[0], g[1]) * DEG + 360) % 360;
	return ([1, 6, 3, 8] as const)[Math.floor((angle + 45) / 90) % 4];
}

/** What the Panoramax pitch and roll gates will decide, in the indicator's words. */
export function levelState(pose: Pose | null): LevelState {
	if (!pose) return 'unmeasured';
	if (pose.roll === null) return 'flat';
	return Math.abs(pose.pitch) <= MAX_PITCH_DEG && Math.abs(pose.roll) <= MAX_ROLL_DEG ? 'level' : 'tilted';
}

/** The state said in words, so it is never colour alone. null when unmeasured. */
export function levelWords(pose: Pose | null): string | null {
	const state = levelState(pose);
	if (state === 'unmeasured' || !pose) return null;
	if (state === 'flat') return pose.pitch < 0 ? 'Pointing at the ground' : 'Pointing at the sky';
	if (state === 'level') return 'Level';
	const parts: string[] = [];
	if (Math.abs(pose.pitch) > MAX_PITCH_DEG) {
		parts.push(`Tilted ${pose.pitch < 0 ? 'down' : 'up'} ${Math.round(Math.abs(pose.pitch))}°`);
	}
	if (pose.roll !== null && Math.abs(pose.roll) > MAX_ROLL_DEG) {
		parts.push(`Horizon tilted ${Math.round(Math.abs(pose.roll))}°`);
	}
	return parts.join(' · ');
}

export interface GravityAverage {
	gravity: Vec3;
	source: GravitySource;
	sample_count: number;
	age_ms: number;
	spread_deg: number;
}

/**
 * The mean of the unit vectors of the samples no older than windowMs at nowMs,
 * scaled back to standard gravity. Only the newest sample's source counts, so a
 * window never mixes a sensor reading with a converted one. null when no sample
 * is fresh: a stale or default vector is never offered in its place.
 */
export function averageGravity(samples: readonly GravitySample[], nowMs: number, windowMs: number): GravityAverage | null {
	let newest: GravitySample | null = null;
	for (const s of samples) {
		if (s.t <= nowMs && nowMs - s.t <= windowMs && (!newest || s.t >= newest.t)) newest = s;
	}
	if (!newest) return null;
	const source = newest.source;
	const units: Vec3[] = [];
	for (const s of samples) {
		if (s.source !== source || s.t > nowMs || nowMs - s.t > windowMs || !isUsableGravity(s.g)) continue;
		const n = length(s.g);
		units.push([s.g[0] / n, s.g[1] / n, s.g[2] / n]);
	}
	const sum: Vec3 = [0, 0, 0];
	for (const u of units) {
		sum[0] += u[0];
		sum[1] += u[1];
		sum[2] += u[2];
	}
	const n = length(sum);
	if (!(n > 1e-9)) return null; // samples cancelling out: no single "down" to offer
	const mean: Vec3 = [sum[0] / n, sum[1] / n, sum[2] / n];
	let spread = 0;
	for (const u of units) {
		const cos = Math.max(-1, Math.min(1, u[0] * mean[0] + u[1] * mean[1] + u[2] * mean[2]));
		spread = Math.max(spread, Math.acos(cos) * DEG);
	}
	return {
		gravity: [mean[0] * STANDARD_GRAVITY, mean[1] * STANDARD_GRAVITY, mean[2] * STANDARD_GRAVITY],
		source,
		sample_count: units.length,
		age_ms: nowMs - newest.t,
		spread_deg: spread,
	};
}

function round(value: number, digits: number): number {
	const f = 10 ** digits;
	return Math.round(value * f) / f + 0;
}

/**
 * The `inertial` object for a capture at nowMs, or null to send none.
 *
 * None for a camera that faces the user: capture_pose assumes the lens looks
 * along -z, the back camera's axis, so a front camera's pitch would read inverted.
 */
export function buildInertialStamp(
	samples: readonly GravitySample[],
	nowMs: number,
	facing?: string | null
): InertialStamp | null {
	if (facing === 'user') return null;
	const avg = averageGravity(samples, nowMs, STAMP_WINDOW_MS);
	if (!avg) return null;
	return {
		gravity: [round(avg.gravity[0], 6), round(avg.gravity[1], 6), round(avg.gravity[2], 6)],
		age_ms: Math.round(avg.age_ms),
		gravity_source: avg.source,
		sample_count: avg.sample_count,
		window_ms: STAMP_WINDOW_MS,
		gravity_spread_deg: round(avg.spread_deg, 2),
	};
}

function normalizeAngle(deg: number): number {
	const a = ((deg % 360) + 360) % 360;
	return a > 180 ? a - 360 : a;
}

/**
 * The true horizon's angle on the page, as a CSS rotation (clockwise degrees,
 * 0 = horizontal).
 *
 * In device coordinates (g_x, g_y) points to the sky in the screen plane and the
 * horizon is perpendicular to it, so on a page upright to the phone the horizon
 * is turned clockwise by atan2(g_x, g_y): a phone turned counterclockwise (a
 * positive stamp roll_deg) shows the horizon turned clockwise, as the 2026-11-15
 * series showed for the image. A page the browser has rotated by
 * screenOrientationAngle has that taken off first.
 */
export function horizonScreenAngle(g: Vec3, screenAngleDeg: number): number {
	return normalizeAngle(Math.atan2(g[0], g[1]) * DEG - screenAngleDeg);
}

/** Where the horizon must lie for level roll 0: the nearest quarter turn, on the page. */
export function levelReferenceScreenAngle(g: Vec3, screenAngleDeg: number): number {
	const r = Math.atan2(g[0], g[1]) * DEG;
	return normalizeAngle(90 * Math.floor(r / 90 + 0.5) - screenAngleDeg);
}

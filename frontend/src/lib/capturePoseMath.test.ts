import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
	averageGravity,
	buildInertialStamp,
	exifOrientationFromGravity,
	gravityFromBetaGamma,
	horizonScreenAngle,
	levelReferenceScreenAngle,
	levelRoll,
	levelState,
	levelWords,
	poseFromGravity,
	ROLL_FLOOR,
	STANDARD_GRAVITY as G,
	STAMP_WINDOW_MS,
	type GravitySample,
	type GravitySource,
	type Vec3,
} from './capturePoseMath';
import { MAX_PITCH_DEG, MAX_ROLL_DEG, PANORAMAX_GATE_TEXT } from './panoramaxStatus';
import { calculateWebviewRelativeOrientation, type ExifOrientation } from './deviceOrientationExif';

describe('capture quarter-turn orientation', () => {
	it.each<[Vec3, ExifOrientation, number]>([
		[[0, G, 0], 1, 0],
		[[-G, 0, 0], 6, 270],
		[[0, -G, 0], 3, 180],
		[[G, 0, 0], 8, 90],
	])('maps gravity %j to EXIF %i independently of the display', (gravity, orientation, screenAngle) => {
		expect(exifOrientationFromGravity(gravity)).toBe(orientation);
		// A locked portrait display shows the actual physical quarter turn.
		expect(calculateWebviewRelativeOrientation(orientation, 0)).toBe(orientation);
		// Auto-rotation already turned the page, so no further rotation is needed.
		expect(calculateWebviewRelativeOrientation(orientation, screenAngle)).toBe(1);
	});

	it('keeps the nearest quarter turn while the phone leans or tilts', () => {
		expect(exifOrientationFromGravity([3, 9, 2])).toBe(1);
		expect(exifOrientationFromGravity([-9, 3, -2])).toBe(6);
		expect(exifOrientationFromGravity([-3, -9, 2])).toBe(3);
		expect(exifOrientationFromGravity([9, -3, -2])).toBe(8);
	});

	it.each(([null, [0, 0, 0], [0.1, 0.1, G], [0, 0, -G], [NaN, G, 0]] as (Vec3 | null)[])
		.map(gravity => ({ gravity })))(
		'does not invent a new orientation for a flat or missing pose $gravity', ({ gravity }) => {
			expect(exifOrientationFromGravity(gravity)).toBeNull();
		}
	);
});

// The cases capture_pose.py and this port must agree on, with the gate limits.
// The backend's test pins the same file to eligibility.py.
interface Case {
	id: string;
	gravity: Vec3;
	pitch: number;
	roll: number | null;
	level: string;
	beta?: number;
	gamma?: number;
}
const FIXTURE = JSON.parse(
	// (happy-dom replaces URL, so the path is resolved without it)
	readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../../backend/common/capture_pose_cases.json'), 'utf8')
) as { max_pitch_deg: number; max_roll_deg: number; roll_floor: number; cases: Case[]; deviceorientation: Case[] };

const atan2Deg = (g: Vec3) => (Math.atan2(g[0], g[1]) * 180) / Math.PI;

function expectVec(actual: Vec3 | null, expected: number[], digits = 4) {
	expect(actual).not.toBeNull();
	actual!.forEach((v, i) => expect(v).toBeCloseTo(expected[i], digits));
}

function samples(vectors: Vec3[], nowMs: number, stepMs = 16, source: GravitySource = 'gravity-sensor'): GravitySample[] {
	// the newest last, at nowMs - stepMs
	return vectors.map((g, i) => ({ t: nowMs - stepMs * (vectors.length - i), g, source }));
}

describe('the shared fixture', () => {
	it('carries the limits panoramaxStatus.ts and this module use', () => {
		expect([FIXTURE.max_pitch_deg, FIXTURE.max_roll_deg]).toEqual([MAX_PITCH_DEG, MAX_ROLL_DEG]);
		expect(FIXTURE.roll_floor).toBe(ROLL_FLOOR);
	});

	it('words the gates with the same limits', () => {
		expect(PANORAMAX_GATE_TEXT.pitch).toContain(`over ${MAX_PITCH_DEG}°`);
		expect(PANORAMAX_GATE_TEXT.roll).toContain(`over ${MAX_ROLL_DEG}°`);
	});

	it.each([...FIXTURE.cases, ...FIXTURE.deviceorientation].map((c) => [c.id, c] as const))(
		'%s: pitch, roll and the verdict',
		(_id, c) => {
			const pose = poseFromGravity(c.gravity);
			expect(pose).not.toBeNull();
			expect(pose!.pitch).toBeCloseTo(c.pitch, 2);
			if (c.roll === null) expect(pose!.roll).toBeNull();
			else expect(pose!.roll).toBeCloseTo(c.roll, 2);
			expect(levelState(pose)).toBe(c.level);
		}
	);

	it.each(FIXTURE.deviceorientation.map((c) => [c.id, c] as const))(
		'%s: beta/gamma convert to the fixture vector',
		(_id, c) => {
			expectVec(gravityFromBetaGamma(c.beta!, c.gamma!), c.gravity);
		}
	);
});

describe('gravityFromBetaGamma', () => {
	it('upright portrait points up the screen', () => {
		expectVec(gravityFromBetaGamma(90, 0), [0, G, 0]);
	});

	it('flat on its back points out of the screen', () => {
		expectVec(gravityFromBetaGamma(0, 0), [0, 0, G]);
	});

	it('upside down points down the screen', () => {
		expectVec(gravityFromBetaGamma(-90, 0), [0, -G, 0]);
	});

	it('a counterclockwise roll gives a positive roll_deg, and a clockwise one a negative', () => {
		// Upright, 15° each way: gamma pinned at -90 and beta either side of 90.
		const ccw = gravityFromBetaGamma(75, -90)!;
		const cw = gravityFromBetaGamma(105, -90)!;
		expect(atan2Deg(ccw)).toBeCloseTo(15, 6);
		expect(atan2Deg(cw)).toBeCloseTo(-15, 6);
		// GPano roll is the opposite sign: the scene turns the other way in the image.
		expect(poseFromGravity(ccw)!.roll).toBeCloseTo(-15, 6);
		expect(poseFromGravity(cw)!.roll).toBeCloseTo(15, 6);
	});

	it('both landscapes are a quarter turn each way, and level', () => {
		const left = gravityFromBetaGamma(0, -90)!; // top of the phone to the left
		const right = gravityFromBetaGamma(0, 89.9)!;
		expect(atan2Deg(left)).toBeCloseTo(90, 6);
		expect(atan2Deg(right)).toBeCloseTo(-90, 6);
		expect(levelState(poseFromGravity(left))).toBe('level');
		expect(levelState(poseFromGravity(right))).toBe('level');
	});

	it('is continuous where the angles wrap near upright portrait', () => {
		// gamma lives in [-90, 90): rolling an upright phone past gamma = -90 makes a
		// browser report (180 - beta, gamma + 180) instead. Neighbouring attitudes on
		// the two sides of that wrap have angles 20° and 179° apart, and vectors not.
		for (const [beta, eps] of [[80, 1], [85, 0.5], [70, 2]]) {
			const a = gravityFromBetaGamma(beta, -90 + eps)!;
			const b = gravityFromBetaGamma(180 - beta, 90 - eps)!;
			const cos = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) / (G * G);
			expect((Math.acos(Math.min(1, cos)) * 180) / Math.PI).toBeLessThan(2 * eps + 1e-6);
		}
	});

	it('gives nothing without both angles', () => {
		expect(gravityFromBetaGamma(null, 0)).toBeNull();
		expect(gravityFromBetaGamma(90, null)).toBeNull();
		expect(gravityFromBetaGamma(NaN, 0)).toBeNull();
	});
});

describe('averageGravity', () => {
	it('averages across the near-upright wrap, where averaging the angles would not', () => {
		// An upright phone rolled 10° counterclockwise, jittering across gamma = -90:
		// the browser alternates between (80, -89) and (100, 89).
		const vectors = Array.from({ length: 10 }, (_, i) =>
			i % 2 ? gravityFromBetaGamma(100, 89)! : gravityFromBetaGamma(80, -89)!
		);
		const avg = averageGravity(samples(vectors, 1000), 1000, STAMP_WINDOW_MS)!;
		const pose = poseFromGravity(avg.gravity)!;
		expect(pose.pitch).toBeCloseTo(0, 2);
		expect(pose.roll).toBeCloseTo(-10, 1);
		expect(avg.spread_deg).toBeLessThan(0.5);
		// The angles' own mean, (90, 0), is upright and unrolled: the roll is lost.
		expect(poseFromGravity(gravityFromBetaGamma((80 + 100) / 2, (-89 + 89) / 2))!.roll).toBeCloseTo(0, 6);
	});

	it('scales the mean of unit vectors back to standard gravity', () => {
		const avg = averageGravity(samples([[0, 9.7, 0], [0, 9.9, 0.2]], 500), 500, 300)!;
		expect(Math.hypot(...avg.gravity)).toBeCloseTo(G, 9);
		expect(avg.sample_count).toBe(2);
		expect(avg.age_ms).toBe(16);
		expect(avg.spread_deg).toBeGreaterThan(0);
	});

	it('is null for an empty or stale window, and ignores samples after now', () => {
		expect(averageGravity([], 1000, 300)).toBeNull();
		const old: GravitySample[] = [{ t: 600, g: [0, G, 0], source: 'gravity-sensor' }];
		expect(averageGravity(old, 1000, 300)).toBeNull();
		expect(averageGravity(old, 900, 300)).not.toBeNull();
		const future: GravitySample[] = [{ t: 1001, g: [0, G, 0], source: 'gravity-sensor' }];
		expect(averageGravity(future, 1000, 300)).toBeNull();
	});

	it('uses only the newest sample source', () => {
		const mixed: GravitySample[] = [
			{ t: 900, g: [0, 0, G], source: 'deviceorientation' },
			{ t: 950, g: [0, G, 0], source: 'gravity-sensor' },
		];
		const avg = averageGravity(mixed, 1000, 300)!;
		expect(avg.source).toBe('gravity-sensor');
		expect(avg.sample_count).toBe(1);
		expectVec(avg.gravity, [0, G, 0]);
	});
});

describe('buildInertialStamp', () => {
	const ring = samples([[3.8, 9.02, -0.64], [3.802262, 9.020489, -0.640069], [3.81, 9.03, -0.63]], 2000);

	it('is the inertial object of the last 300 ms', () => {
		const stamp = buildInertialStamp(ring, 2000, 'environment')!;
		expect(Object.keys(stamp)).toEqual([
			'gravity', 'age_ms', 'gravity_source', 'sample_count', 'window_ms', 'gravity_spread_deg',
		]);
		expect(stamp.gravity_source).toBe('gravity-sensor');
		expect(stamp.sample_count).toBe(3);
		expect(stamp.window_ms).toBe(300);
		expect(stamp.age_ms).toBe(16);
		expect(Math.hypot(...stamp.gravity)).toBeCloseTo(G, 4);
		const pose = poseFromGravity(stamp.gravity)!;
		expect(pose.pitch).toBeCloseTo(3.741, 1);
		expect(pose.roll).toBeCloseTo(-22.856, 1);
		// JSON-ready: plain numbers, no -0
		expect(JSON.parse(JSON.stringify(stamp))).toEqual(stamp);
	});

	it('is null when no sample is fresh, never a stale or default vector', () => {
		expect(buildInertialStamp([], 2000, 'environment')).toBeNull();
		expect(buildInertialStamp(ring, 2400, 'environment')).toBeNull();
	});

	it('is left out for a camera facing the user', () => {
		expect(buildInertialStamp(ring, 2000, 'user')).toBeNull();
		// An unknown facing (a fake camera, a browser that does not say) keeps it.
		expect(buildInertialStamp(ring, 2000, null)).not.toBeNull();
		expect(buildInertialStamp(ring, 2000, undefined)).not.toBeNull();
	});
});

describe('the indicator', () => {
	it('is unmeasured without a vector, and for junk', () => {
		expect(levelState(null)).toBe('unmeasured');
		expect(levelState(poseFromGravity([0, 0, 0]))).toBe('unmeasured');
		expect(levelState(poseFromGravity([NaN, G, 0]))).toBe('unmeasured');
		expect(levelWords(null)).toBeNull();
	});

	it('says the state in words', () => {
		expect(levelWords({ pitch: 3, roll: -4 })).toBe('Level');
		expect(levelWords({ pitch: -25.4, roll: 2 })).toBe('Tilted down 25°');
		expect(levelWords({ pitch: 31, roll: -12.2 })).toBe('Tilted up 31° · Horizon tilted 12°');
		expect(levelWords({ pitch: -80, roll: null })).toBe('Pointing at the ground');
		expect(levelWords({ pitch: 80, roll: null })).toBe('Pointing at the sky');
	});

	it('level roll never returns -0', () => {
		for (const r of [0, -0, 90, -90, 180, -180]) expect(Object.is(levelRoll(r), -0)).toBe(false);
	});

	it('draws a counterclockwise-turned phone horizon turned clockwise', () => {
		const ccw = gravityFromBetaGamma(75, -90)!; // roll_deg +15
		expect(horizonScreenAngle(ccw, 0)).toBeCloseTo(15, 6); // CSS rotate(): clockwise
		expect(levelReferenceScreenAngle(ccw, 0)).toBe(0);
	});

	it('takes the page rotation off the horizon', () => {
		// Phone a quarter turn counterclockwise, 5° short of level.
		const g: Vec3 = [G * Math.sin((85 * Math.PI) / 180), G * Math.cos((85 * Math.PI) / 180), 0];
		// Page locked upright to the phone: the horizon runs down the screen.
		expect(horizonScreenAngle(g, 0)).toBeCloseTo(85, 6);
		expect(levelReferenceScreenAngle(g, 0)).toBe(90);
		// Page rotated with the phone (screen.orientation.angle 90): nearly flat.
		expect(horizonScreenAngle(g, 90)).toBeCloseTo(-5, 6);
		expect(levelReferenceScreenAngle(g, 90)).toBe(0);
	});
});

/**
 * The device pose while the web camera is shown: the one home for "which way is
 * down", beside deviceOrientationExif.ts, which answers "which way up is the
 * phone". It is a pose, not a heading, so it never enters bearingState
 * (docs/one-state.md, "The device pose is its own state").
 *
 * ONE writer, the sensor source below, started and stopped by CameraCapture
 * while the camera is shown. Three readers, none opening a sensor of its own:
 *
 * - the shutter, through stampInertial(): the samples of the last 300 ms,
 *   averaged into the `inertial` object the upload carries;
 * - the level indicator, through capturePose: a shorter display-only average of
 *   the same ring, published once per animation frame.
 * - CameraCapture, through that same average: the device's quarter turn written
 *   to deviceOrientationExif, shared by the capture icons and photo metadata.
 *
 * Sources, first that works:
 *
 * - GravitySensor({referenceFrame: 'device'}) on Chromium (Chrome and Samsung
 *   Internet on Android), which Chromium maps to Android's TYPE_GRAVITY, the
 *   sensor frontend2 stamps. Its reading is the stamp's vector as is. Where
 *   there is no hardware (desktop Chromium) it fails with an error event, and
 *   the next source takes over.
 * - deviceorientation's beta/gamma (iOS Safari, Firefox), converted per event to
 *   the up vector (gravityFromBetaGamma).
 *
 * Never accelerationIncludingGravity: it is the raw accelerometer, and reportedly
 * sign-inverted on iOS, which would flip pitch's sign while leaving the gated
 * absolute values looking fine. Desktop browsers have neither source, so their
 * photos stay unmeasured. Both sources are in DEVICE coordinates, which is what
 * the stamp needs whatever the page's rotation; only the indicator's drawing
 * takes the screen angle off.
 *
 * Maths in capturePoseMath.ts. Plan: docs/todo/web-capture-level-stamp.md.
 */

import { writable, type Readable } from 'svelte/store';
import {
	averageGravity,
	buildInertialStamp,
	gravityFromBetaGamma,
	isUsableGravity,
	DISPLAY_WINDOW_MS,
	RING_MS,
	type GravitySample,
	type GravitySource,
	type InertialStamp,
	type Vec3,
} from './capturePoseMath';

const LOG_PREFIX = '🢄[CapturePose]';

export interface PoseReading {
	gravity: Vec3;
	source: GravitySource;
}

const ring: GravitySample[] = [];
const pose = writable<PoseReading | null>(null);

/** The display average, null while nothing is measured. Read by the level
 * indicator; the stamp reads the ring itself, through stampInertial(). */
export const capturePose: Readable<PoseReading | null> = { subscribe: pose.subscribe };

let running = false;
let gravitySensor: GenericSensorLike | null = null;
let orientationListener: ((event: DeviceOrientationEvent) => void) | null = null;
let rafId: number | null = null;

interface GenericSensorLike extends EventTarget {
	readonly x?: number | null;
	readonly y?: number | null;
	readonly z?: number | null;
	start(): void;
	stop(): void;
}

function push(g: Vec3 | null, source: GravitySource): void {
	if (!isUsableGravity(g)) return;
	const t = performance.now();
	ring.push({ t, g, source });
	while (ring.length && t - ring[0].t > RING_MS) ring.shift();
}

function startGravitySensor(): boolean {
	const GravitySensor = (window as unknown as { GravitySensor?: new (options: object) => GenericSensorLike })
		.GravitySensor;
	if (typeof GravitySensor !== 'function') return false;
	try {
		const sensor = new GravitySensor({ referenceFrame: 'device', frequency: 60 });
		sensor.addEventListener('reading', () => {
			push([sensor.x ?? NaN, sensor.y ?? NaN, sensor.z ?? NaN], 'gravity-sensor');
		});
		sensor.addEventListener('error', (event) => {
			const error = (event as Event & { error?: DOMException }).error;
			console.warn(`${LOG_PREFIX} GravitySensor failed (${error?.name}: ${error?.message}), falling back to deviceorientation`);
			if (gravitySensor !== sensor) return;
			sensor.stop();
			gravitySensor = null;
			if (running) startDeviceOrientation();
		});
		sensor.start();
		gravitySensor = sensor;
		console.log(`${LOG_PREFIX} GravitySensor started`);
		return true;
	} catch (error) {
		// SecurityError (permissions policy), ReferenceError, …
		console.warn(`${LOG_PREFIX} GravitySensor unavailable:`, error);
		return false;
	}
}

function startDeviceOrientation(): void {
	if (orientationListener || !('ondeviceorientation' in window)) return;
	orientationListener = (event: DeviceOrientationEvent) => {
		push(gravityFromBetaGamma(event.beta, event.gamma), 'deviceorientation');
	};
	window.addEventListener('deviceorientation', orientationListener);
	console.log(`${LOG_PREFIX} listening to deviceorientation`);
}

function tick(): void {
	if (!running) return;
	const avg = averageGravity(ring, performance.now(), DISPLAY_WINDOW_MS);
	pose.set(avg ? { gravity: avg.gravity, source: avg.source } : null);
	rafId = requestAnimationFrame(tick);
}

/** Start sensing. Idempotent; CameraCapture calls it while the camera is shown. */
export function startCapturePose(): void {
	if (running || typeof window === 'undefined') return;
	running = true;
	if (!startGravitySensor()) startDeviceOrientation();
	rafId = requestAnimationFrame(tick);
}

/** Stop sensing and forget every sample, so nothing measured before can be stamped later. */
export function stopCapturePose(): void {
	if (!running) return;
	running = false;
	if (gravitySensor) {
		gravitySensor.stop();
		gravitySensor = null;
	}
	if (orientationListener) {
		window.removeEventListener('deviceorientation', orientationListener);
		orientationListener = null;
	}
	if (rafId !== null) {
		cancelAnimationFrame(rafId);
		rafId = null;
	}
	ring.length = 0;
	pose.set(null);
}

/**
 * The capture's `inertial` object, or null to send none: when no sample is
 * fresh, and for a camera facing the user. Call it before any await in the
 * shutter handler, so the window ends at the press.
 */
export function stampInertial(facing?: string | null, nowMs: number = performance.now()): InertialStamp | null {
	return buildInertialStamp(ring, nowMs, facing);
}

/**
 * Ask for the sensors, inside the click that opens the camera: iOS refuses
 * DeviceOrientationEvent.requestPermission() outside a user gesture, and Chrome
 * plans to make sensor permission Ask-by-default, so this runs everywhere. The
 * prompt call comes before any await, which keeps it inside the gesture. A
 * refusal only leaves photos unmeasured.
 */
export async function requestCapturePosePermission(): Promise<void> {
	if (typeof window === 'undefined') return;
	const DOE = (window as unknown as { DeviceOrientationEvent?: { requestPermission?: () => Promise<string> } })
		.DeviceOrientationEvent;
	const asked = typeof DOE?.requestPermission === 'function' ? DOE.requestPermission() : null;
	if ('GravitySensor' in window && navigator.permissions?.query) {
		try {
			// The Generic Sensor permission has no request call: starting the sensor
			// asks. This query reports what that will meet.
			const status = await navigator.permissions.query({ name: 'accelerometer' as PermissionName });
			console.log(`${LOG_PREFIX} accelerometer permission: ${status.state}`);
		} catch (error) {
			console.log(`${LOG_PREFIX} accelerometer permission cannot be queried:`, error);
		}
	}
	if (asked) {
		try {
			console.log(`${LOG_PREFIX} deviceorientation permission: ${await asked}`);
		} catch (error) {
			console.warn(`${LOG_PREFIX} deviceorientation permission request failed:`, error);
		}
	}
}

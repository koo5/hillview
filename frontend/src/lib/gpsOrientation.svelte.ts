import {writable, get} from 'svelte/store';
import {browser} from '$app/environment';
import {gpsLocation} from './location.svelte';
import {updateBearing, updateBearingByDiff} from './mapState';
import {isOnMapRoute} from './compass.svelte';
import {locationManager} from './locationManager';
import {HeadingFilter} from './utils/headingFilter';
import {getAngularDistance} from './utils/bearingUtils';
import {TAURI} from './tauri';
import {addPluginListener, invoke, type PluginListener} from '@tauri-apps/api/core';

// User preference - simple enabled/disabled
export const gpsOrientationEnabled = writable(false);

// Internal state for tracking GPS orientation functionality
export type GpsOrientationInternalState =
	| 'inactive'        // Not running
	| 'starting'        // Waiting for first GPS data
	| 'active'          // Successfully tracking GPS heading changes
	| 'error';          // Failed (no GPS heading available)

export const gpsOrientationInternalState = writable<GpsOrientationInternalState>('inactive');
export const gpsOrientationError = writable<string | null>(null);

// Camera-mount offset (degrees). Applied on top of travel direction in car
// mode: photo_bearing = travel + mountOffset. In Tauri, Kotlin owns the
// composition — this store reflects it for UI and is pushed down via
// set_mount_offset when adjusted.
export const carMountOffset = writable(0);

// Kalman filter: estimates heading from GPS position pairs instead of raw GPS heading
let headingFilter = new HeadingFilter();

// Track last filtered heading for differential updates
// Only diffs are applied to map bearing, preserving any user-set base angle
let lastGpsHeading: number | null = null;

// Flash signal for UI feedback when GPS bearing updates
export const gpsOrientationFlash = writable(false);
let gpsOrientationFlashTimer: ReturnType<typeof setTimeout> | null = null;

// Flag to prevent recursion when reverting user preference
let revertingUserPreference = false;

const doLog = false;

// Simple user-level API functions
export function enableGpsOrientation() {
	if (doLog) console.log('🚗 User enabled GPS orientation tracking');
	gpsOrientationEnabled.set(true);
}

export function disableGpsOrientation() {
	if (doLog) console.log('🚗 User disabled GPS orientation tracking');
	gpsOrientationEnabled.set(false);
}

// Adjust the camera-mount offset — the angle of the camera relative to the
// direction of travel. Caller is responsible for only invoking this in car
// mode (gps orientation enabled); the offset is meaningless otherwise.
export function adjustMountOffset(diff: number) {
	const next = ((get(carMountOffset) + diff) % 360 + 360) % 360;
	carMountOffset.set(next);
	// Immediate UI feedback; Kotlin reconciles on the next GPS tick.
	updateBearingByDiff(diff, 'gps-kalman');
	if (TAURI) {
		invoke('plugin:hillview|cmd', {
			command: 'set_mount_offset',
			params: {offset: next}
		}).catch(err => console.error('🚗 Failed to push mount offset to Kotlin:', err));
	}
}

// Stop GPS orientation tracking internally
async function stopGpsOrientationInternal() {
	if (doLog) console.log('🚗 Stopping GPS orientation tracking internal state');
	gpsOrientationInternalState.set('inactive');
	headingFilter.reset();
	lastGpsHeading = null;
	gpsOrientationError.set(null);
	if (TAURI) {
		invoke('plugin:hillview|cmd', {command: 'reset_heading_filter', params: {}}).catch(() => {});
	}
	await locationManager.releaseLocation('gps-orientation');
}

// State machine that manages GPS orientation tracking based on user preferences + route state
async function updateGpsOrientationState() {
	// Don't process updates if we're reverting user preference to avoid recursion
	if (revertingUserPreference) {
		return;
	}

	const userEnabled = get(gpsOrientationEnabled);
	const onMapRoute = get(isOnMapRoute);
	const currentInternalState = get(gpsOrientationInternalState);

	if (doLog) console.log('🚗🎛️ GPS orientation state update:', JSON.stringify(
		{userEnabled, onMapRoute, currentInternalState}));

	if (!userEnabled || !onMapRoute) {
		// User disabled or not on map route - stop internal tracking
		if (currentInternalState !== 'inactive') {
			await stopGpsOrientationInternal();
		}
	} else {
		// User enabled and on map route - should start internal tracking
		if (currentInternalState === 'inactive') {
			gpsOrientationInternalState.set('starting');
			gpsOrientationError.set(null);
			headingFilter.reset();
			lastGpsHeading = null;
			if (doLog) console.log('🚗 GPS orientation tracking starting, waiting for GPS data');

			// Push the current mount offset down so Kotlin composes correctly from the first tick.
			if (TAURI) {
				invoke('plugin:hillview|cmd', {
					command: 'set_mount_offset',
					params: {offset: get(carMountOffset)}
				}).catch(err => console.error('🚗 Failed to push initial mount offset:', err));
			}

			// Request location service
			try {
				await locationManager.requestLocation('gps-orientation');
				if (doLog) console.log('🚗 GPS orientation requested location service successfully');
			} catch (error) {
				console.error('🚗 GPS orientation failed to request location service:', error);
				gpsOrientationInternalState.set('error');
				gpsOrientationError.set('Failed to start location service');
			}
		}
	}
}

// Listener for Kotlin-emitted composed bearings (Tauri only).
let kalmanBearingListener: PluginListener | null = null;

async function ensureKalmanBearingListener() {
	if (!TAURI || kalmanBearingListener) return;
	try {
		kalmanBearingListener = await addPluginListener(
			'hillview',
			'gps-kalman-bearing',
			(data: {bearing: number; mount_offset: number; timestamp: number; source: string}) => {
				const internalState = get(gpsOrientationInternalState);
				if (internalState !== 'active' && internalState !== 'starting') return;
				if (internalState === 'starting') {
					gpsOrientationInternalState.set('active');
					gpsOrientationError.set(null);
				}
				updateBearing(data.bearing, 'gps-kalman');
				gpsOrientationFlash.set(true);
				if (gpsOrientationFlashTimer) clearTimeout(gpsOrientationFlashTimer);
				gpsOrientationFlashTimer = setTimeout(() => gpsOrientationFlash.set(false), 100);
			}
		);
	} catch (e) {
		console.error('🚗 Failed to set up gps-kalman-bearing listener:', e);
	}
}

if (browser) {

// Subscribe to state changes
	gpsOrientationEnabled.subscribe(updateGpsOrientationState);
	isOnMapRoute.subscribe(updateGpsOrientationState);

	if (TAURI) {
		// Kotlin owns the filter — listen for composed bearings instead.
		ensureKalmanBearingListener();
	}

// Subscribe to GPS location updates for orientation tracking
	gpsLocation.subscribe((position) => {
		if (TAURI) return; // Kotlin-side filter handles this path.
		const internalState = get(gpsOrientationInternalState);

		if (doLog) console.log('🚗 GPS orientation received location update:', JSON.stringify(position));

		// Only process if internal tracking is active or starting
		if (internalState !== 'active' && internalState !== 'starting') {
			return;
		}

		if (!position) {
			return;
		}

		// Feed position to Kalman filter — it handles speed gating and
		// reference point management internally
		const filteredHeading = headingFilter.update({
			lat: position.coords.latitude,
			lng: position.coords.longitude,
			speed: position.coords.speed ?? null,
			timestamp: position.timestamp
		});

		if (filteredHeading === null) {
			if (doLog) console.log('🚗 Kalman filter: position rejected (low speed or insufficient distance)');
			return;
		}

		// Transition from starting to active on first filtered heading
		if (internalState === 'starting') {
			gpsOrientationInternalState.set('active');
			gpsOrientationError.set(null);
			lastGpsHeading = filteredHeading;
			if (doLog) console.log('🚗 GPS orientation: Kalman filter locked heading at', filteredHeading.toFixed(1), '°');
			return;
		}

		// Apply differential updates when active
		if (internalState === 'active' && lastGpsHeading !== null) {
			const headingDiff = getAngularDistance(lastGpsHeading, filteredHeading);

			if (Math.abs(headingDiff) > 1) { // Ignore tiny changes to reduce noise
				updateBearingByDiff(headingDiff, 'gps-kalman');
				if (doLog) console.log(`🚗 GPS orientation: Kalman heading diff ${headingDiff.toFixed(1)}°, estimated heading ${filteredHeading.toFixed(1)}°`);

				// Flash the compass button
				gpsOrientationFlash.set(true);
				if (gpsOrientationFlashTimer) clearTimeout(gpsOrientationFlashTimer);
				gpsOrientationFlashTimer = setTimeout(() => gpsOrientationFlash.set(false), 100);
			}

			lastGpsHeading = filteredHeading;
		}
	});

// Reset tracking when internal state changes to inactive
	gpsOrientationInternalState.subscribe(state => {
		if (state === 'inactive') {
			headingFilter.reset();
			lastGpsHeading = null;
		}
	});

}

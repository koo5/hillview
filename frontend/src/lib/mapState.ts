import {writable, derived, get} from 'svelte/store';
import {LatLng} from 'leaflet';
import {
	staggeredLocalStorageSharedStore,
	localStorageReadOnceSharedStore,
	localStorageSharedStore
} from './svelte-shared-store';
import type {PhotoData} from './types/photoTypes';
import {AngularRangeCuller, sortPhotosByBearing} from './AngularRangeCuller';
import {normalizeBearing} from './utils/bearingUtils';

const angularRangeCuller = new AngularRangeCuller();

export interface Bounds {
	top_left: LatLng;
	bottom_right: LatLng;
}

export interface SpatialState {
	center: LatLng;
	zoom: number;
	bounds: Bounds | null;
	range: number;
	source: 'gps' | 'map';
}

export interface BearingState {
	bearing: number;
	source: string;
	photoUid?: string;
	accuracy?: number | null;
}

// Bearing mode for controlling automatic bearing source
export type BearingMode = 'car' | 'walking';

// Spatial state - triggers photo filtering in worker
export const spatialState = localStorageReadOnceSharedStore<SpatialState>('spatialState', {
	center: new LatLng(50.114429599683604, 14.523528814315798),
	zoom: 20,
	bounds: null,
	range: 1000,
	source: 'map'
});


// Visual state - only affects rendering, optimized with debounced writes
export const bearingState = staggeredLocalStorageSharedStore<BearingState>('bearingState', {
	bearing: 230,
	source: 'map',
	accuracy: null
}, 500);

// Bearing mode state - controls automatic bearing source (car = GPS, walking = compass)
export const bearingMode = localStorageSharedStore<BearingMode>('bearingMode', 'walking');

// Photos filtered by spatial criteria (from worker)
export const photosInArea = writable<PhotoData[]>([]);

// Photos in range for navigation (from worker)
export const photosInRange = writable<PhotoData[]>([]);

photosInRange.subscribe(photos => {
	//console.log(`Spatial: photosInRange updated with ${photos.length} photos`);
});

bearingState.subscribe(v => {
	//console.log(`bearingState updated to ${JSON.stringify(v)}`);
});

// Recalculate photosInRange when map moves (spatialState changes)
let oldPhotosInRangeSpatialState: SpatialState | null = null;
spatialState.subscribe(spatial => {
	if (oldPhotosInRangeSpatialState &&
		oldPhotosInRangeSpatialState.center.lat === spatial.center.lat &&
		oldPhotosInRangeSpatialState.center.lng === spatial.center.lng &&
		oldPhotosInRangeSpatialState.range === spatial.range) {
		// No significant change
		return;
	}
	oldPhotosInRangeSpatialState = spatial;

	const photos = get(photosInArea);
	const center = {lat: spatial.center.lat, lng: spatial.center.lng};
	const inRange = angularRangeCuller.cullPhotosInRange(photos, center, spatial.range, 300);

	// Sort by bearing for consistent navigation order
	sortPhotosByBearing(inRange);
	//console.log(`🢄spatialState: photosInRange recalculated to ${inRange.length} photos within range ${spatial.range}m`);
	photosInRange.set(inRange);
});

export const photoInFront = writable<PhotoData | null>(null);

// Navigation photos (front, left, right) - derived from bearing-sorted photosInRange (within spatialState.range)


/* fixme:
we have to make photo id a part of bearingState. (First, we have to ensure cross-source unique photo ids.)
Then, photosInRange should already be sorted by bearing and id here, and then we can maybe make this work, where bearing takes precedence, but id is a tiebreaker.
*/

export const newPhotoInFront = derived(
	[photosInRange, bearingState],
	([photos, visual]) => {
		if (photos.length === 0) {
			//console.log('🢄Navigation: No photos available for photoInFront');
			return null;
		}

		//console.log(`🢄Navigation: Calculating photoInFront from ${JSON.stringify(photos.map(p => ({uid: p.uid, bearing: p.bearing})))} with current bearing ${visual.bearing} and photoUid ${visual.photoUid}`);

		// If a specific photo is selected in bearingState, and bearing matches, use that photo
		if (visual.photoUid) {
			const selectedPhoto = photos.find(p => p.uid === visual.photoUid);
			if (selectedPhoto && calculateAbsBearingDiff(selectedPhoto.bearing, visual.bearing) === 0) {
				console.log(`🢄Navigation: photoInFront ${selectedPhoto.uid} selected by photoUid from bearingState`);
				return selectedPhoto;
			}
		}


		// Find photo closest to current bearing (using uid as tiebreaker for stable sorting)
		const currentBearing = visual.bearing;
		let closestIndex = 0;
		let smallestDiff = calculateAbsBearingDiff(photos[0].bearing, currentBearing);

		for (let i = 1; i < photos.length; i++) {
			const diff = calculateAbsBearingDiff(photos[i].bearing, currentBearing);
			if (diff < smallestDiff || (diff === smallestDiff && photos[i].uid < photos[closestIndex].uid)) {
				smallestDiff = diff;
				closestIndex = i;
			}
		}

		const p = photos[closestIndex];

		console.log(`🢄Navigation: photoInFront ${p.uid} selected from ${photos.length} photos in range by bearing proximity`);
		return p;
	}
);

newPhotoInFront.subscribe(photo => {
	if (photo != get(photoInFront)) {
		photoInFront.set(photo);
	}
});

export const photoToLeft = derived(
	[photosInRange, photoInFront],
	([photos, front]) => {
		if (photos.length === 0) return null;
		if (!front) return null;
		if (photos.length === 1) return null; // Only one photo, no left/right
		const frontIndex = photos.findIndex(p => p.uid === front.uid);
		if (frontIndex === -1) return null; // Front photo not in range anymore
		const leftIndex = (frontIndex - 1 + photos.length) % photos.length;
		const bestPhoto = photos[leftIndex];
		console.log(`🢄Navigation: photoToLeft is ${bestPhoto ? bestPhoto.uid : 'null'}`);
		return bestPhoto;
	}
);

export const photoToRight = derived(
	[photosInRange, photoInFront],
	([photos, front]) => {
		if (photos.length === 0) return null;
		if (!front) return null;
		if (photos.length === 1) return null; // Only one photo, no left
		const frontIndex = photos.findIndex(p => p.uid === front.uid);
		if (frontIndex === -1) return null; // Front photo not in range anymore
		const rightIndex = (frontIndex + 1) % photos.length;
		const bestPhoto = photos[rightIndex];
		console.log(`🢄Navigation: photoToRight is ${bestPhoto ? bestPhoto.uid : 'null'}`);
		return bestPhoto;
	}
);

// Combined photos for rendering (includes placeholders)
// Only recalculates when photo list changes, not on bearing changes
export const visiblePhotos = derived(
	[photosInArea],
	([photos]) => {
		const currentBearing = get(bearingState).bearing;
		return photos.map(photo => ({
			...photo,
			abs_bearing_diff: calculateAbsBearingDiff(photo.bearing, currentBearing),
			bearing_color: getBearingColor(calculateAbsBearingDiff(photo.bearing, currentBearing))
		}));
	}
);

// Helper functions for bearing calculations
function calculateAbsBearingDiff(bearing1: number, bearing2: number): number {
	const diff = Math.abs(bearing1 - bearing2);
	return Math.min(diff, 360 - diff);
}

function getBearingColor(absBearingDiff: number): string {
	if (absBearingDiff === null || absBearingDiff === undefined) return '#9E9E9E';
	return `hsl(${Math.round(100 - absBearingDiff / 2)}, 100%, 70%)`;
}

// Update functions with selective reactivity
export function updateSpatialState(updates: Partial<SpatialState>, source: 'gps' | 'map' = 'map') {
	spatialState.update(state => ({...state, ...updates, source}));
}

export function updateBearing(bearing: number, source: string = 'map', photoUid?: string, accuracy?: number | null) {
	bearingState.update(state => ({...state, bearing, source, photoUid, accuracy}));
}

export function updateBearingByDiff(diff: number) {
	const current = get(bearingState);
	const newBearing = normalizeBearing(current.bearing + diff);
	updateBearing(newBearing);
}

export function updateBearingWithPhoto(photo: PhotoData, source: string = 'photo_navigation') {
	updateBearing(photo.bearing, source, photo.uid);
}

// Calculate range from map center and bounds
export function calculateRange(center: LatLng, bounds: Bounds): number {
	if (!bounds) return 1000;

	// Calculate distance from center to edge of bounds
	const cornerDistance = center.distanceTo(bounds.top_left);
	const sideDistance = center.distanceTo(new LatLng(center.lat, bounds.bottom_right.lng));

	return Math.max(cornerDistance, sideDistance);
}

// Update bounds and recalculate range
export function updateBounds(bounds: Bounds) {
	const current = get(spatialState);
	const range = calculateRange(current.center, bounds);

	updateSpatialState({
		bounds,
		range
	});
}

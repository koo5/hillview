import { writable, derived, get } from 'svelte/store';
import { LatLng } from 'leaflet';
import {
    staggeredLocalStorageSharedStore,
    localStorageReadOnceSharedStore,
    localStorageSharedStore
} from './svelte-shared-store';
import type { PhotoData } from './types/photoTypes';
import {AngularRangeCuller, sortPhotosByBearing} from './AngularRangeCuller';

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
}

export interface BearingState {
  bearing: number;
}

// Bearing mode for controlling automatic bearing source
export type BearingMode = 'car' | 'walking';

// Spatial state - triggers photo filtering in worker
export const spatialState = localStorageReadOnceSharedStore<SpatialState>('spatialState', {
  center: new LatLng(50.114429599683604, 14.523528814315798),
  zoom: 20,
  bounds: null,
  range: 1000
});


// Visual state - only affects rendering, optimized with debounced writes
export const bearingState = staggeredLocalStorageSharedStore<BearingState>('bearingState', {
  bearing: 230
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
spatialState.subscribe(spatial => {
    const photos = get(photosInArea);
    const center = { lat: spatial.center.lat, lng: spatial.center.lng };
    const inRange = angularRangeCuller.cullPhotosInRange(photos, center, spatial.range, 300);

    // Sort by bearing for consistent navigation order
    sortPhotosByBearing(inRange);
	console.log(`spatialState: photosInRange recalculated to ${inRange.length} photos within range ${spatial.range}m`);
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
      console.log('🢄Navigation: No photos available for photoInFront');
      return null;
    }

	console.log(`🢄Navigation: Calculating photoInFront from ${JSON.stringify(photos.map(p => ({id: p.id, bearing: p.bearing})))} with current bearing ${visual.bearing}`);

    // Find photo closest to current bearing
    const currentBearing = visual.bearing;
    let closestIndex = 0;
    let smallestDiff = calculateAbsBearingDiff(photos[0].bearing, currentBearing);

    for (let i = 1; i < photos.length; i++) {
      const diff = calculateAbsBearingDiff(photos[i].bearing, currentBearing);
      if (diff < smallestDiff) {
        smallestDiff = diff;
        closestIndex = i;
      }
    }

	const p = photos[closestIndex];

    console.log(`Navigation: (fixme) photoIFront ${p.id} selected from ${photos.length} photos in range`);
    return p;
  }
);

newPhotoInFront.subscribe(photo => {
	if (photo != get(photoInFront)) {
		photoInFront.set(photo);
	}
});

export const photoToLeft = derived(
  [photosInRange, bearingState],
  ([photos, visual]) => {
    if (photos.length === 0) return null;

    // Sort photos by bearing for proper navigation
    const sortedPhotos = [...photos].sort((a, b) => a.bearing - b.bearing);

    // Find the next photo counter-clockwise from current bearing
    const currentBearing = visual.bearing;
    let bestPhoto = null;
    let bestDiff = Infinity;

    for (const photo of sortedPhotos) {
      // Calculate counter-clockwise difference
      let diff = currentBearing - photo.bearing;
      if (diff <= 0) diff += 360; // Handle wraparound

      if (diff < bestDiff) {
        bestDiff = diff;
        bestPhoto = photo;
      }
    }

    return bestPhoto;
  }
);

export const photoToRight = derived(
  [photosInRange, bearingState],
  ([photos, visual]) => {
    if (photos.length === 0) return null;

    // Sort photos by bearing for proper navigation
    const sortedPhotos = [...photos].sort((a, b) => a.bearing - b.bearing);

    // Find the next photo clockwise from current bearing
    const currentBearing = visual.bearing;
    let bestPhoto = null;
    let bestDiff = Infinity;

    for (const photo of sortedPhotos) {
      // Calculate clockwise difference
      let diff = photo.bearing - currentBearing;
      if (diff <= 0) diff += 360; // Handle wraparound

      if (diff < bestDiff) {
        bestDiff = diff;
        bestPhoto = photo;
      }
    }

    return bestPhoto;
  }
);

// Combined photos for rendering (includes placeholders)
// Only recalculates when photo list changes, not on bearing changes
export const visiblePhotos = derived(
  [photosInArea ],
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
export function updateSpatialState(updates: Partial<SpatialState>) {
  spatialState.update(state => ({ ...state, ...updates }));
}

export function updateBearing(bearing: number) {
  bearingState.update(state => ({ ...state, bearing }));
}

export function updateBearingByDiff(diff: number) {
  const current = get(bearingState);
  const newBearing = (current.bearing + diff + 360) % 360;
  updateBearing(newBearing);
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

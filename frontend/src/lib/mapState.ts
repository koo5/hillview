import { writable, derived, get } from 'svelte/store';
import { LatLng } from 'leaflet';
import { staggeredLocalStorageSharedStore, localStorageReadOnceSharedStore } from './svelte-shared-store';
import type { PhotoData } from './types/photoTypes';

// Bounds interface
export interface Bounds {
  top_left: LatLng;
  bottom_right: LatLng;
}

// Separate spatial state (triggers worker updates)
export interface SpatialState {
  center: LatLng;
  zoom: number;
  bounds: Bounds | null;
  range: number;
}

// Visual state (main thread only updates)
export interface VisualState {
  bearing: number;
}

// Source configuration
export interface SourceConfig {
  id: string;
  enabled: boolean;
}

// Spatial state - triggers photo filtering in worker
export const spatialState = localStorageReadOnceSharedStore<SpatialState>('spatialState', {
  center: new LatLng(50.06173640462974, 14.514600411057472),
  zoom: 20,
  bounds: null,
  range: 1000
});

// Visual state - only affects rendering, optimized with debounced writes
export const visualState = staggeredLocalStorageSharedStore<VisualState>('visualState', {
  bearing: 0
}, 250); // 250ms debounce for smooth bearing updates

// Source configuration - triggers photo filtering
export const sources = writable<SourceConfig[]>([
  { id: 'hillview', enabled: true },
  { id: 'mapillary', enabled: true },
  { id: 'device', enabled: true }
]);

// Photos filtered by spatial criteria (from worker)
export const photosInArea = writable<PhotoData[]>([]);

// Photos in range for navigation (from worker)
export const photosInRange = writable<PhotoData[]>([]);

// Navigation photos (front, left, right)
export const photoInFront = writable<PhotoData | null>(null);
export const photoToLeft = writable<PhotoData | null>(null);
export const photoToRight = writable<PhotoData | null>(null);

// Combined photos for rendering (includes placeholders)
export const visiblePhotos = derived(
  [photosInArea, visualState],
  ([photos, visual]) => {
    // Only add bearing diff colors - no spatial filtering
    return photos.map(photo => ({
      ...photo,
      abs_bearing_diff: calculateAbsBearingDiff(photo.bearing, visual.bearing),
      bearing_color: getBearingColor(calculateAbsBearingDiff(photo.bearing, visual.bearing))
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

export function updateVisualState(updates: Partial<VisualState>) {
  visualState.update(state => ({ ...state, ...updates }));
}

export function updateBearing(bearing: number) {
  visualState.update(state => ({ ...state, bearing }));
}

export function updateBearingDiff(diff: number) {
  const current = get(visualState);
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

// Legacy compatibility exports (for gradual migration)
export { spatialState as pos };
export { spatialState as pos2 };
export { visualState as bearing };
export { updateSpatialState as update_pos };
export { updateSpatialState as update_pos2 };
/**
 * A person moving the observer by hand: the map's pan, the 3D world's flight (recon ea07). One rule for both, as
 * userTurn is for the bearing (docs/one-state.md: the automatic producer is switched off first). Without it the next
 * GPS fix puts the point back: the map would jump home after a pan, and flight could not leave the GPS point.
 */
import { get } from 'svelte/store';
import { locationTracking, setBackgroundLocationTracking, setLocationTracking } from '$lib/location.svelte';
import { setElectedLocationSource, updateSpatialState } from '$lib/mapState';

/**
 * ACTIVE → BACKGROUND while GPS follows; from OFF or BACKGROUND it changes nothing. Deliberately not
 * stopLocationTracking(): the GPS subscription stays up so pulses continue and fixes keep logging -- under their
 * own name now, simply no longer the elected source. The map stops following because locationTracking is false
 * (Map.svelte's handleGpsLocationUpdate early-returns). Nothing needs awaiting: the manual 'map' row
 * updateSpatialState writes carries the election itself, so it cannot be stamped with the era it ends.
 */
export function enterBackgroundTracking() {
	if (!get(locationTracking)) return;
	setLocationTracking(false);
	setBackgroundLocationTracking(true);
	setElectedLocationSource('manual');
}

/** the hand put the observer at `center` (the map's own pan writes its full state itself; it calls enterBackgroundTracking) */
export function userMove(center: { lat: number; lng: number }) {
	enterBackgroundTracking();
	return updateSpatialState({ center }, 'map');
}

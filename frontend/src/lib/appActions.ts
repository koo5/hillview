import { get } from 'svelte/store';
import { goto } from '$app/navigation';
import { app, onAppActivityChange } from '$lib/data.svelte';
import { spatialState, updateSpatialState } from '$lib/mapState';
import { track } from '$lib/analytics';

// Switch to capture mode and navigate to the map. For links outside the map page.
export function openCamera() {
	if (get(app).activity !== 'capture') {
		toggleCamera();
	}
	goto('/');
}

export function toggleCamera() {
	const newActivity = get(app).activity === 'capture' ? 'view' : 'capture';
	track(newActivity === 'capture' ? 'activityCamera' : 'activityView');
	onAppActivityChange(newActivity);
	if (get(spatialState).zoom < 17 && newActivity === 'capture') {
		updateSpatialState({
			...get(spatialState),
			zoom: 17
		});
	}
	app.update(a => ({
		...a,
		activity: newActivity
	}));
}

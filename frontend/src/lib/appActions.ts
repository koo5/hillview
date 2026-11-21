import { get } from 'svelte/store';
import { goto } from '$app/navigation';
import { app, onAppActivityChange } from '$lib/data.svelte';
import { spatialState, updateSpatialState } from '$lib/mapState';
import { track } from '$lib/analytics';
import { TAURI } from '$lib/tauri';
import { requestCapturePosePermission } from '$lib/capturePose';

// Switch to capture mode and navigate to the map. For links outside the map page.
export function openCamera() {
	if (get(app).activity !== 'capture') {
		toggleCamera();
	}
	goto('/');
}

export function toggleCamera() {
	const newActivity = get(app).activity === 'capture' ? 'view' : 'capture';
	// Inside the click, before anything awaits: iOS only shows the motion prompt
	// from a user gesture. The camera's level stamp needs it (capturePose.ts).
	if (newActivity === 'capture' && !TAURI) {
		requestCapturePosePermission();
	}
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

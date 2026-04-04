import { get } from 'svelte/store';
import { app, onAppActivityChange } from '$lib/data.svelte';
import { spatialState, updateSpatialState } from '$lib/mapState';

export function toggleCamera() {
	const newActivity = get(app).activity === 'capture' ? 'view' : 'capture';
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

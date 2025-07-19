import {get} from "svelte/store";
import {updateCaptureLocation} from "$lib/captureLocation";
import {triggerPhotosBearingDiffRecalculator} from "$lib/photosBearingDiffRecalculator";
import {app, pos} from "$lib/data.svelte";

export let bearing = staggeredLocalStorageSharedStore('bearing', 0);

let oldBearing;

export function updateBearing(b: number) {
    b = (b + 360) % 360;
    if (oldBearing === b) {
        return;
    }
    bearing.set(b);

    // Update capture location when bearing changes
    const p = get(pos);
    if (get(app).activity === 'capture') {
        updateCaptureLocation(p.center.lat, p.center.lng, b);
    }
    triggerPhotosBearingDiffRecalculator();
};

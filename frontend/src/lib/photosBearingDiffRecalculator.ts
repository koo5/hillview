
/* fixme - finish this file. this will recalculate the bearing difference for photos in range on the UI thread in a rate-limited manner.

will be triggered when photos_in_range changes, or when the current bearing changes.

*/

const minInterval = 100; // Minimum interval in milliseconds

import { photos_in_range } from '$lib/stores/photos_in_range';
import { app } from './data.svelte';

let timer;
let last_recalculation: number | null = null;

export function triggerPhotosBearingDiffRecalculator() {
    const now = Date.now();
    if (last_recalculation && now - last_recalculation < minInterval) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(triggerPhotosBearingDiffRecalculator, minInterval - (now - last_recalculation));
        return;
    }

    last_recalculation = now;
    let bearing = get(app).current_bearing;
    let photos = get(photos_in_range);
    recalculatePhotosBearingDiff(photos, bearing);
    photos_in_range.set(photos);
}

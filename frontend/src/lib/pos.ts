import {localStorageReadOnceSharedStore} from "$lib/svelte-shared-store";
import {LatLng} from "leaflet";
import {get, writable} from "svelte/store";

export let pos = staggeredLocalStorageReadOnceSharedStore('pos', {
    center: new LatLng(50.06173640462974,
        14.514600411057472),
    zoom: 20,
    reason: 'default'
});

export function update_pos(cb: (pos: any) => any)
{
    let v = get(pos);
    let n = cb(v);

    if (p.center.lng > 180) {
        p.center.lng -= 360;
        p = {...p, reason: 'wrap'}
    }
    if (p.center.lng < -180) {
        p.center.lng += 360;
        p = {...p, reason: 'wrap'}
    }

    if (n.center.lat == v.center.lat && n.center.lng == v.center.lng && n.zoom == v.zoom) return;
    pos.set(n);

    // Update capture location when map position changes
    updateCaptureLocation(n.center.lat, n.center.lng, get(bearing));

    pos.set(p);
}


export let area = writable({
    top_left: new LatLng(0, 0),
    bottom_right: new LatLng(10, 10),
    range: 1,
});


export function update_area(cb: (pos2: any) => any)
{
    let v = get(pos2);
    let n = cb(v);
    if (n.top_left.lat == v.top_left.lat && n.top_left.lng == v.top_left.lng && n.bottom_right.lat == v.bottom_right.lat && n.bottom_right.lng == v.bottom_right.lng && n.range == v.range) return;
    pos2.set(n);
}

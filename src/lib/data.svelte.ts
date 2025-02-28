import {type Photo} from "./types.ts";
import {Coordinate} from "tsgeo/Coordinate";
import {Vincenty} from "tsgeo/Distance/Vincenty";
import Angles from 'angles';
//import {DMS} from "tsgeo/Formatter/Coordinate/DMS";
import {space_db} from "./debug_server.js";
import {LatLng} from 'leaflet';
import {get, writable} from "svelte/store";
import { localStorageSharedStore } from './svelte-shared-store.ts';

export const geoPicsUrl = import.meta.env.VITE_REACT_APP_GEO_PICS_URL;

let calculator = new Vincenty();

export let app = writable({
    loading: true,
    error: null,
    debug: false,
})

export let pos = localStorageSharedStore('pos', {
    center: new LatLng(50.06173640462974,
        14.514600411057472),
    zoom: 20
});

export let pos2 = writable({
    top_left: new LatLng(0, 0),
    bottom_right: new LatLng(10, 10),
    range: 1,
});

export let bearing = localStorageSharedStore('bearing', 0);

export let photos = writable([]);
export let photos_in_area = writable([]);
export let photos_in_range = writable([]);

export let photo_in_front = writable(null);
export let photos_to_left = writable([]);
export let photos_to_right = writable([]);
export let photo_to_left = writable(null);
export let photo_to_right = writable(null);

function dist(coord1, coord2) {
    return calculator.getDistance(new Coordinate(coord1.lat, coord1.lng), new Coordinate(coord2.lat, coord2.lng));
}

bearing.subscribe(b => {
    let b2 = (b + 360) % 360;
    if (b2 !== b) {
        bearing.set(b2);
    }
});

async function share_state() {
    let p = get(pos);
    let p2 = get(pos2);
    await space_db.transaction('rw', 'state', async () => {
        await space_db.state.clear();
        let state = {
            ts: Date.now(),
            center: p.center,
            zoom: p.zoom,
            top_left: p2.top_left,
            bottom_right: p2.bottom_right,
            range: p2.range,
            bearing: get(bearing)
        }
        //console.log('Saving state:', state);
        space_db.state.add(state);
    });
};

pos.subscribe(share_state);
bearing.subscribe(share_state);


function filter_photos_by_area() {
    let p = get(pos);
    let p2 = get(pos2);
    let b = get(bearing);
    let ph = get(photos);
    //console.log('photos:', ph);
    let res = ph.filter(photo => {
        //console.log('photo:', photo);
        //console.log('map_state.top_left:', p.top_left, 'map_state.bottom_right:', p.bottom_right);
        let yes = photo.coord.lat < p2.top_left.lat && photo.coord.lat > p2.bottom_right.lat &&
            photo.coord.lng > p2.top_left.lng && photo.coord.lng < p2.bottom_right.lng;
        //console.log('yes:', yes);
        return yes;
    });
    for (let photo of res) {
        photo.abs_bearing_diff = Math.abs(Angles.diff(b, photo.bearing));
        photo.range_distance = null;
    }
    console.log('Photos in area:', res.length);
    photos_in_area.set(res);
};

pos.subscribe(filter_photos_by_area);
bearing.subscribe(filter_photos_by_area);
photos.subscribe(filter_photos_by_area);

function filter_photos_in_range() {
    let p = get(pos);
    let p2 = get(pos2);
    let ph = get(photos_in_area);
    let res = ph.filter(photo => {
        photo.range_distance = dist(photo.coord, p.center);
        console.log('photo.range_distance:', photo.range_distance, 'p2.range:', p2.range);
        if (photo.range_distance > p2.range) {
            photo.range_distance = null;
        }
        return photo.range_distance !== null;
    });
    photos_in_range.set(res);
};

photos_in_area.subscribe(filter_photos_in_range);

function update_view() {
    let b = get(bearing);
    let ph = get(photos_in_range);
    if (ph.length === 0) {
        photo_in_front.set(null);
        photo_to_left.set(null);
        photo_to_right.set(null);
        return;
    }
    ph.map(photo => {
        photo.angular_distance_abs = Math.abs(Angles.distance(b, photo.bearing));
    });
    let phs = ph.slice().sort((a, b) => a.angular_distance_abs - b.angular_distance_abs);
    let fr = phs[0];
    let idx = ph.indexOf(fr);
    let phl = ph[(idx - 1 + ph.length) % ph.length];
    let phr = ph[(idx + 1) % ph.length];
    photo_to_left.set(phl);
    photo_to_right.set(phr);
    photo_in_front.set(fr);
}

bearing.subscribe(update_view);
photos_in_range.subscribe(update_view);

export function turn_to_photo_to(dir) {
    if (dir === 'left') {
        let phl = get(photo_to_left);
        console.log('phl:', phl);
        if (phl) {
            bearing.set(phl.bearing);
        }
    } else if (dir === 'right') {
        let phr = get(photo_to_right);
        console.log('phr:', phr);
        if (phr) {
            bearing.set(phr.bearing);
        }
    }
}

export function update_bearing(diff) {
    let b = get(bearing);
    bearing.set(b + diff);
}
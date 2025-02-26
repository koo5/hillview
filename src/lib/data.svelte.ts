import {type Photo} from "./types.ts";
import {Coordinate} from "tsgeo/Coordinate";
import {Vincenty} from "tsgeo/Distance/Vincenty";
import Angles from 'angles';
//import {DMS} from "tsgeo/Formatter/Coordinate/DMS";
import {space_db} from "./debug_server.js";
import {LatLng} from 'leaflet';
import {get, writable} from "svelte/store";


export const geoPicsUrl = import.meta.env.VITE_REACT_APP_GEO_PICS_URL;

let calculator = new Vincenty();

export let app = writable({
    loading: true,
    error: null
})

export let pos = writable({
    center: new LatLng(50.033989, 14.539032),
    zoom: 12,
    top_left: new LatLng(0, 0),
    bottom_right: new LatLng(10, 10),
    range: 1,
});

export let bearing = writable(0);

export let photos = writable([]);
export let photos_in_area = writable([]);
export let photos_in_range = writable([]);

export let photo_in_front = writable(null);
export let photos_to_left = writable([]);
export let photos_to_right = writable([]);
export let photo_to_left = writable(null);
export let photo_to_right = writable(null);

function dist(coord1, coord2) {
    return calculator.getDistance(new Coordinate(coord1[0], coord1[1]), new Coordinate(coord2[0], coord2[1]));
}

bearing.subscribe(b => {
    let b2 = (b + 360) % 360;
    if (b2 !== b) {
        bearing.set(b2);
    }
});

async function share_state() {
    let p = get(pos);
    await space_db.transaction('rw', 'state', async () => {
        await space_db.state.clear();
        let state = {
            ts: Date.now(),
            center: p.center,
            zoom: p.zoom,
            top_left: p.top_left,
            bottom_right: p.bottom_right,
            range: p.range,
            bearing: get(bearing)
        }
        console.log('Saving state:', state);
        space_db.state.add(state);
    });
};

pos.subscribe(share_state);
bearing.subscribe(share_state);


function filter_photos_by_area() {
    let p = get(pos);
    let b = get(bearing);
    let ph = get(photos);
    console.log('photos:', ph);
    let res = ph.filter(photo => {
        console.log('photo:', photo);
        console.log('map_state.top_left:', p.top_left, 'map_state.bottom_right:', p.bottom_right);
        let yes = photo.coord.lat < p.top_left.lat && photo.coord.lat > p.bottom_right.lat &&
            photo.coord.lng > p.top_left.lng && photo.coord.lng < p.bottom_right.lng;
        //console.log('yes:', yes);
        return yes;
    });
    for (let photo of res) {
        photo.abs_bearing_diff = Math.abs(Angles.diff(b, photo.bearing));
        photo.range_distance = null;
    }
    console.log('Photos in area:', res);
    photos_in_area.set(res);
};

pos.subscribe(filter_photos_by_area);
bearing.subscribe(filter_photos_by_area);
photos.subscribe(filter_photos_by_area);

function filter_photos_in_range() {
    let p = get(pos);
    let ph = get(photos_in_area);
    let res = ph.filter(photo => {
        photo.range_distance = dist(photo.coord, p.center);
        if (photo.range_distance > p.range) {
            photo.range_distance = null;
        }
        return photo.range_distance !== null;
    });
    photos_in_range.set(res);
};

photos_in_area.subscribe(filter_photos_in_range);

function update_photo_in_front() {
    let b = get(bearing);
    let ph = get(photos_in_range);
    ph.map(photo => {photo.diff = undefined});
    let phf = ph.reduce((prev, current) => {
        current.diff = Math.abs(Angles.diff(b, current.bearing));
        if (!prev || prev.diff === undefined) return current;
        if (prev.diff > current.diff) {
            return current;
        }
        return prev;
    }, null);
    photo_in_front.set(phf);
    let phsl = ph.filter(photo => photo !== phf && Angles.shortestDirection(b, photo.bearing) > 0);
    photos_to_left.set(phsl);
    let phsr = ph.filter(photo => photo !== phf && Angles.shortestDirection(b, photo.bearing) < 0);
    photos_to_right.set(phsr);
    photo_to_left.set(get_photo_to_left(b, phsl, phsr));
    photo_to_right.set(get_photo_to_right(b, phsl, phsr));
};

function get_photo_to_left(b, phsl, phsr) {
    let result = phsl.reduce((prev, current) => {
        if (!prev) return current;
        current.diff = Math.abs(Angles.diff(b, current.bearing));
        if (prev.diff > current.diff) {
            return current;
        }
        return prev;
    }, null);
    if (!result) {
        // if no photo to the left, then get the "furthest away (along the circle)" photo on the right
        result = phsr.reduce((prev, current) => {
            if (!prev) return current;
            if (prev.bearing < current.bearing) {
                return current;
            }
            return prev;
        }, null);
    }
    return result;
};

function get_photo_to_right(b, phsl, phsr) {
    // what is the next closest photo going right
    let result = phsr.reduce((prev, current) => {
        if (!prev) return current;
        current.diff = Math.abs(Angles.diff(b, current.bearing));
        if (prev.diff > current.diff) {
            return current;
        }
        return prev;
    }, null);
    if (!result) {
        // if no photo to the right, then get the "furthest away (along the circle)" photo on the left
        result = phsl.reduce((prev, current) => {
            if (!prev) return current;
            if (prev.bearing > current.bearing) {
                return current;
            }
            return prev;
        }, null);
    }
    return result;
};

bearing.subscribe(update_photo_in_front);
photos_in_range.subscribe(update_photo_in_front);

export function turn_to_photo_to(dir) {
    if (dir === 'left') {
        let phl = get(photo_to_left);
        if (phl) {
            bearing.set(phl.bearing);
        }
    } else if (dir === 'right') {
        let phr = get(photo_to_right);
        if (phr) {
            bearing.set(phr.bearing);
        }
    }
}

export function update_bearing(diff) {
    let b = get(bearing);
    bearing.set(b + diff);
}
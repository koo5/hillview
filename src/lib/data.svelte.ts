import {type Photo} from "./types.ts";
import {Coordinate} from "tsgeo/Coordinate";
import {Vincenty} from "tsgeo/Distance/Vincenty";
import Angles from 'angles';
//import {DMS} from "tsgeo/Formatter/Coordinate/DMS";
import {space_db} from "./debug_server.js";
import {LatLng} from 'leaflet';
import {get, writable} from "svelte/store";
import { localStorageSharedStore } from './svelte-shared-store.ts';

export const geoPicsUrl = import.meta.env.VITE_REACT_APP_GEO_PICS_URL; //+'2'

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
    //let p = get(pos);
    let p2 = get(pos2);
    let b = get(bearing);
    let ph = get(photos);
    console.log('filter_photos_by_area: p2.top_left:', p2.top_left, 'p2.bottom_right:', p2.bottom_right);
    //console.log('photos:', ph);
    const tolerance = 0.1;
    let res = ph.filter(photo => {
        //console.log('photo:', photo);
        let yes = photo.coord.lat < p2.top_left.lat + tolerance && photo.coord.lat > p2.bottom_right.lat - tolerance &&
            photo.coord.lng > p2.top_left.lng - tolerance && photo.coord.lng < p2.bottom_right.lng + tolerance;
        //console.log('yes:', yes);
        return yes;
    });
    for (let photo of res) {
        photo.abs_bearing_diff = Math.abs(Angles.distance(b, photo.bearing));
        photo.bearing_color = get_bearing_color(photo);
        photo.range_distance = null;
    }
    console.log('Photos in area:', res.length);
    photos_in_area.set(res);
};

//pos.subscribe(filter_photos_by_area);
pos2.subscribe(filter_photos_by_area);
bearing.subscribe(filter_photos_by_area);
photos.subscribe(filter_photos_by_area);

function filter_photos_in_range() {
    let p = get(pos);
    let p2 = get(pos2);
    let ph = get(photos_in_area);
    let res = ph.filter(photo => {
        photo.range_distance = dist(photo.coord, p.center);
        //console.log('photo.range_distance:', photo.range_distance, 'p2.range:', p2.range);
        if (photo.range_distance > p2.range) {
            photo.range_distance = null;
        }
        return photo.range_distance !== null;
    });
    console.log('Photos in range:', res.length);
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
    let phsl = [];
    let phsr = [];
    for (let i = 0; i < 5; i++) {
        let phl = ph[(idx - i + ph.length) % ph.length];
        let phr = ph[(idx + i) % ph.length];
        if (phsl.indexOf(phl) === -1 && phsr.indexOf(phl) === -1)
            phsl.push(phl);
        if (phsl.indexOf(phr) === -1 && phsr.indexOf(phr) === -1)
            phsr.push(phr);
    }
    phsl.reverse();
    photos_to_left.set(phsl);
    photos_to_right.set(phsr);
}

bearing.subscribe(update_view);
photos_in_range.subscribe(update_view);

export function turn_to_photo_to(dir) {
    console.log('turn_to_photo_to:', dir);
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

function get_bearing_color(photo) {
    if (photo.abs_bearing_diff === null) return '#9E9E9E'; // grey
    return 'hsl(' + (100 - photo.abs_bearing_diff/2) + ', 100%, 70%)';
}


function RGB2HTML(red, green, blue)
{
    red = Math.min(255, Math.max(0, Math.round(red)));
    green = Math.min(255, Math.max(0, Math.round(green)));
    blue = Math.min(255, Math.max(0, Math.round(blue)));
    let r = red.toString(16);
    let g = green.toString(16);
    let b = blue.toString(16);
    if (r.length == 1) r = '0' + r;
    if (g.length == 1) g = '0' + g;
    if (b.length == 1) b = '0' + b;
    return '#' + r + g + b;
}


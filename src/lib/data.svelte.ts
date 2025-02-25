import { Photo} from "./types";
import { Coordinate } from "tsgeo/Coordinate";
import {Vincenty}   from "tsgeo/Distance/Vincenty";
import * as angles from 'angles';
import {DMS} from "tsgeo/Formatter/Coordinate/DMS";


export const geoPicsUrl = import.meta.env.VITE_REACT_APP_GEO_PICS_URL;

let calculator = new Vincenty();

export let loading = $state(true);
export let error = $state(null);


export let center = $state(new Coordinate(51.505, -0.09));
export let zoom = $state(13);
export let top_left = $state(new Coordinate(0, 0));
export let bottom_right = $state(new Coordinate(10, 10));
export let range = $state(1);
export let bearing = $state(0);

$effect(() => {
    bearing = (bearing + 360) % 360;
});

export let photos = $state([]);

export let photos_in_area = $derived.by(() => {
    let res = photos.filter(photo => {
        return photo.coord.lat >= top_left.lat && photo.coord.lat <= bottom_right.lat &&
            photo.coord.lon >= top_left.lon && photo.coord.lon <= bottom_right.lon;
    });
    for (let photo of res) {
        photo.abs_bearing_diff = Math.abs(angles.diff(bearing, photo.bearing));
        photo.range_distance = null;
    }
    return res;
});

export let photos_in_range = $derived.by(() => {
    let res = photos_in_area.filter(photo => {
        photo.range_distance = calculator.getDistance(photo.coord, center);
        if (photo.range_distance > range) {
            photo.range_distance = null;
        }
        return photo.range_distance !== null;
    });
    return res;
});

export let photo_in_front = $derived.by(() => {
    return photos_in_range.reduce((prev, current) => {
        current.diff = Math.abs(angles.diff(bearing, current.bearing));
        if (prev.diff > current.diff) {
            return current;
        }
        return prev;
    });
});

// unordered
let photos_to_left = $derived(photos_in_range.filter(photo => photo !== photo_in_front && angles.shortestDirection(bearing, photo.bearing) < 0));
let photos_to_right = $derived(photos_in_range.filter(photo => photo !== photo_in_front && angles.shortestDirection(bearing, photo.bearing) > 0));

export let photo_to_left = $derived.by(() => {
    // what is the next closest photo going left
    let result = photos_to_left.reduce((prev, current) => {
        current.diff = Math.abs(angles.diff(bearing, current.bearing));
        if (prev.diff > current.diff) {
            return current;
        }
        return prev;
    });
    if (!result) {
        // if no photo to the left, then get the "furthest away (along the circle)" photo on the right
        return photos_to_right.reduce((prev, current) => {
            if (prev.bearing < current.bearing) {
                return current;
            }
            return prev;
        });
    }
});

export let photo_to_right = $derived.by(() => {
    // what is the next closest photo going right
    let result = photos_to_right.reduce((prev, current) => {
        current.diff = Math.abs(angles.diff(bearing, current.bearing));
        if (prev.diff > current.diff) {
            return current;
        }
        return prev;
    });
    if (!result) {
        // if no photo to the right, then get the "furthest away (along the circle)" photo on the left
        return photos_to_left.reduce((prev, current) => {
            if (prev.bearing > current.bearing) {
                return current;
            }
            return prev;
        });
    }
});

export function turn_to_photo_to(dir)
{
    if (dir === 'left')
    {
        if (photo_to_left)
        {
            bearing = photo_to_left.bearing;
        }
    }
    else if (dir === 'right')
    {
        if (photo_to_right)
        {
            bearing = photo_to_right.bearing;
        }
    }
}
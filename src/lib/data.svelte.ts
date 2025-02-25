import {Coordinate, APIPhotoData, Photo, MapState} from "./types";
import { Coordinate } from "tsgeo/Coordinate";
import {Vincenty}   from "tsgeo/Distance/Vincenty";
import * as angles from 'angles';
import {DMS} from "tsgeo/Formatter/Coordinate/DMS";


export const geoPicsUrl = import.meta.env.VITE_REACT_APP_GEO_PICS_URL;

let calculator = new Vincenty();

export let loading = $state(true);
export let error = $state(null);
export let photos = $state([]);



export let map_state = $state({
    center: new Coordinate(51.505, -0.09),
    zoom: 13,
    bearing: 0
});
export let range = $state(1);

export let photos_in_area = $derived.by(() => {
    return photos.filter(photo => {calculator.getDistance(photo.coord, map_state.center) <= range;});
});
export let photo_in_front = $derived.by(() => {
    return photos_in_area.reduce((prev, current) => {
        current.diff = Math.abs(angles.diff(map_state.bearing, current.bearing));
        if (prev.diff > current.diff) {
            return current;
        }
        return prev;
    });
});

// unordered
let photos_to_left = $derived(photos_in_area.filter(photo => angles.shortestDirection(map_state.bearing, photo.bearing) < 0));
let photos_to_right = $derived(photos_in_area.filter(photo => angles.shortestDirection(map_state.bearing, photo.bearing) > 0));

export let photo_to_left = $derived.by(() => {
    // what is the next closest photo going left
    let result = photos_to_left.reduce((prev, current) => {
        current.diff = Math.abs(angles.diff(map_state.bearing, current.bearing));
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
        current.diff = Math.abs(angles.diff(map_state.bearing, current.bearing));
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

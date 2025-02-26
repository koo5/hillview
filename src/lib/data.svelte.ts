//import { Photo } from "./types.ts";
import { Coordinate } from "tsgeo/Coordinate";
import {Vincenty}   from "tsgeo/Distance/Vincenty";
import * as angles from 'angles';
//import {DMS} from "tsgeo/Formatter/Coordinate/DMS";
import { space_db } from "./debug_server.js";


export const geoPicsUrl = import.meta.env.VITE_REACT_APP_GEO_PICS_URL;

let calculator = new Vincenty();

export let state = $state({
    loading: true,
    error: null
})

export let map_state = $state({
    center: new Coordinate(51.505, -0.09),
    zoom: 13,
    top_left: new Coordinate(0, 0),
    bottom_right: new Coordinate(10, 10),
    range: 1,
    bearing: 0,
});

export let data = $state(
    {
        photos: [],
        photos_in_area: [],
        photos_in_range: [],
        photo_in_front: null,
        photos_to_left: [],
        photos_to_right: [],
        photo_to_left: null,
        photo_to_right: null
    });

const magic = $effect.root(() => {

    $effect(() => {
        map_state.bearing = (map_state.bearing + 360) % 360;
    });

    $effect(async () => {
        await space_db.transaction('rw', 'state', async () => {
            await space_db.state.clear();
            space_db.state.add({
                ts: Date.now(),
                center: map_state.center,
                zoom: map_state.zoom,
                top_left: map_state.top_left,
                bottom_right: map_state.bottom_right,
                range: map_state.range,
                bearing: map_state.bearing
            });
        });
    });

    $effect(() => {
        let res = data.photos.filter(photo => {
            return photo.coord.lat >= map_state.top_left.lat && photo.coord.lat <= map_state.bottom_right.lat &&
                photo.coord.lon >= map_state.top_left.lon && photo.coord.lon <= map_state.bottom_right.lon;
        });
        for (let photo of res) {
            photo.abs_bearing_diff = Math.abs(angles.diff(map_state.bearing, photo.bearing));
            photo.range_distance = null;
        }
        data.photos_in_area = res;
    });

    $effect(() => {
        let res = data.photos_in_area.filter(photo => {
            photo.range_distance = calculator.getDistance(photo.coord, map_state.center);
            if (photo.range_distance > map_state.range) {
                photo.range_distance = null;
            }
            return photo.range_distance !== null;
        });
        data.photos_in_range = res;
    });

    $effect(() => {
        data.photo_in_front = data.photos_in_range.reduce((prev, current) => {
            current.diff = Math.abs(angles.diff(map_state.bearing, current.bearing));
            if (prev.diff > current.diff) {
                return current;
            }
            return prev;
        }, null);
    });

// unordered
    $effect(() => {
        data.photos_to_left = data.photos_in_range.filter(photo => photo !== data.photo_in_front && angles.shortestDirection(map_state.bearing, photo.bearing) < 0);
    });

    $effect(() => {
        data.photos_to_right = data.photos_in_range.filter(photo => photo !== data.photo_in_front && angles.shortestDirection(map_state.bearing, photo.bearing) > 0);
    });

    $effect(() => {
        // what is the next closest photo going left
        let result = data.photos_to_left.reduce((prev, current) => {
            current.diff = Math.abs(angles.diff(map_state.bearing, current.bearing));
            if (prev.diff > current.diff) {
                return current;
            }
            return prev;
        }, null);
        if (!result) {
            // if no photo to the left, then get the "furthest away (along the circle)" photo on the right
            result = data.photos_to_right.reduce((prev, current) => {
                if (prev.bearing < current.bearing) {
                    return current;
                }
                return prev;
            }, null);
        }
        data.photo_to_left = result;
    });

    $effect(() => {
        // what is the next closest photo going right
        let result = data.photos_to_right.reduce((prev, current) => {
            current.diff = Math.abs(angles.diff(map_state.bearing, current.bearing));
            if (prev.diff > current.diff) {
                return current;
            }
            return prev;
        }, null);
        if (!result) {
            // if no photo to the right, then get the "furthest away (along the circle)" photo on the left
            result = data.photos_to_left.reduce((prev, current) => {
                if (prev.bearing > current.bearing) {
                    return current;
                }
                return prev;
            }, null);
        }
        data.photo_to_right = result;
    });

});

export function turn_to_photo_to(dir)
{
    if (dir === 'left')
    {
        if (data.photo_to_left)
        {
            map_state.bearing = data.photo_to_left.bearing;
        }
    }
    else if (dir === 'right')
    {
        if (data.photo_to_right)
        {
            map_state.bearing = data.photo_to_right.bearing;
        }
    }
}
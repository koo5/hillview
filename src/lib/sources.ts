import {app, photos, geoPicsUrl} from "$lib/data.svelte";
//import { APIPhotoData, Photo} from "./types.ts";
import { Coordinate } from "tsgeo/Coordinate";
import { LatLng } from 'leaflet';


export async function fetch_photos() {
    console.log('Fetching photos...');
    try {
        app.update(state => ({ ...state, loading: true, error: null }));
        const response = await fetch(`${geoPicsUrl}/files.json`, {
            headers: { Accept: 'application/json' }
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const res = await response.json();
        if (!Array.isArray(res)) {
            throw new Error('Expected an array of APIPhotoData, but received something else.');
        }

        const ph = res.map(item => parse_photo_data(item));
        fixup(ph)
        console.log('Photos loaded:', ph);
        app.update(state => ({ ...state, error: null }));
        photos.set(ph);
    } catch (err) {
        console.error('Error fetching photos:', err);
        app.update(state => ({ ...state, error: err.message }));
    } finally {
        app.update(state => ({ ...state, loading: false }));
    }
}

function fixup(photos) {
    // Sort photos by bearing
    photos.sort((a, b) => a.bearing - b.bearing);
    // Calculate the difference between each photo's bearing and the next
    photos.forEach((photo, index) => {
        const next = photos[(index + 1) % photos.length];
        let diff = next.bearing - photo.bearing;
        if (diff === 0) {
            next.bearing += 0.0001;
        }
    });
}

export function parseCoordinate(coord) {
    try {
        // Convert something like "[51, 30, 20]" or "[51,30,20/1]" into decimal
        const parts = coord.replace('[', '').replace(']', '').split(',').map(p => p.trim());
        const degrees = parseFloat(parts[0]);
        const minutes = parseFloat(parts[1]);
        let seconds = 0;
        if (parts[2].includes('/')) {
            const [num, denom] = parts[2].split('/').map(Number);
            seconds = num / denom;
        } else {
            seconds = parseFloat(parts[2]);
        }
        return degrees + minutes / 60 + seconds / 3600;
    } catch (error) {
        console.error('Error parsing coordinate:', coord, error);
        return 0;
    }
}

function parseFraction(value) {
    if (!value) return 0;
    if (value.includes('/')) {
        const [numerator, denominator] = value.split('/').map(Number);
        return numerator / denominator;
    }
    return parseFloat(value) || 0;
}

function parse_photo_data(item) {
    let latitude = parseCoordinate(item.latitude);
    let longitude = parseCoordinate(item.longitude);

    let photo = {
        id: Math.random().toString(36).substring(7),
        file: item.file,
        url: `${geoPicsUrl}/${encodeURIComponent(item.file)}`,
        coord: new LatLng(latitude, longitude),
        bearing: parseFraction(item.bearing),
        altitude: parseFraction(item.altitude),
        loaded: false
    };

    if (item.sizes) {
        photo.sizes = {}
        for (let size in item.sizes) {
            photo.sizes[size] = `${geoPicsUrl}/${item.sizes[size]}`;
        }
    }

    if (latitude.isNaN || longitude.isNaN) {
        console.error('Invalid coordinates:', photo);
    }
    if (photo.bearing < 0 || photo.bearing > 360) {
        console.error('Invalid bearing:', photo);
    }
    return photo;
}


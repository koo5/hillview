import {state, geoPicsUrl, data} from "$lib/data.svelte";
//import { APIPhotoData, Photo} from "./types.ts";
import { Coordinate } from "tsgeo/Coordinate";


export async function fetch_photos() {
    try {
        state.loading = true;
        const response = await fetch(`${geoPicsUrl}/files.json`, {
            headers: { Accept: 'application/json' }
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        if (!Array.isArray(data)) {
            throw new Error('Expected an array of APIPhotoData, but received something else.');
        }

        const initialPhotos = data.map(item => parse_photo_data(item));
        data.photos = initialPhotos;
        state.error = null;
    } catch (err) {
        console.error('Error fetching photos:', err);
        state.error = `Failed to load photos: ${err.message}`;
    } finally {
        state.loading = false;
    }
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
    let photo = {
        id: Math.random().toString(36).substring(7),
        file: item.file,
        url: `${geoPicsUrl}/${encodeURIComponent(item.file)}`,
        latitude: parseCoordinate(item.latitude),
        longitude: parseCoordinate(item.longitude),
        bearing: parseFraction(item.bearing),
        altitude: parseFraction(item.altitude),
        loaded: false
    };
    photo.coord = new Coordinate(photo.latitude, photo.longitude);
    if (photo.latitude.isNaN || photo.longitude.isNaN) {
        console.error('Invalid coordinates:', photo);
    }
    if (photo.direction < 0 || photo.direction > 360) {
        console.error('Invalid direction:', photo);
    }
    return photo;
}


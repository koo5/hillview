import {error, geoPicsUrl, loading, photos, range} from "$lib/data.svelte";
import { APIPhotoData, Photo} from "./types";

export async function fetch_photos() {
    try {
        loading = true;
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
        photos = initialPhotos;
        error = null;
    } catch (err) {
        console.error('Error fetching photos:', err);
        error = `Failed to load photos: ${err.message}`;
    } finally {
        loading = false;
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
    let result = {
        id: Math.random().toString(36).substring(7),
        file: item.file,
        url: `${geoPicsUrl}/${encodeURIComponent(item.file)}`,
        latitude: parseCoordinate(item.latitude),
        longitude: parseCoordinate(item.longitude),
        bearing: parseFraction(item.bearing),
        altitude: parseFraction(item.altitude),
        loaded: false
    };
    if (result.latitude.isNaN || result.longitude.isNaN) {
        console.error('Invalid coordinates:', result);
    }
    if (direction < 0 || direction > 360) {
        console.error('Invalid direction:', result);
    }
    return result;
}


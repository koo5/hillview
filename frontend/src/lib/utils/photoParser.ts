import type { PhotoSize } from '../types/photoTypes';

// Simple coordinate interface for worker compatibility
export interface SimpleLatLng {
    lat: number;
    lng: number;
}

// Shared photo parsing utilities that can be used by both frontend and worker

export function parseCoordinate(coord: string): number {
    try {
        // Convert something like "[51, 30, 20]" or "[51,30,20/1]" into decimal
        const parts = coord.replace('[', '').replace(']', '').split(',').map((p: string) => p.trim());
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

export function parseFraction(value: string | number): number {
    if (!value) return 0;
    if (typeof value === 'string' && value.includes('/')) {
        const [numerator, denominator] = value.split('/').map(Number);
        return numerator / denominator;
    }
    return typeof value === 'string' ? parseFloat(value) || 0 : value;
}

// Worker-compatible PhotoData with simple coordinate object
export interface WorkerPhotoData {
    id: string;
    source_type: string;
    file: string;
    url: string;
    coord: SimpleLatLng; // Simple object for worker compatibility
    bearing: number;
    altitude: number;
    source?: any;
    sizes?: Record<string, PhotoSize>;
}

export function parsePhotoData(item: any, geoPicsUrl: string): WorkerPhotoData {
    const latitude = parseCoordinate(item.latitude);
    const longitude = parseCoordinate(item.longitude);

    const photo: WorkerPhotoData = {
        id: 'hillview_' + item.file,
        source_type: 'hillview',
        file: item.file,
        url: `${geoPicsUrl}/${encodeURIComponent(item.file)}`,
        coord: { lat: latitude, lng: longitude }, // Simple object for worker compatibility
        bearing: parseFraction(item.bearing),
        altitude: parseFraction(item.altitude),
    };

    if (item.sizes) {
        photo.sizes = {};
        for (const size in item.sizes) {
            const s = item.sizes[size];
            photo.sizes[size] = {
                url: `${geoPicsUrl}/${s.path}`,
                width: s.width,
                height: s.height
            };
        }
    }

    if (isNaN(latitude) || isNaN(longitude)) {
        console.error('Invalid coordinates:', photo);
    }
    if (photo.bearing < 0 || photo.bearing > 360) {
        console.error('Invalid bearing:', photo);
    }
    return photo;
}

// Source loading functions that can be used by both frontend and worker
export async function loadJsonPhotos(url: string, geoPicsUrl: string): Promise<WorkerPhotoData[]> {
    console.log(`Loading JSON photos from ${url}`);
    
    const response = await fetch(url, {
        headers: { Accept: 'application/json' }
    });

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    const rawData = await response.json();
    if (!Array.isArray(rawData)) {
        throw new Error('Expected an array of photo data');
    }

    return rawData.map((item: any) => parsePhotoData(item, geoPicsUrl));
}
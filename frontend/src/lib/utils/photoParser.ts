
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


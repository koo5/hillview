import { Coordinate } from 'tsgeo/Coordinate';
import { Vincenty } from 'tsgeo/Distance/Vincenty';
import type { LatLng } from 'leaflet';
import type { Bounds } from '../photoWorkerTypes';

// Shared calculator instance
const calculator = new Vincenty();

/**
 * Calculate distance between two coordinates in meters
 */
export function calculateDistance(from: LatLng | { lat: number; lng: number }, to: LatLng | { lat: number; lng: number }): number {
    const fromCoord = new Coordinate(from.lat, from.lng);
    const toCoord = new Coordinate(to.lat, to.lng);
    return calculator.getDistance(fromCoord, toCoord);
}

/**
 * Calculate center point from bounds
 */
export function calculateCenterFromBounds(bounds: Bounds): { lat: number; lng: number } {
    return {
        lat: (bounds.top_left.lat + bounds.bottom_right.lat) / 2,
        lng: (bounds.top_left.lng + bounds.bottom_right.lng) / 2
    };
}

/**
 * Simple distance calculator for use in web workers (where tsgeo might not be available)
 * Uses Haversine formula
 */
/*
export class SimpleDistanceCalculator {
    getDistance(coord1: { lat: number; lng: number }, coord2: { lat: number; lng: number }): number {
        const R = 6371000; // Earth's radius in meters
        const lat1Rad = coord1.lat * Math.PI / 180;
        const lat2Rad = coord2.lat * Math.PI / 180;
        const deltaLat = (coord2.lat - coord1.lat) * Math.PI / 180;
        const deltaLng = (coord2.lng - coord1.lng) * Math.PI / 180;
        
        const a = Math.sin(deltaLat/2) * Math.sin(deltaLat/2) +
                 Math.cos(lat1Rad) * Math.cos(lat2Rad) *
                 Math.sin(deltaLng/2) * Math.sin(deltaLng/2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        
        return R * c;
    }
}
*/
export class SimpleDistanceCalculator {
    getDistance(coord1: { lat: number; lng: number }, coord2: { lat: number; lng: number }): number {
        const deltaLat = coord2.lat - coord1.lat;
        const deltaLng = coord2.lng - coord1.lng;
        return Math.sqrt(deltaLat * deltaLat + deltaLng * deltaLng);
    }
}

/**
 * Check if a coordinate is within bounds
 */
export function isInBounds(location: { lat: number; lng: number }, bounds: Bounds): boolean {
    const normalizeLng = (lng: number): number => {
        while (lng > 180) lng -= 360;
        while (lng < -180) lng += 360;
        return lng;
    };
    
    const photoLng = normalizeLng(location.lng);
    const leftLng = normalizeLng(bounds.top_left.lng);
    const rightLng = normalizeLng(bounds.bottom_right.lng);
    
    const inLat = location.lat <= bounds.top_left.lat && 
                 location.lat >= bounds.bottom_right.lat;
    
    let inLng: boolean;
    if (leftLng > rightLng) {
        // Bounds cross the date line
        inLng = photoLng >= leftLng || photoLng <= rightLng;
    } else {
        // Normal bounds
        inLng = photoLng >= leftLng && photoLng <= rightLng;
    }
    
    return inLat && inLng;
}
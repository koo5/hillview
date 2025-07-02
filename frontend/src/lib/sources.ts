import {app, hillview_photos, geoPicsUrl} from "$lib/data.svelte";
//import { APIPhotoData, Photo} from "./types.ts";
//import { Coordinate } from "tsgeo/Coordinate";
import { LatLng } from 'leaflet';
import {writable, get} from "svelte/store";
import { auth } from "$lib/auth.svelte.ts";
import { userPhotos, devicePhotos } from './stores';
import { photoCaptureService } from './photoCapture';


export let sources = writable([
    {id: 'hillview', name: 'Hillview', enabled: true, requests: [], color: '#000'},
    {id: 'mapillary', name: 'Mapillary', enabled: false, requests: [], color: '#888'},
    {id: 'device', name: 'My Device', enabled: true, requests: [], color: '#4a90e2'},
]);


export async function fetch_photos() {
    console.log('Fetching photos...');
    try {
        app.update(state => ({ ...state, loading: true, error: null }));
        
        // Load device photos from backend
        try {
            const devicePhotosDb = await photoCaptureService.loadDevicePhotos();
            devicePhotos.set(devicePhotosDb.photos);
        } catch (error) {
            console.error('Failed to load device photos:', error);
        }
        
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

        console.log('parse_photo_data...');
        const ph = res.map(item => parse_photo_data(item));
        let src = get(sources).find(s => s.id === 'hillview');
        ph.map(p => p.source = src);
        
        // Add user photos if authenticated
        const authState = get(auth);
        const userPhotosList = get(userPhotos);
        if (authState.isAuthenticated && userPhotosList && userPhotosList.length > 0) {
            console.log('Adding user photos:', userPhotosList.length);
            for (let photo of userPhotosList) {
                // Only add photos with location data
                if (photo.latitude && photo.longitude) {
                    let userPhoto = {
                        id: 'user_' + photo.id,
                        source_type: 'user',
                        file: photo.filename,
                        url: `http://localhost:8089/api/photos/${photo.id}/thumbnail`,
                        coord: new LatLng(photo.latitude, photo.longitude),
                        bearing: photo.compass_angle || 0,
                        altitude: photo.altitude || 0,
                        source: src,
                        isUserPhoto: true
                    };
                    
                    if (userPhoto.bearing < 0 || userPhoto.bearing > 360) {
                        userPhoto.bearing = 0;
                    }
                    
                    ph.push(userPhoto);
                }
            }
        }
        
        // Add device photos
        const devicePhotosList = get(devicePhotos);
        const deviceSource = get(sources).find(s => s.id === 'device');
        if (deviceSource && deviceSource.enabled && devicePhotosList && devicePhotosList.length > 0) {
            console.log('Adding device photos:', devicePhotosList.length);
            for (let photo of devicePhotosList) {
                let devicePhoto = {
                    id: photo.id,
                    source_type: 'device',
                    file: photo.filename,
                    url: photo.path, // Local file path
                    coord: new LatLng(photo.latitude, photo.longitude),
                    bearing: photo.bearing || 0,
                    altitude: photo.altitude || 0,
                    source: deviceSource,
                    isDevicePhoto: true,
                    timestamp: photo.timestamp,
                    accuracy: photo.accuracy,
                    sizes: {
                        full: {
                            url: photo.path,
                            width: photo.width,
                            height: photo.height
                        }
                    }
                };
                
                if (devicePhoto.bearing < 0 || devicePhoto.bearing > 360) {
                    devicePhoto.bearing = 0;
                }
                
                ph.push(devicePhoto);
            }
        }
        
        console.log('fixup_bearings...');
        fixup_bearings(ph)
        console.log('Photos loaded:', ph);
        app.update(state => ({ ...state, error: null }));
        hillview_photos.set(ph);
    } catch (err) {
        console.error('Error fetching photos:', err);
        app.update(state => ({ ...state, error: err.message }));
    } finally {
        app.update(state => ({ ...state, loading: false }));
    }
}

export function fixup_bearings(photos) {
    // Sort photos by bearing, spreading out photos with the same bearing
    if (photos.length < 2) return;
    let moved = true;
    while (moved) {
        photos.sort((a, b) => a.bearing - b.bearing);
        moved = false;
        for (let index = 0; index < photos.length + 1; index++) {
            //console.log('Index:', index);
            const next = photos[(index + 1) % photos.length];
            const photo = photos[index % photos.length];
            let diff = next.bearing - photo.bearing;
            if (diff === 0) {
                next.bearing = (next.bearing + 0.01) % 360;
                moved = true;
            }
        }
        console.log('Moved:', moved);
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
    let latitude = parseCoordinate(item.latitude);
    let longitude = parseCoordinate(item.longitude);

    let photo = {
        id: 'hillview_' + item.file,
        source_type: 'hillview',
        file: item.file,
        url: `${geoPicsUrl}/${encodeURIComponent(item.file)}`,
        coord: new LatLng(latitude, longitude),
        bearing: parseFraction(item.bearing),
        altitude: parseFraction(item.altitude),
    };

    if (item.sizes) {
        photo.sizes = {}
        for (let size in item.sizes) {
            let s = item.sizes[size];
            photo.sizes[size] = {
                url: `${geoPicsUrl}/${s.path}`,
                width: s.width,
                height: s.height
            }
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


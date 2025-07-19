import {app, hillview_photos, sources, type Source} from "$lib/data.svelte";
import { geoPicsUrl } from './config';
//import { APIPhotoData, Photo} from "./types.ts";
//import { Coordinate } from "tsgeo/Coordinate";
import { LatLng } from 'leaflet';
import {writable, get} from "svelte/store";
import { auth } from "$lib/auth.svelte";
import { userPhotos, devicePhotos } from './stores';
import { photoCaptureService } from './photoCapture';
import type { PhotoData, PhotoSize, DevicePhotoMetadata } from './types/photoTypes';



// Fetch photos from a specific source
export async function fetchSourcePhotos(sourceId: string) {
    const source = get(sources).find(s => s.id === sourceId);
    if (!source || !source.enabled) return;
    
    console.log(`Fetching photos from source: ${source.name}`);
    
    switch (source.type) {
        case 'json':
            await fetchJsonSource(source);
            break;
        case 'device':
            await fetchDeviceSource(source);
            break;
        case 'directory':
            await fetchDirectorySource(source);
            break;
        // Mapillary is handled separately through streaming
    }
}

async function fetchJsonSource(source: Source) {
    if (!source.url) return;
    
    const requestId = Date.now();
    try {
        // Add loading indicator
        sources.update(srcs => {
            const src = srcs.find(s => s.id === source.id);
            if (src) src.requests.push(requestId);
            return srcs;
        });
        
        const response = await fetch(source.url, {
            headers: { Accept: 'application/json' }
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const res = await response.json();
        if (!Array.isArray(res)) {
            throw new Error('Expected an array of photo data');
        }

        const newPhotos: PhotoData[] = res.map((item: any) => {
            const photo = parse_photo_data(item);
            photo.source = source;
            return photo;
        });

        // Update hillview_photos by replacing photos from this source
        hillview_photos.update(photos => {
            // Remove old photos from this source
            const otherPhotos = photos.filter(p => p.source?.id !== source.id);
            // Add new photos
            return [...otherPhotos, ...newPhotos];
        });
        
    } catch (error) {
        console.error(`Error fetching from ${source.name}:`, error);
        app.update(state => ({ 
            ...state, 
            error: `Failed to load ${source.name}: ${error instanceof Error ? error.message : 'Unknown error'}` 
        }));
    } finally {
        // Clear loading indicator
        sources.update(srcs => {
            const src = srcs.find(s => s.id === source.id);
            if (src) src.requests = src.requests.filter(id => id !== requestId);
            return srcs;
        });
    }
}

async function fetchDeviceSource(source: Source) {
    const requestId = Date.now();
    try {
        // Add loading indicator
        sources.update(srcs => {
            const src = srcs.find(s => s.id === source.id);
            if (src) src.requests.push(requestId);
            return srcs;
        });
        
        const devicePhotosDb = await photoCaptureService.loadDevicePhotos();
        devicePhotos.set(devicePhotosDb.photos);
        
        const devicePhotosList = devicePhotosDb.photos;
        const newPhotos: PhotoData[] = [];
        
        if (devicePhotosList && devicePhotosList.length > 0) {
            for (let photo of devicePhotosList) {
                let devicePhoto: PhotoData = {
                    id: photo.id,
                    source_type: 'device',
                    file: photo.filename,
                    url: photo.path,
                    coord: new LatLng(photo.latitude, photo.longitude),
                    bearing: photo.bearing || 0,
                    altitude: photo.altitude || 0,
                    source: source,
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
                
                newPhotos.push(devicePhoto);
            }
        }
        
        // Update hillview_photos by replacing device photos
        hillview_photos.update(photos => {
            // Remove old device photos
            const otherPhotos = photos.filter(p => p.source?.id !== 'device');
            // Add new device photos
            return [...otherPhotos, ...newPhotos];
        });
        
    } catch (error) {
        console.error('Failed to load device photos:', error);
    } finally {
        // Clear loading indicator
        sources.update(srcs => {
            const src = srcs.find(s => s.id === source.id);
            if (src) src.requests = src.requests.filter(id => id !== requestId);
            return srcs;
        });
    }
}

async function fetchDirectorySource(source: Source) {
    if (!source.path) {
        console.warn('Directory source has no path specified');
        return;
    }

    const requestId = Date.now();
    try {
        // Add loading indicator
        sources.update(srcs => {
            const src = srcs.find(s => s.id === source.id);
            if (src) src.requests.push(requestId);
            return srcs;
        });
        
        // Use photoCaptureService pattern but for directory scanning
        const directoryPhotosDb = await photoCaptureService.loadDirectoryPhotos(source.path);
        
        const directoryPhotosList = directoryPhotosDb.photos;
        const newPhotos: PhotoData[] = [];
        
        if (directoryPhotosList && directoryPhotosList.length > 0) {
            for (let photo of directoryPhotosList) {
                let directoryPhoto: PhotoData = {
                    id: `${source.id}_${photo.id}`,
                    source_type: 'directory',
                    file: photo.filename,
                    url: photo.path,
                    coord: new LatLng(photo.latitude, photo.longitude),
                    bearing: photo.bearing || 0,
                    altitude: photo.altitude || 0,
                    source: source,
                    isDirectoryPhoto: true,
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
                
                if (directoryPhoto.bearing < 0 || directoryPhoto.bearing > 360) {
                    directoryPhoto.bearing = 0;
                }
                
                newPhotos.push(directoryPhoto);
            }
        }
        
        // Update hillview_photos by replacing photos from this source
        hillview_photos.update(photos => {
            // Remove old photos from this source
            const otherPhotos = photos.filter(p => p.source?.id !== source.id);
            // Add new photos
            return [...otherPhotos, ...newPhotos];
        });
        
    } catch (error) {
        console.error(`Failed to load directory photos from ${source.path}:`, error);
        app.update(state => ({ 
            ...state, 
            error: `Failed to load directory ${source.name}: ${error instanceof Error ? error.message : 'Unknown error'}` 
        }));
    } finally {
        // Clear loading indicator
        sources.update(srcs => {
            const src = srcs.find(s => s.id === source.id);
            if (src) src.requests = src.requests.filter(id => id !== requestId);
            return srcs;
        });
    }
}

export async function fetch_photos() {
    console.log('Fetching all photos...');
    const requestId = Date.now();
    
    try {
        app.update(state => ({ ...state, loading: true, error: null }));
        
        // Add loading indicators for enabled sources
        sources.update(srcs => {
            srcs.forEach((src, index) => {
                if (src.enabled) {
                    src.requests.push(requestId + index);
                }
            });
            return srcs;
        });
        
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
        const ph: PhotoData[] = res.map((item: any) => parse_photo_data(item));
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
        console.log('Device photos check:', {
            deviceSource: deviceSource?.id,
            enabled: deviceSource?.enabled,
            devicePhotosCount: devicePhotosList?.length
        });
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
        
        
        console.log('Photos loaded:', ph.length);
        app.update(state => ({ ...state, error: null }));
        hillview_photos.set(ph);
    } catch (err) {
        console.error('Error fetching photos:', err);
        app.update(state => ({ ...state, error: err instanceof Error ? err.message : 'Unknown error' }));
    } finally {
        app.update(state => ({ ...state, loading: false }));
        
        // Clear loading indicators for both sources
        sources.update(srcs => {
            const hillviewSrc = srcs.find(s => s.id === 'hillview');
            const deviceSrc = srcs.find(s => s.id === 'device');
            
            if (hillviewSrc) {
                hillviewSrc.requests = hillviewSrc.requests.filter(id => id !== requestId);
            }
            if (deviceSrc) {
                deviceSrc.requests = deviceSrc.requests.filter(id => id !== requestId + 1);
            }
            
            return srcs;
        });
    }
}


export function parseCoordinate(coord: string) {
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

function parseFraction(value: string | number) {
    if (!value) return 0;
    if (typeof value === 'string' && value.includes('/')) {
        const [numerator, denominator] = value.split('/').map(Number);
        return numerator / denominator;
    }
    return typeof value === 'string' ? parseFloat(value) || 0 : value;
}

// Re-export for backward compatibility
export type { PhotoData, PhotoSize };

function parse_photo_data(item: any): PhotoData {
    let latitude = parseCoordinate(item.latitude);
    let longitude = parseCoordinate(item.longitude);

    let photo: PhotoData = {
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

    if (isNaN(latitude) || isNaN(longitude)) {
        console.error('Invalid coordinates:', photo);
    }
    if (photo.bearing < 0 || photo.bearing > 360) {
        console.error('Invalid bearing:', photo);
    }
    return photo;
}







export function source_by_id(id: string) {
    return get(sources).find(s => s.id === id);
}


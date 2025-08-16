import {app, hillview_photos, sources, type Source} from "$lib/data.svelte";
import { geoPicsUrl } from './config';
import { LatLng } from 'leaflet';
import {writable, get} from "svelte/store";
import { auth } from "$lib/auth.svelte";
import { userPhotos, devicePhotos } from './stores';
import { photoCaptureService } from './photoCapture';
import type { PhotoData, PhotoSize, DevicePhotoMetadata } from './types/photoTypes';
import { parsePhotoData, loadJsonPhotos, parseCoordinate, parseFraction } from './utils/photoParser';

// Frontend-specific photo parser that uses proper LatLng objects
function parsePhotoDataForFrontend(item: any): PhotoData {
    const latitude = parseCoordinate(item.latitude);
    const longitude = parseCoordinate(item.longitude);

    const photo: PhotoData = {
        id: 'hillview_' + item.file,
        source_type: 'hillview',
        file: item.file,
        url: `${geoPicsUrl}/${encodeURIComponent(item.file)}`,
        coord: new LatLng(latitude, longitude), // Use proper LatLng for frontend
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

    return photo;
}



// Fetch photos from a specific source
export async function fetchSourcePhotos(sourceId: string) {
    const source = get(sources).find(s => s.id === sourceId);
    if (!source || !source.enabled) return;
    
    console.log(`Fetching photos from source: ${source.name}`);
    
    switch (source.type) {
        case 'device':
            await fetchDeviceSource(source);
            break;
        // Stream sources are handled separately through streaming
        case 'stream':
            console.log(`Stream source ${source.name} is handled via streaming, not fetch`);
            break;
        default:
            console.warn(`Unknown source type: ${source.type}`);
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
        
        // Use shared photo loading utility
        const newPhotos = await loadJsonPhotos(source.url);
        
        // Set source reference on each photo
        newPhotos.forEach(photo => {
            photo.source = source;
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
        const ph: PhotoData[] = res.map((item: any) => parsePhotoDataForFrontend(item));
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


// Re-export utilities and types for backward compatibility
export { parseCoordinate, parseFraction } from './utils/photoParser';
export { parsePhotoDataForFrontend as parse_photo_data };
export type { PhotoData, PhotoSize };







export function source_by_id(id: string) {
    return get(sources).find(s => s.id === id);
}


import {app, hillview_photos, sources, type Source} from "$lib/data.svelte";
import { LatLng } from 'leaflet';
import {writable, get} from "svelte/store";
import { userPhotos, devicePhotos } from './stores';
import { photoCaptureService } from './photoCapture';
import type { PhotoData, PhotoSize, DevicePhotoMetadata } from './types/photoTypes';
import { parseCoordinate, parseFraction } from './utils/photoParser';



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



// Re-export utilities and types for backward compatibility
export { parseCoordinate, parseFraction } from './utils/photoParser';
export type { PhotoData, PhotoSize };

import { writable } from 'svelte/store';
import { localStorageSharedStore } from './svelte-shared-store';

export interface Resolution {
    width: number;
    height: number;
    label: string; // e.g., "1080p", "4K", "720p"
}

export interface CameraDevice {
    deviceId: string;
    label: string;
    facingMode: 'front' | 'back' | 'unknown';
    isPreferred?: boolean; // For marking the "standard" back camera
    resolutions?: Resolution[]; // Available resolutions for this camera
}

// Store for available camera devices
export const availableCameras = writable<CameraDevice[]>([]);

// Store for currently selected camera device ID (persistent)
export const selectedCameraId = localStorageSharedStore<string | null>('selectedCameraId', null);

// Store for currently selected resolution (persistent)
export const selectedResolution = localStorageSharedStore<Resolution | null>('selectedResolution', null);

// Store for whether camera enumeration is supported
export const cameraEnumerationSupported = writable<boolean>(false);

export async function enumerateCameraDevices(): Promise<CameraDevice[]> {
    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
            console.log('🢄[CAMERAS] Device enumeration not supported');
            cameraEnumerationSupported.set(false);
            return [];
        }

        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter(device => device.kind === 'videoinput');

        console.log('🢄[CAMERAS] Found video devices:', videoDevices.length);

        const cameraDevices: CameraDevice[] = videoDevices
            .map(device => {
                const label = device.label.toLowerCase();
                let facingMode: 'front' | 'back' | 'unknown' = 'unknown';
                let isPreferred = false;

                // Determine facing mode from label
                if (label.includes('front') || label.includes('user') || label.includes('selfie')) {
                    facingMode = 'front';
                } else if (label.includes('back') || label.includes('rear') || label.includes('environment')) {
                    facingMode = 'back';

                    // Mark as preferred if it's a standard back camera (not wide/ultra/telephoto)
                    if (!label.includes('wide') && !label.includes('ultra') && !label.includes('telephoto')) {
                        isPreferred = true;
                    }
                }

                return {
                    deviceId: device.deviceId,
                    label: device.label || `Camera ${videoDevices.indexOf(device) + 1}`,
                    facingMode,
                    isPreferred
                };
            })
            .filter(camera => camera.facingMode !== 'front'); // Skip front cameras

        // Sort cameras: preferred back cameras first, then other back cameras
        cameraDevices.sort((a, b) => {
            if (a.isPreferred && !b.isPreferred) return -1;
            if (!a.isPreferred && b.isPreferred) return 1;
            return a.label.localeCompare(b.label);
        });

        console.log('🢄[CAMERAS] Processed cameras:', JSON.stringify(
			cameraDevices.map(c => ({
            label: c.label,
            facing: c.facingMode,
            preferred: c.isPreferred,
            id: c.deviceId.slice(0, 8) + '...'
        }))));

        availableCameras.set(cameraDevices);
        cameraEnumerationSupported.set(true);

        return cameraDevices;
    } catch (error) {
        console.error('🢄[CAMERAS] Failed to enumerate devices:', error);
        cameraEnumerationSupported.set(false);
        return [];
    }
}

export function getPreferredBackCamera(cameras: CameraDevice[]): CameraDevice | null {
    // First try to find a preferred back camera
    const preferred = cameras.find(c => c.facingMode === 'back' && c.isPreferred);
    if (preferred) return preferred;

    // Fallback to any back camera
    const anyBack = cameras.find(c => c.facingMode === 'back');
    if (anyBack) return anyBack;

    // Last resort: any camera
    return cameras[0] || null;
}



// Get hardcoded resolution options for camera
export async function getCameraSupportedResolutions(deviceId: string): Promise<Resolution[]> {
    console.log(`🢄[CAMERA] Using hardcoded resolution options for device ${deviceId.slice(0, 8)}...`);

    const hardcodedResolutions: Resolution[] = [
        { width: 3840, height: 2160, label: "4K (3840×2160)" },
        { width: 2560, height: 1440, label: "1440p (2560×1440)" },
        { width: 1920, height: 1080, label: "1080p (1920×1080)" },
        { width: 1280, height: 720, label: "720p (1280×720)" }
    ];

    console.log(`🢄[CAMERA] Offering ${hardcodedResolutions.length} resolution options:`,
        hardcodedResolutions.map(r => r.label));

    return hardcodedResolutions;
}

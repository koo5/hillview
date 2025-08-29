/**
 * Secure Upload Service
 * 
 * Implements the three-phase secure upload process:
 * 1. Request upload authorization from API server
 * 2. Generate client signature and upload to worker
 * 3. Worker verifies JWT and forwards results to API server
 */

import { clientCrypto } from './clientCrypto';
import { http } from './http';
import { backendUrl } from './config';

export interface UploadAuthorizationRequest {
    filename: string;
    file_size: number;
    content_type: string;
    description?: string;
    is_public: boolean;
    // Geolocation data for immediate map display
    latitude?: number;
    longitude?: number;
    altitude?: number;
    compass_angle?: number;
    captured_at?: string;
}

export interface UploadAuthorizationResponse {
    upload_jwt: string;
    photo_id: string;
    expires_at: string;
    worker_url: string;
}

export interface SecureUploadResult {
    success: boolean;
    message: string;
    photo_id?: string;
    error?: string;
}

/**
 * Extract geolocation data from photo file EXIF
 */
async function extractGeolocationFromFile(file: File): Promise<{
    latitude?: number;
    longitude?: number;
    altitude?: number;
    compass_angle?: number;
    captured_at?: string;
}> {
    try {
        // Basic EXIF extraction - in a real app you might use a library like exifr
        // For now, return empty object and let the worker extract EXIF data
        return {};
    } catch (error) {
        console.warn('Failed to extract EXIF data:', error);
        return {};
    }
}

/**
 * Get current device geolocation if available
 */
async function getCurrentLocation(): Promise<{
    latitude?: number;
    longitude?: number;
    altitude?: number;
}> {
    return new Promise((resolve) => {
        if (!navigator.geolocation) {
            resolve({});
            return;
        }
        
        navigator.geolocation.getCurrentPosition(
            (position) => {
                resolve({
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    altitude: position.coords.altitude || undefined
                });
            },
            (error) => {
                console.warn('Failed to get current location:', error);
                resolve({});
            },
            {
                timeout: 5000,
                enableHighAccuracy: false
            }
        );
    });
}

/**
 * Request upload authorization from API server
 */
async function requestUploadAuthorization(request: UploadAuthorizationRequest): Promise<UploadAuthorizationResponse> {
    const response = await http.post('/photos/authorize-upload', request);
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Failed to authorize upload' }));
        throw new Error(error.detail || `Upload authorization failed: ${response.status}`);
    }
    
    return await response.json();
}

/**
 * Generate client signature for upload
 */
async function generateClientSignature(photoId: string, filename: string): Promise<string> {
    const timestamp = Math.floor(Date.now() / 1000); // Unix timestamp
    
    const signature = await clientCrypto.signUploadData({
        photo_id: photoId,
        filename: filename,
        timestamp: timestamp
    });
    
    return signature;
}

/**
 * Upload file to worker with JWT and client signature
 */
async function uploadToWorker(
    file: File, 
    uploadJwt: string, 
    clientSignature: string,
    workerUrl?: string
): Promise<SecureUploadResult> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('client_signature', clientSignature);
    
    // Use configured worker URL or default to backend URL with worker port
    const workerEndpoint = workerUrl || `${backendUrl.replace(':8055', ':8056')}/upload`;
    
    const response = await fetch(workerEndpoint, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${uploadJwt}`
        },
        body: formData
    });
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Worker upload failed' }));
        throw new Error(error.detail || `Worker upload failed: ${response.status}`);
    }
    
    return await response.json();
}

/**
 * Perform secure upload of a single file
 */
export async function secureUploadFile(
    file: File,
    description?: string,
    isPublic: boolean = true,
    workerUrl?: string
): Promise<SecureUploadResult> {
    try {
        console.log(`🔐 Starting secure upload for: ${file.name}`);
        
        // Step 1: Try to extract geolocation data from file and device
        const [fileGeo, deviceGeo] = await Promise.all([
            extractGeolocationFromFile(file),
            getCurrentLocation()
        ]);
        
        // Prefer file EXIF data over device location
        const geolocation = {
            latitude: fileGeo.latitude || deviceGeo.latitude,
            longitude: fileGeo.longitude || deviceGeo.longitude,
            altitude: fileGeo.altitude || deviceGeo.altitude,
            compass_angle: fileGeo.compass_angle,
            captured_at: fileGeo.captured_at
        };
        
        // Step 2: Request upload authorization
        console.log(`🔐 Requesting upload authorization for: ${file.name}`);
        const authRequest: UploadAuthorizationRequest = {
            filename: file.name,
            file_size: file.size,
            content_type: file.type,
            description,
            is_public: isPublic,
            ...geolocation
        };
        
        const authResponse = await requestUploadAuthorization(authRequest);
        console.log(`🔐 Upload authorized, photo_id: ${authResponse.photo_id}`);
        
        // Step 3: Generate client signature
        console.log(`🔐 Generating client signature for: ${file.name}`);
        const clientSignature = await generateClientSignature(authResponse.photo_id, file.name);
        
        // Step 4: Upload to worker (use URL from authorization response)
        console.log(`🔐 Uploading to worker: ${file.name}`);
        const uploadResult = await uploadToWorker(
            file, 
            authResponse.upload_jwt, 
            clientSignature, 
            authResponse.worker_url  // Use worker URL from auth response
        );
        
        console.log(`🔐 Secure upload completed: ${file.name}`);
        return uploadResult;
        
    } catch (error) {
        console.error(`🔐 Secure upload failed for ${file.name}:`, error);
        return {
            success: false,
            message: 'Secure upload failed',
            error: error instanceof Error ? error.message : String(error)
        };
    }
}

/**
 * Upload multiple files securely with progress tracking
 */
export async function secureUploadFiles(
    files: File[],
    description?: string,
    isPublic: boolean = true,
    workerUrl?: string,
    onProgress?: (completed: number, total: number, currentFile: string) => void
): Promise<{
    results: SecureUploadResult[];
    successCount: number;
    errorCount: number;
    skipCount: number;
}> {
    const results: SecureUploadResult[] = [];
    let successCount = 0;
    let errorCount = 0;
    let skipCount = 0;
    
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        
        // Report progress
        onProgress?.(i, files.length, file.name);
        
        const result = await secureUploadFile(file, description, isPublic, workerUrl);
        results.push(result);
        
        if (result.success) {
            successCount++;
        } else {
            errorCount++;
        }
    }
    
    // Final progress report
    onProgress?.(files.length, files.length, '');
    
    return {
        results,
        successCount,
        errorCount,
        skipCount // Currently not implemented but kept for API compatibility
    };
}
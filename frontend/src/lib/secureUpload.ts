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
    file_md5: string; // MD5 hash for duplicate detection
    client_key_id: string; // Key ID that will be used for signing
    description?: string;
    is_public: boolean;
    // Geolocation data for immediate map display
    latitude?: number;
    longitude?: number;
    altitude?: number;
    bearing?: number;
    captured_at?: string;
}

export interface UploadAuthorizationResponse {
    upload_jwt: string;
    photo_id: string;
    expires_at: string;
    worker_url: string;
    upload_authorized_at: number; // Unix timestamp when upload was authorized
}

export interface SecureUploadResult {
    success: boolean;
    message: string;
    photo_id?: string;
    error?: string;
}

/**
 * Upload error classes
 */
export class UploadError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'UploadError';
    }
}

// Don't retry these - user/client issues
export class NonRetryableUploadError extends UploadError {
    constructor(message: string) {
        super(message);
        this.name = 'NonRetryableUploadError';
    }
}

// Retry these - server/network issues
export class RetryableUploadError extends UploadError {
    constructor(message: string) {
        super(message);
        this.name = 'RetryableUploadError';
    }
}

/**
 * Calculate MD5 hash of a file using crypto-js library
 */
async function calculateFileMD5(file: File): Promise<string> {
    try {
        // Import crypto-js dynamically to avoid SSR issues
        const CryptoJS = await import('crypto-js');

        // Read file as ArrayBuffer and convert to WordArray
        const buffer = await file.arrayBuffer();
        const wordArray = CryptoJS.lib.WordArray.create(buffer);

        // Calculate MD5 hash
        const hash = CryptoJS.MD5(wordArray);
        return hash.toString();
    } catch (error) {
        console.error('🢄Failed to calculate MD5 hash:', error);
        // Fall back to a simple hash based on file content and metadata
        const fallbackString = file.name + file.size + file.type + file.lastModified;
        const encoder = new TextEncoder();
        const data = encoder.encode(fallbackString);
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
        return hashHex.substring(0, 32); // Truncate to 32 chars like MD5
    }
}

/**
 * Extract geolocation data from photo file EXIF
 */
async function extractGeolocationFromFile(file: File): Promise<{
    latitude?: number;
    longitude?: number;
    altitude?: number;
    bearing?: number;
    captured_at?: string;
}> {
    try {
        // Basic EXIF extraction - in a real app you might use a library like exifr
        // For now, return empty object and let the worker extract EXIF data
        return {};
    } catch (error) {
        console.warn('🢄Failed to extract EXIF data:', error);
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
                console.warn('🢄Failed to get current location:', error);
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
 * Request upload authorization from API server with retry logic
 */
async function requestUploadAuthorization(request: UploadAuthorizationRequest): Promise<UploadAuthorizationResponse> {
    const maxRetries = 3;
    const baseDelay = 1000;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            const response = await http.post('/photos/authorize-upload', request);

            if (response.ok) {
                const responseData = await response.json();

                // Check for duplicates (non-retryable)
                if (responseData.duplicate) {
                    throw new NonRetryableUploadError(`Duplicate file detected: ${responseData.message || 'This file has already been uploaded'}`);
                }

                return responseData;
            }

            // Got response but not OK
            const error = await response.json().catch(() => ({ detail: 'Failed to authorize upload' }));
            const errorMessage = error.detail || `Upload authorization failed: ${response.status}`;

            if (response.status >= 500) {
                throw new RetryableUploadError(errorMessage);
            } else {
                throw new NonRetryableUploadError(errorMessage);
            }

        } catch (error) {
            // Let TokenExpiredError pass through unchanged
            if (error instanceof Error && error.name === 'TokenExpiredError') {
                throw error;
            }

            // Non-retryable errors should immediately propagate
            if (error instanceof NonRetryableUploadError) {
                throw error;
            }

            // Last attempt - give up
            if (attempt === maxRetries) {
                throw error instanceof RetryableUploadError ? error : new RetryableUploadError(error instanceof Error ? error.message : 'Network error');
            }

            // Retry logic
            const delay = baseDelay * Math.pow(2, attempt);
            console.log(`🢄🔐 Upload authorization failed, retrying in ${delay}ms... (attempt ${attempt + 1}/${maxRetries + 1})`);
            await new Promise(resolve => setTimeout(resolve, delay));
        }
    }

    throw new RetryableUploadError('Maximum retries exceeded');
}

/**
 * Generate client signature for upload using authorization timestamp
 */
async function generateClientSignature(photoId: string, filename: string, authTimestamp: number): Promise<{ signature: string; keyId: string }> {
    const signatureData = await clientCrypto.signUploadData({
        photo_id: photoId,
        filename: filename,
        timestamp: authTimestamp
    });

    return signatureData;
}

/**
 * Upload file to worker with JWT and client signature (with retry logic)
 */
async function uploadToWorker(
    file: File,
    uploadJwt: string,
    signature: string,
    workerUrl?: string
): Promise<SecureUploadResult> {
    const maxRetries = 3;
    const baseDelay = 2000; // Longer delay for file uploads

    // Use configured worker URL or default to backend URL with worker port
    const workerEndpoint = workerUrl || `${backendUrl.replace(':8055', ':8056')}/upload`;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('client_signature', signature);

            const response = await fetch(workerEndpoint, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${uploadJwt}`
                },
                body: formData
            });

            if (response.ok) {
                return await response.json();
            }

            // Got response but not OK
            const error = await response.json().catch(() => ({ detail: 'Worker upload failed' }));
            const errorMessage = error.detail || `Worker upload failed: ${response.status}`;

            if (response.status >= 500) {
                throw new RetryableUploadError(errorMessage);
            } else {
                throw new NonRetryableUploadError(errorMessage);
            }

        } catch (error) {
            // Let TokenExpiredError pass through unchanged
            if (error instanceof Error && error.name === 'TokenExpiredError') {
                throw error;
            }

            // Non-retryable errors should immediately propagate
            if (error instanceof NonRetryableUploadError) {
                throw error;
            }

            // Last attempt - give up
            if (attempt === maxRetries) {
                throw error instanceof RetryableUploadError ? error : new RetryableUploadError(error instanceof Error ? error.message : 'Network error');
            }

            // Retry logic
            const delay = baseDelay * Math.pow(2, attempt);
            console.log(`🢄🔐 Worker upload failed, retrying in ${delay}ms... (attempt ${attempt + 1}/${maxRetries + 1})`);
            await new Promise(resolve => setTimeout(resolve, delay));
        }
    }

    throw new RetryableUploadError('Maximum retries exceeded');
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
        console.log(`🢄🔐 Starting secure upload for: ${file.name}`);

        // Step 1: Calculate file MD5 hash, extract geolocation data, and get client key info
        const [fileMD5, fileGeo, keyInfo/*, deviceGeo*/] = await Promise.all([
            calculateFileMD5(file),
            extractGeolocationFromFile(file),
            clientCrypto.getPublicKeyInfo()
			//getCurrentLocation()
        ]);

        // Prefer file EXIF data over device location
        const geolocation = {
            latitude: fileGeo.latitude,// || deviceGeo?.latitude,
            longitude: fileGeo.longitude,// || deviceGeo?.longitude,
            altitude: fileGeo.altitude,// || deviceGeo?.altitude,
            bearing: fileGeo.bearing,
            captured_at: fileGeo.captured_at
        };

        // Step 2: Request upload authorization
        console.log(`🢄🔐 Requesting upload authorization for: ${file.name} (MD5: ${fileMD5})`);
        const authRequest: UploadAuthorizationRequest = {
            filename: file.name,
            file_size: file.size,
            content_type: file.type,
            file_md5: fileMD5,
            client_key_id: keyInfo.keyId,
            description,
            is_public: isPublic,
            ...geolocation
        };

        const authResponse = await requestUploadAuthorization(authRequest);

		console.debug('Authorization response:', JSON.stringify(authResponse));

        console.log(`🢄🔐 Upload authorized, photo_id: ${authResponse.photo_id}`);

        // Step 3: Generate client signature using authorization timestamp
        console.log(`🢄🔐 Generating client signature for: ${file.name}`);
        const signatureData = await generateClientSignature(authResponse.photo_id, file.name, authResponse.upload_authorized_at);

        // Step 4: Upload to worker (use URL from authorization response)
        console.log(`🢄🔐 Uploading to worker: ${file.name}`);
        const uploadResult = await uploadToWorker(
            file,
            authResponse.upload_jwt,
            signatureData.signature,
            authResponse.worker_url + '/upload'
        );

        console.log(`🢄🔐 Secure upload completed: ${file.name}`);
        return uploadResult;

    } catch (error) {
        console.error(`🢄🔐 Secure upload failed for ${file.name}:`, error);
        return {
            success: false,
            message: 'Upload failed',
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
    onProgress?: (completed: number, total: number, currentFile: string) => void,
    onError?: (file: File, errorMessage: string) => void
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
            // Call error callback immediately when file fails
            if (onError && result.error) {
                onError(file, result.error);
            }
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

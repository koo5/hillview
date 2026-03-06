// Service worker secure upload module that uses the async upload flow with client signatures
// This module is used by service workers to upload photos with proper authentication

import type { StoredPhoto } from './photoStorage';
import { clientCrypto } from '../clientCrypto';
import { backendUrl } from '$lib/config';
import { authStorage } from './authStorage';

const LOG_PREFIX = '🢄[SW SecureUpload]';

interface AuthorizeResponse {
    upload_jwt: string;
    photo_id: string;
    worker_url: string;
    expires_at: string;
    upload_authorized_at: number;
}

export class ServiceWorkerSecureUploader {
    async uploadPhoto(photo: StoredPhoto): Promise<{ success: boolean; photoId?: string; error?: string }> {
        console.log(`${LOG_PREFIX} Starting secure upload for photo ${photo.id}`);

        try {
            // Step 1: Get valid auth token (refreshes if needed)
            const authToken = await authStorage.getValidToken();
            if (!authToken) {
                return { success: false, error: 'No auth token available' };
            }

            // Step 2: Request upload authorization from API server
            const authResponse = await this.requestUploadAuthorization(authToken, photo);
            if (!authResponse) {
                return { success: false, error: 'Failed to get upload authorization' };
            }

            // Step 3: Upload to worker with client signature
            const uploadSuccess = await this.uploadToWorker(
                authResponse.upload_jwt,
                authResponse.photo_id,
                authResponse.worker_url,
                photo
            );

            if (uploadSuccess) {
                console.log(`${LOG_PREFIX} Photo ${photo.id} uploaded successfully as ${authResponse.photo_id}`);
                return { success: true, photoId: authResponse.photo_id };
            } else {
                return { success: false, error: 'Worker upload failed' };
            }

        } catch (error) {
            console.error(`${LOG_PREFIX} Upload error:`, error);
            return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
        }
    }

    private async requestUploadAuthorization(
        authToken: string,
        photo: StoredPhoto
    ): Promise<AuthorizeResponse | null> {
        try {
            // Get client public key info
            const keyInfo = await clientCrypto.getPublicKeyInfo();

            // Create file from blob for MD5 calculation
            const file = new File([photo.blob], `photo_${photo.id}.jpg`, {
                type: 'image/jpeg',
                lastModified: photo.metadata.captured_at
            });

            const md5Hash = await this.calculateFileMD5(file);

            const authRequest = {
                filename: file.name,
                filesize: file.size,
                md5_hash: md5Hash,
                client_public_key_pem: keyInfo.public_key_pem,
                client_public_key_id: keyInfo.key_id
            };

            const response = await fetch(`${backendUrl}/photos/authorize-upload`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(authRequest)
            });

            if (!response.ok) {
                console.error(`${LOG_PREFIX} Authorization failed:`, response.status);
                return null;
            }

            const result = await response.json();
            console.log(`${LOG_PREFIX} Got upload authorization for photo ${result.photo_id}`);
            return result;

        } catch (error) {
            console.error(`${LOG_PREFIX} Authorization error:`, error);
            return null;
        }
    }

    private async uploadToWorker(
        uploadJwt: string,
        photoId: string,
        workerUrl: string,
        photo: StoredPhoto
    ): Promise<boolean> {
        try {
            const timestamp = Date.now();
            const filename = `photo_${photo.id}.jpg`;

            // Create file from blob
            const file = new File([photo.blob], filename, {
                type: 'image/jpeg',
                lastModified: photo.metadata.captured_at
            });

            // Generate client signature
            const { signature, keyId } = await clientCrypto.signUploadData({
                photo_id: photoId,
                filename: filename,
                timestamp: timestamp
            });

            // Create form data with file and metadata
            const formData = new FormData();
            formData.append('file', file);
            formData.append('upload_jwt', uploadJwt);
            formData.append('client_signature', signature);
            formData.append('client_public_key_id', keyId);
            formData.append('auth_timestamp', timestamp.toString());

            // Add metadata as JSON (browser can't write EXIF)
            const metadata = {
                latitude: photo.metadata.location.latitude,
                longitude: photo.metadata.location.longitude,
                altitude: photo.metadata.location.altitude,
                bearing: photo.metadata.location.bearing,
                captured_at: new Date(photo.metadata.captured_at).toISOString(),
                orientation_code: photo.metadata.orientation_code,
                location_source: photo.metadata.location.location_source,
                bearing_source: photo.metadata.location.bearing_source,
                accuracy: photo.metadata.location.accuracy
            };
            formData.append('metadata', JSON.stringify(metadata));

            // Upload to worker
            const response = await fetch(`${workerUrl}/upload`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                console.error(`${LOG_PREFIX} Worker upload failed:`, response.status);
                return false;
            }

            const result = await response.json();
            console.log(`${LOG_PREFIX} Worker accepted upload:`, result);
            return true;

        } catch (error) {
            console.error(`${LOG_PREFIX} Worker upload error:`, error);
            return false;
        }
    }

    private async calculateFileMD5(file: File): Promise<string> {
        try {
            const buffer = await file.arrayBuffer();
            const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
        } catch (error) {
            console.error(`${LOG_PREFIX} Failed to calculate MD5:`, error);
            return '';
        }
    }
}

// Export singleton for service worker use
export const swSecureUploader = new ServiceWorkerSecureUploader();
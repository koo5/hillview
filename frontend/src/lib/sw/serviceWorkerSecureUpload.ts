// Service worker secure upload — thin wrapper over shared uploadProtocol.
// Uses authStorage for IndexedDB-based auth tokens (no DOM/Svelte dependencies).

import type { StoredPhoto } from '$lib/browser/photoStorage';
import { clientCrypto } from '$lib/clientCrypto';
import { authStorage } from '$lib/browser/authStorage';
import {
	calculateFileHash,
	generateClientSignature,
	requestUploadAuthorization,
	uploadToWorker,
	type AuthFetch,
	type UploadAuthorizationRequest
} from '$lib/uploadProtocol';

const LOG_PREFIX = '🢄[SW SecureUpload]';

/**
 * SW auth fetch: manually attach token from IndexedDB.
 * Unlike the main thread http client, the service worker has no interceptor,
 * so we attach the Authorization header ourselves.
 */
export const swAuthFetch: AuthFetch = async (url: string, init: RequestInit): Promise<Response> => {
	const token = await authStorage.getValidToken();
	if (!token) throw new Error('No auth token available');
	return fetch(url, {
		...init,
		headers: {
			...(init.headers as Record<string, string>),
			Authorization: `Bearer ${token}`
		}
	});
};

export class ServiceWorkerSecureUploader {
	async uploadPhoto(photo: StoredPhoto): Promise<{ success: boolean; photoId?: string; error?: string }> {
		console.log(`${LOG_PREFIX} Starting secure upload for photo ${photo.id}`);

		try {
			const filename = `photo_${photo.id}.jpg`;
			const file = new File([photo.blob], filename, {
				type: 'image/jpeg',
				lastModified: photo.metadata.captured_at
			});

			// Step 1: Calculate hash and get key info in parallel
			const [fileHash, keyInfo] = await Promise.all([
				calculateFileHash(file),
				clientCrypto.getPublicKeyInfo()
			]);

			// Step 2: Request upload authorization
			const authRequest: UploadAuthorizationRequest = {
				filename: file.name,
				file_size: file.size,
				content_type: file.type,
				file_md5: fileHash,
				client_key_id: keyInfo.key_id,
				is_public: true,
				latitude: photo.metadata.location.latitude,
				longitude: photo.metadata.location.longitude,
				altitude: photo.metadata.location.altitude ?? undefined,
				bearing: photo.metadata.location.bearing ?? undefined,
				captured_at: new Date(photo.metadata.captured_at).toISOString()
			};

			const authResponse = await requestUploadAuthorization(swAuthFetch, authRequest);
			console.log(`${LOG_PREFIX} Got upload authorization for photo ${authResponse.photo_id}`);

			// Step 3: Generate client signature using authorization timestamp (NOT Date.now())
			const signatureData = await generateClientSignature(
				authResponse.photo_id,
				file.name,
				authResponse.upload_authorized_at
			);

			// Step 4: Upload to worker with metadata
			const metadata = {
				latitude: photo.metadata.location.latitude,
				longitude: photo.metadata.location.longitude,
				altitude: photo.metadata.location.altitude,
				bearing: photo.metadata.location.bearing,
				captured_at: photo.metadata.captured_at,
				orientation_code: photo.metadata.orientation_code,
				location_source: photo.metadata.location.location_source,
				bearing_source: photo.metadata.location.bearing_source,
				accuracy: photo.metadata.location.accuracy
			};

			const result = await uploadToWorker(
				file,
				authResponse.upload_jwt,
				signatureData.signature,
				authResponse.worker_url,
				metadata
			);

			if (result.success) {
				console.log(`${LOG_PREFIX} Photo ${photo.id} uploaded successfully as ${authResponse.photo_id}`);
				return { success: true, photoId: authResponse.photo_id };
			} else {
				return { success: false, error: result.error || result.message };
			}
		} catch (error) {
			console.error(`${LOG_PREFIX} Upload error:`, error);
			return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
		}
	}
}

// Export singleton for service worker use
export const swSecureUploader = new ServiceWorkerSecureUploader();

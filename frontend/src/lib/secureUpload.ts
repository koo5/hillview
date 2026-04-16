/**
 * Secure Upload Service (Main Thread)
 *
 * High-level API for uploading photos from the main thread.
 * Uses shared uploadProtocol for the actual protocol logic.
 */

import { clientCrypto } from './clientCrypto';
import { http } from './http';
import {
	calculateFileHash,
	generateClientSignature,
	requestUploadAuthorization,
	uploadToWorker,
	type AuthFetch,
	type UploadAuthorizationRequest,
	type SecureUploadResult
} from './uploadProtocol';

// Re-export types and errors for consumers that import from secureUpload
export type { UploadAuthorizationRequest, UploadAuthorizationResponse, SecureUploadResult } from './uploadProtocol';
export { UploadError, NonRetryableUploadError, RetryableUploadError } from './uploadProtocol';

/**
 * Main-thread authFetch: delegates to http.post which auto-attaches auth via interceptor.
 * Wraps http.post to match the AuthFetch signature (url, RequestInit) => Response.
 */
export const mainThreadAuthFetch: AuthFetch = async (url: string, init: RequestInit): Promise<Response> => {
	// http.post already handles auth headers, JSON content-type, and token refresh.
	// We need to pass the raw body since http.post expects a data object for JSON.
	const data = init.body ? JSON.parse(init.body as string) : undefined;
	return http.post(url, data);
};

/**
 * Extract geolocation data from photo file EXIF or provided metadata
 */
async function extractGeolocationFromFile(file: File, providedMetadata?: any): Promise<{
	latitude?: number;
	longitude?: number;
	altitude?: number;
	bearing?: number;
	captured_at?: string;
}> {
	try {
		// If metadata is provided (from browser capture), use it
		if (providedMetadata) {
			return {
				latitude: providedMetadata.latitude,
				longitude: providedMetadata.longitude,
				altitude: providedMetadata.altitude,
				bearing: providedMetadata.bearing,
				captured_at: providedMetadata.captured_at ?
					(typeof providedMetadata.captured_at === 'number' ?
						new Date(providedMetadata.captured_at).toISOString() :
						providedMetadata.captured_at) :
					undefined
			};
		}

		// Otherwise, return empty and let the worker extract EXIF data
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
 * Perform secure upload of a single file
 */
export async function secureUploadFile(
	file: File,
	description?: string,
	isPublic: boolean = true,
	browserMetadata?: any,  // Metadata from browser capture that can't be written as EXIF
	license?: string        // License identifier (e.g. 'ccbysa4')
): Promise<SecureUploadResult> {
	try {
		console.log(`🢄🔐 Starting secure upload for: ${file.name}`);

		// Step 1: Calculate file MD5 hash, extract geolocation data, and get client key info
		const [fileMD5, fileGeo, keyInfo/*, deviceGeo*/] = await Promise.all([
			calculateFileHash(file),
			extractGeolocationFromFile(file, browserMetadata),
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
			client_key_id: keyInfo.key_id,
			description,
			is_public: isPublic,
			license,
			...geolocation
		};

		const authResponse = await requestUploadAuthorization(mainThreadAuthFetch, authRequest);

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
			authResponse.worker_url,
			browserMetadata  // Pass metadata for form parameters
		);

		console.log(`🢄🔐 Secure upload completed: ${file.name}`);

		// /upload_async returns {success: true} without photo_id —
		// photo_id comes from the authorization step.
		return {
			...uploadResult,
			photo_id: authResponse.photo_id
		};

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
	onProgress?: (completed: number, total: number, currentFile: string) => void,
	onError?: (file: File, errorMessage: string) => void,
	browserMetadata?: any,  // Metadata from browser capture that can't be written as EXIF
	license?: string        // License identifier (e.g. 'ccbysa4')
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

		const result = await secureUploadFile(file, description, isPublic, browserMetadata, license);
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

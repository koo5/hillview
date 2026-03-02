/**
 * Shared Upload Protocol
 *
 * Extracted from secureUpload.ts so both the main thread and service worker
 * can use the same correct protocol without duplicating logic.
 *
 * The protocol (matching backend Pydantic model + Kotlin client):
 * 1. Authorization: POST /photos/authorize-upload with file_size, file_md5, etc.
 *    JWT in Authorization header.
 * 2. Signing: JSON.stringify([filename, photo_id, upload_authorized_at])
 *    — timestamp from auth response, NOT Date.now()
 * 3. Worker upload: FormData with file + client_signature.
 *    JWT in Authorization header. No upload_jwt/auth_timestamp/client_public_key_id in FormData.
 */

import { clientCrypto } from './clientCrypto';
import { backendUrl } from './config';

// ── Types ──

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

// ── Errors ──

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

// ── Auth fetch type ──

/**
 * A fetch-like function that attaches authentication.
 * Main thread: wraps http client (auto-attaches token via interceptor)
 * Service worker: manually adds Authorization header from IndexedDB token
 */
export type AuthFetch = (url: string, init: RequestInit) => Promise<Response>;

// ── File hash ──

/**
 * Calculate MD5 hash of a file using crypto-js library.
 *
 * Backend field is called file_md5 and Kotlin uses real MD5.
 * Cross-platform dedup requires matching hashes, so we use MD5 everywhere.
 * crypto-js is pure JS — works in both main thread and service worker.
 */
export async function calculateFileHash(file: File): Promise<string> {
	const CryptoJS = await import('crypto-js');

	const buffer = await file.arrayBuffer();
	const wordArray = CryptoJS.lib.WordArray.create(buffer);

	const hash = CryptoJS.MD5(wordArray);
	return hash.toString();
}

// ── Client signature ──

/**
 * Generate client signature for upload using authorization timestamp.
 *
 * Signs: JSON.stringify([filename, photo_id, upload_authorized_at])
 * The timestamp MUST come from the auth response, not Date.now().
 */
export async function generateClientSignature(
	photoId: string,
	filename: string,
	authTimestamp: number
): Promise<{ signature: string; keyId: string }> {
	return clientCrypto.signUploadData({
		photo_id: photoId,
		filename: filename,
		timestamp: authTimestamp
	});
}

// ── Upload authorization ──

/**
 * Request upload authorization from API server with retry logic.
 *
 * Takes an authFetch callback for context flexibility:
 * - Main thread passes a wrapper around http.post
 * - Service worker passes a raw fetch wrapper with manual Authorization header
 */
export async function requestUploadAuthorization(
	authFetch: AuthFetch,
	request: UploadAuthorizationRequest
): Promise<UploadAuthorizationResponse> {
	const maxRetries = 3;
	const baseDelay = 1000;

	for (let attempt = 0; attempt <= maxRetries; attempt++) {
		try {
			const response = await authFetch(`${backendUrl}/photos/authorize-upload`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(request)
			});

			if (response.ok) {
				const responseData = await response.json();

				// Check for duplicates (non-retryable)
				if (responseData.duplicate) {
					throw new NonRetryableUploadError(
						`Duplicate file detected: ${responseData.message || 'This file has already been uploaded'}`
					);
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
				throw error instanceof RetryableUploadError
					? error
					: new RetryableUploadError(error instanceof Error ? error.message : 'Network error');
			}

			// Retry logic
			const delay = baseDelay * Math.pow(2, attempt);
			console.log(
				`🔐 Upload authorization failed, retrying in ${delay}ms... (attempt ${attempt + 1}/${maxRetries + 1})`
			);
			await new Promise((resolve) => setTimeout(resolve, delay));
		}
	}

	throw new RetryableUploadError('Maximum retries exceeded');
}

// ── Worker upload ──

/**
 * Upload file to worker with JWT in Authorization header and client_signature in FormData.
 * Includes health check + retry logic (3 attempts).
 */
export async function uploadToWorker(
	file: File,
	uploadJwt: string,
	signature: string,
	workerUrl?: string,
	browserMetadata?: any // Additional metadata that can't be in EXIF
): Promise<SecureUploadResult> {
	const maxRetries = 3;
	const baseDelay = 2000; // Longer delay for file uploads

	// Use configured worker URL or default to backend URL with worker port
	const workerEndpoint = workerUrl || `${backendUrl.replace(':8055', ':8056')}/upload`;
	const workerBase = workerEndpoint.replace(/\/upload$/, '');

	for (let attempt = 0; attempt <= maxRetries; attempt++) {
		try {
			// Pre-flight health check - wait for worker to be ready before uploading
			const healthCheck = await fetch(`${workerBase}/health`, {
				method: 'GET',
				signal: AbortSignal.timeout(10000)
			});
			if (!healthCheck.ok) {
				throw new RetryableUploadError(`Worker not ready: ${healthCheck.status}`);
			}

			const formData = new FormData();
			formData.append('file', file);
			formData.append('client_signature', signature);

			// If browser metadata is provided, add it as a JSON object
			// since browser can't write EXIF tags
			if (browserMetadata) {
				const metadataObj = {
					latitude: browserMetadata.latitude,
					longitude: browserMetadata.longitude,
					altitude: browserMetadata.altitude,
					bearing: browserMetadata.bearing,
					captured_at:
						typeof browserMetadata.captured_at === 'number'
							? new Date(browserMetadata.captured_at).toISOString()
							: browserMetadata.captured_at,
					orientation_code: browserMetadata.orientation_code,
					location_source: browserMetadata.location_source,
					bearing_source: browserMetadata.bearing_source,
					accuracy: browserMetadata.accuracy
				};

				// Remove undefined values
				const metadataRecord = metadataObj as Record<string, any>;
				Object.keys(metadataRecord).forEach((key) => {
					if (metadataRecord[key] === undefined || metadataRecord[key] === null) {
						delete metadataRecord[key];
					}
				});

				// Add as JSON string form field
				formData.append('metadata', JSON.stringify(metadataObj));
			}

			const response = await fetch(workerEndpoint, {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${uploadJwt}`
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
				throw error instanceof RetryableUploadError
					? error
					: new RetryableUploadError(error instanceof Error ? error.message : 'Network error');
			}

			// Retry logic
			const delay = baseDelay * Math.pow(2, attempt);
			console.log(
				`🔐 Worker upload failed, retrying in ${delay}ms... (attempt ${attempt + 1}/${maxRetries + 1})`
			);
			await new Promise((resolve) => setTimeout(resolve, delay));
		}
	}

	throw new RetryableUploadError('Maximum retries exceeded');
}

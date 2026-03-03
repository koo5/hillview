import { describe, it, expect, beforeEach, vi } from 'vitest';

// ── Mocks ──

vi.mock('$lib/clientCrypto', () => ({
	clientCrypto: {
		getPublicKeyInfo: vi.fn().mockResolvedValue({
			key_id: 'mock-key-id',
			public_key_pem: 'mock-pem'
		})
	}
}));

vi.mock('$lib/browser/authStorage', () => ({
	authStorage: {
		getValidToken: vi.fn().mockResolvedValue('mock-jwt-token')
	}
}));

vi.mock('$lib/uploadProtocol', async (importOriginal) => {
	const original = await importOriginal<typeof import('$lib/uploadProtocol')>();
	return {
		...original,
		calculateFileHash: vi.fn().mockResolvedValue('mock-md5-hash'),
		generateClientSignature: vi.fn().mockResolvedValue({
			signature: 'mock-signature',
			keyId: 'mock-key-id'
		}),
		requestUploadAuthorization: vi.fn().mockResolvedValue({
			upload_jwt: 'mock-upload-jwt',
			photo_id: 'photo-xyz',
			expires_at: new Date().toISOString(),
			worker_url: 'http://worker:8056',
			upload_authorized_at: 1700000000
		}),
		uploadToWorker: vi.fn().mockResolvedValue({
			success: true,
			message: 'Upload complete',
			photo_id: 'photo-xyz'
		})
	};
});

// ── Imports (after mocks) ──

import { ServiceWorkerSecureUploader } from './serviceWorkerSecureUpload';
import {
	calculateFileHash,
	generateClientSignature,
	requestUploadAuthorization,
	uploadToWorker
} from '$lib/uploadProtocol';
import { authStorage } from '$lib/browser/authStorage';
import type { StoredPhoto } from '$lib/browser/photoStorage';

const mockRequestAuth = vi.mocked(requestUploadAuthorization);
const mockUploadToWorker = vi.mocked(uploadToWorker);
const mockCalcHash = vi.mocked(calculateFileHash);
const mockGenSig = vi.mocked(generateClientSignature);
const mockGetToken = vi.mocked(authStorage.getValidToken);

// ── Helpers ──

function makeStoredPhoto(overrides: Partial<StoredPhoto> = {}): StoredPhoto {
	return {
		id: 'test-photo-1',
		blob: new Blob(['fake photo data'], { type: 'image/jpeg' }),
		width: 640,
		height: 480,
		metadata: {
			location: {
				latitude: 50.08,
				longitude: 14.42,
				altitude: 300,
				accuracy: 5,
				bearing: 90,
				location_source: 'gps',
				bearing_source: 'compass'
			},
			captured_at: 1700000000000,
			orientation_code: 1
		},
		status: 'pending',
		retry_count: 0,
		added_at: Date.now(),
		...overrides
	};
}

// ── Tests ──

describe('ServiceWorkerSecureUploader', () => {
	let uploader: ServiceWorkerSecureUploader;

	beforeEach(() => {
		vi.clearAllMocks();
		uploader = new ServiceWorkerSecureUploader();

		// Reset default implementations
		mockCalcHash.mockResolvedValue('mock-md5-hash');
		mockGenSig.mockResolvedValue({ signature: 'mock-signature', keyId: 'mock-key-id' });
		mockRequestAuth.mockResolvedValue({
			upload_jwt: 'mock-upload-jwt',
			photo_id: 'photo-xyz',
			expires_at: new Date().toISOString(),
			worker_url: 'http://worker:8056',
			upload_authorized_at: 1700000000
		});
		mockUploadToWorker.mockResolvedValue({
			success: true,
			message: 'Upload complete',
			photo_id: 'photo-xyz'
		});
		mockGetToken.mockResolvedValue('mock-jwt-token');
	});

	it('should construct File from StoredPhoto blob with correct name and type', async () => {
		const photo = makeStoredPhoto({ id: 'abc-123' });
		await uploader.uploadPhoto(photo);

		// calculateFileHash receives the constructed File
		const fileArg = mockCalcHash.mock.calls[0][0];
		expect(fileArg).toBeInstanceOf(File);
		expect(fileArg.name).toBe('photo_abc-123.jpg');
		expect(fileArg.type).toBe('image/jpeg');
	});

	it('should pass correct geo fields from photo metadata to auth request', async () => {
		const photo = makeStoredPhoto();
		await uploader.uploadPhoto(photo);

		const authRequest = mockRequestAuth.mock.calls[0][1];
		expect(authRequest.latitude).toBe(50.08);
		expect(authRequest.longitude).toBe(14.42);
		expect(authRequest.altitude).toBe(300);
		expect(authRequest.bearing).toBe(90);
		expect(authRequest.file_md5).toBe('mock-md5-hash');
		expect(authRequest.client_key_id).toBe('mock-key-id');
		expect(authRequest.is_public).toBe(true);
		expect(authRequest.captured_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
	});

	it('should use upload_authorized_at from auth response for signature', async () => {
		mockRequestAuth.mockResolvedValueOnce({
			upload_jwt: 'jwt',
			photo_id: 'p-999',
			expires_at: new Date().toISOString(),
			worker_url: 'http://w',
			upload_authorized_at: 9999999999
		});

		const photo = makeStoredPhoto();
		await uploader.uploadPhoto(photo);

		expect(mockGenSig).toHaveBeenCalledWith('p-999', expect.any(String), 9999999999);
	});

	it('should pass swAuthFetch that attaches Authorization header from authStorage', async () => {
		const photo = makeStoredPhoto();
		await uploader.uploadPhoto(photo);

		// The first arg to requestUploadAuthorization is the authFetch callback
		const authFetch = mockRequestAuth.mock.calls[0][0];

		// Mock global fetch for testing the authFetch callback
		const mockGlobalFetch = vi.mocked(fetch);
		mockGlobalFetch.mockResolvedValueOnce(
			new Response(JSON.stringify({ ok: true }), { status: 200 })
		);

		// Call the authFetch to verify it attaches the token
		await authFetch('http://test.com/api', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: '{}'
		});

		expect(mockGlobalFetch).toHaveBeenCalledWith('http://test.com/api', expect.objectContaining({
			headers: expect.objectContaining({
				Authorization: 'Bearer mock-jwt-token'
			})
		}));
	});

	it('should return { success: true, photoId } on successful upload', async () => {
		const photo = makeStoredPhoto();
		const result = await uploader.uploadPhoto(photo);

		expect(result.success).toBe(true);
		expect(result.photoId).toBe('photo-xyz');
		expect(result.error).toBeUndefined();
	});

	it('should return { success: false, error } when auth token is missing', async () => {
		mockGetToken.mockResolvedValueOnce(null);

		// The authFetch will throw, and uploadPhoto catches it
		mockRequestAuth.mockImplementationOnce(async (authFetch) => {
			// Simulate calling the authFetch which should throw
			await authFetch('http://test.com', { method: 'POST', headers: {}, body: '{}' });
			throw new Error('Should not reach here');
		});

		const photo = makeStoredPhoto();
		const result = await uploader.uploadPhoto(photo);

		expect(result.success).toBe(false);
		expect(result.error).toBe('No auth token available');
	});

	it('should return { success: false, error } when upload fails', async () => {
		mockUploadToWorker.mockResolvedValueOnce({
			success: false,
			message: 'Worker rejected upload',
			error: 'Invalid signature'
		});

		const photo = makeStoredPhoto();
		const result = await uploader.uploadPhoto(photo);

		expect(result.success).toBe(false);
		expect(result.error).toBe('Invalid signature');
	});
});

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

vi.mock('$lib/http', () => ({
	http: {
		post: vi.fn()
	}
}));

// Mock the uploadProtocol functions since they're tested separately
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
			upload_jwt: 'mock-jwt',
			photo_id: 'photo-abc',
			expires_at: new Date().toISOString(),
			worker_url: 'http://worker:8056',
			upload_authorized_at: 1700000000
		}),
		uploadToWorker: vi.fn().mockResolvedValue({
			success: true,
			message: 'Upload complete',
			photo_id: 'photo-abc'
		})
	};
});

// ── Imports (after mocks) ──

import { secureUploadFile, secureUploadFiles } from '$lib/secureUpload';
import {
	calculateFileHash,
	generateClientSignature,
	requestUploadAuthorization,
	uploadToWorker
} from '$lib/uploadProtocol';
import { http } from '$lib/http';

const mockRequestAuth = vi.mocked(requestUploadAuthorization);
const mockUploadToWorker = vi.mocked(uploadToWorker);
const mockCalcHash = vi.mocked(calculateFileHash);
const mockGenSig = vi.mocked(generateClientSignature);
const mockHttpPost = vi.mocked(http.post);

// ── Tests ──

describe('secureUpload', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		// Reset default implementations after clearAllMocks
		mockCalcHash.mockResolvedValue('mock-md5-hash');
		mockGenSig.mockResolvedValue({ signature: 'mock-signature', keyId: 'mock-key-id' });
		mockRequestAuth.mockResolvedValue({
			upload_jwt: 'mock-jwt',
			photo_id: 'photo-abc',
			expires_at: new Date().toISOString(),
			worker_url: 'http://worker:8056',
			upload_authorized_at: 1700000000
		});
		mockUploadToWorker.mockResolvedValue({
			success: true,
			message: 'Upload complete',
			photo_id: 'photo-abc'
		});
	});

	describe('secureUploadFile', () => {
		const file = new File(['photo data'], 'test.jpg', { type: 'image/jpeg' });

		it('should call protocol functions in correct order with correct args', async () => {
			await secureUploadFile(file, 'A photo', true);

			// 1. Calculate hash
			expect(mockCalcHash).toHaveBeenCalledWith(file);

			// 2. Request auth (first arg is the authFetch callback, second is the request)
			expect(mockRequestAuth).toHaveBeenCalledTimes(1);
			const authRequest = mockRequestAuth.mock.calls[0][1];
			expect(authRequest.filename).toBe('test.jpg');
			expect(authRequest.file_size).toBe(file.size);
			expect(authRequest.content_type).toBe('image/jpeg');
			expect(authRequest.file_md5).toBe('mock-md5-hash');
			expect(authRequest.client_key_id).toBe('mock-key-id');
			expect(authRequest.description).toBe('A photo');
			expect(authRequest.is_public).toBe(true);

			// 3. Generate signature with auth timestamp (not Date.now())
			expect(mockGenSig).toHaveBeenCalledWith('photo-abc', 'test.jpg', 1700000000);

			// 4. Upload to worker (uploadToWorker appends /upload internally)
			expect(mockUploadToWorker).toHaveBeenCalledWith(
				file,
				'mock-jwt',
				'mock-signature',
				'http://worker:8056',
				undefined // no browserMetadata
			);
		});

		it('should pass mainThreadAuthFetch that delegates to http.post', async () => {
			// Set up http.post mock
			mockHttpPost.mockResolvedValue(
				new Response(JSON.stringify({
					upload_jwt: 'jwt-from-post',
					photo_id: 'p-from-post',
					expires_at: new Date().toISOString(),
					worker_url: 'http://w:8056',
					upload_authorized_at: 99
				}), { status: 200 })
			);
			// Override the mock to actually call through so we can test the authFetch
			mockRequestAuth.mockImplementationOnce(async (authFetch, request) => {
				const resp = await authFetch('http://localhost:8055/api/photos/authorize-upload', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(request)
				});
				return resp.json();
			});

			await secureUploadFile(file);

			// http.post should have been called (mainThreadAuthFetch parses body and delegates)
			expect(mockHttpPost).toHaveBeenCalledTimes(1);
			const [url, data] = mockHttpPost.mock.calls[0];
			expect(url).toBe('http://localhost:8055/api/photos/authorize-upload');
			expect(data.filename).toBe('test.jpg');
		});

		it('should use upload_authorized_at from auth response for signature', async () => {
			mockRequestAuth.mockResolvedValueOnce({
				upload_jwt: 'jwt',
				photo_id: 'p-123',
				expires_at: new Date().toISOString(),
				worker_url: 'http://w',
				upload_authorized_at: 1234567890
			});

			await secureUploadFile(file);

			// The timestamp passed to generateClientSignature must be from auth response
			expect(mockGenSig).toHaveBeenCalledWith('p-123', 'test.jpg', 1234567890);
		});

		it('should return { success: false } on error', async () => {
			mockCalcHash.mockRejectedValueOnce(new Error('Hash failed'));

			const result = await secureUploadFile(file);

			expect(result.success).toBe(false);
			expect(result.error).toBe('Hash failed');
		});
	});

	describe('secureUploadFiles', () => {
		it('should upload each file sequentially and return counts', async () => {
			const files = [
				new File(['a'], 'a.jpg', { type: 'image/jpeg' }),
				new File(['b'], 'b.jpg', { type: 'image/jpeg' }),
				new File(['c'], 'c.jpg', { type: 'image/jpeg' })
			];

			const result = await secureUploadFiles(files);

			expect(result.successCount).toBe(3);
			expect(result.errorCount).toBe(0);
			expect(result.results).toHaveLength(3);
			expect(mockCalcHash).toHaveBeenCalledTimes(3);
		});

		it('should report progress via callback', async () => {
			const files = [
				new File(['a'], 'a.jpg', { type: 'image/jpeg' }),
				new File(['b'], 'b.jpg', { type: 'image/jpeg' })
			];
			const onProgress = vi.fn();

			await secureUploadFiles(files, undefined, true, onProgress);

			// Called for each file start + final
			expect(onProgress).toHaveBeenCalledWith(0, 2, 'a.jpg');
			expect(onProgress).toHaveBeenCalledWith(1, 2, 'b.jpg');
			expect(onProgress).toHaveBeenCalledWith(2, 2, ''); // final
		});

		it('should call error callback on failure and count errors', async () => {
			const files = [
				new File(['a'], 'good.jpg', { type: 'image/jpeg' }),
				new File(['b'], 'bad.jpg', { type: 'image/jpeg' })
			];
			const onError = vi.fn();

			// Second file fails
			mockCalcHash
				.mockResolvedValueOnce('hash-a')
				.mockRejectedValueOnce(new Error('Hash failed'));

			const result = await secureUploadFiles(files, undefined, true, undefined, onError);

			expect(result.successCount).toBe(1);
			expect(result.errorCount).toBe(1);
			expect(onError).toHaveBeenCalledTimes(1);
			expect(onError).toHaveBeenCalledWith(files[1], 'Hash failed');
		});
	});
});

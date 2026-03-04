import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// ── Mocks (hoisted before imports) ──

vi.mock('$lib/clientCrypto', () => ({
	clientCrypto: {
		signUploadData: vi.fn().mockResolvedValue({
			signature: 'mock-signature-base64',
			keyId: 'mock-key-id-123'
		})
	}
}));

vi.mock('crypto-js', () => {
	const mockHash = {
		toString: vi.fn(() => 'abcdef1234567890abcdef1234567890')
	};
	return {
		default: {
			lib: {
				WordArray: {
					create: vi.fn(() => mockHash)
				}
			},
			MD5: vi.fn(() => mockHash)
		},
		lib: {
			WordArray: {
				create: vi.fn(() => mockHash)
			}
		},
		MD5: vi.fn(() => mockHash)
	};
});

vi.mock('$lib/config', () => ({
	backendUrl: 'http://localhost:8055/api'
}));

// ── Imports (after mocks) ──

import {
	calculateFileHash,
	generateClientSignature,
	requestUploadAuthorization,
	uploadToWorker,
	NonRetryableUploadError,
	RetryableUploadError,
	type AuthFetch,
	type UploadAuthorizationRequest
} from '$lib/uploadProtocol';
import { clientCrypto } from '$lib/clientCrypto';

// ── Helpers ──

const mockFetch = vi.mocked(fetch);

function makeAuthResponse(overrides = {}) {
	return {
		upload_jwt: 'mock-upload-jwt',
		photo_id: 'photo-123',
		expires_at: new Date().toISOString(),
		worker_url: 'http://worker:8056',
		upload_authorized_at: 1700000000,
		...overrides
	};
}

function okResponse(data: any): Response {
	return new Response(JSON.stringify(data), { status: 200 });
}

function errorResponse(status: number, detail?: string): Response {
	return new Response(JSON.stringify({ detail: detail || `Error ${status}` }), { status });
}

const sampleRequest: UploadAuthorizationRequest = {
	filename: 'test.jpg',
	file_size: 1024,
	content_type: 'image/jpeg',
	file_md5: 'abcdef1234567890abcdef1234567890',
	client_key_id: 'key-123',
	is_public: true
};

// ── Tests ──

describe('uploadProtocol', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	// ── calculateFileHash ──

	describe('calculateFileHash', () => {
		it('should return MD5 hex string from crypto-js', async () => {
			const file = new File(['test content'], 'test.jpg', { type: 'image/jpeg' });
			const hash = await calculateFileHash(file);
			expect(hash).toBe('abcdef1234567890abcdef1234567890');
		});

		it('should read file as ArrayBuffer and pass to WordArray.create', async () => {
			const CryptoJS = (await import('crypto-js')).default;
			const file = new File(['hello'], 'test.jpg');
			await calculateFileHash(file);
			expect(CryptoJS.lib.WordArray.create).toHaveBeenCalled();
			expect(CryptoJS.MD5).toHaveBeenCalled();
		});

		it('should propagate errors without fallback', async () => {
			const CryptoJS = (await import('crypto-js')).default;
			vi.mocked(CryptoJS.MD5).mockImplementationOnce(() => {
				throw new Error('MD5 calculation failed');
			});
			const file = new File(['test'], 'test.jpg');
			await expect(calculateFileHash(file)).rejects.toThrow('MD5 calculation failed');
		});
	});

	// ── generateClientSignature ──

	describe('generateClientSignature', () => {
		it('should pass correct args to clientCrypto.signUploadData', async () => {
			await generateClientSignature('photo-456', 'image.jpg', 1700000000);

			expect(clientCrypto.signUploadData).toHaveBeenCalledWith({
				photo_id: 'photo-456',
				filename: 'image.jpg',
				timestamp: 1700000000
			});
		});

		it('should return signature and keyId from crypto module', async () => {
			const result = await generateClientSignature('photo-456', 'image.jpg', 1700000000);
			expect(result).toEqual({
				signature: 'mock-signature-base64',
				keyId: 'mock-key-id-123'
			});
		});
	});

	// ── requestUploadAuthorization ──

	describe('requestUploadAuthorization', () => {
		it('should call authFetch with correct URL, method, headers, and body', async () => {
			const mockAuthFetch: AuthFetch = vi.fn().mockResolvedValue(okResponse(makeAuthResponse()));

			await requestUploadAuthorization(mockAuthFetch, sampleRequest);

			expect(mockAuthFetch).toHaveBeenCalledWith(
				'http://localhost:8055/api/photos/authorize-upload',
				{
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(sampleRequest)
				}
			);
		});

		it('should return parsed response on 200 OK', async () => {
			const authResponse = makeAuthResponse();
			const mockAuthFetch: AuthFetch = vi.fn().mockResolvedValue(okResponse(authResponse));

			const result = await requestUploadAuthorization(mockAuthFetch, sampleRequest);

			expect(result.photo_id).toBe('photo-123');
			expect(result.upload_jwt).toBe('mock-upload-jwt');
			expect(result.upload_authorized_at).toBe(1700000000);
		});

		it('should throw NonRetryableUploadError on duplicate response', async () => {
			const mockAuthFetch: AuthFetch = vi.fn().mockResolvedValue(
				okResponse({ ...makeAuthResponse(), duplicate: true, message: 'Already uploaded' })
			);

			try {
				await requestUploadAuthorization(mockAuthFetch, sampleRequest);
				expect.unreachable('Should have thrown');
			} catch (error) {
				expect(error).toBeInstanceOf(NonRetryableUploadError);
				expect((error as Error).message).toMatch(/Duplicate file detected/);
			}
		});

		it('should throw NonRetryableUploadError on 4xx errors without retry', async () => {
			const mockAuthFetch: AuthFetch = vi.fn().mockResolvedValue(errorResponse(400, 'Bad request'));

			await expect(requestUploadAuthorization(mockAuthFetch, sampleRequest)).rejects.toThrow(
				NonRetryableUploadError
			);
			// Should NOT retry — only 1 call
			expect(mockAuthFetch).toHaveBeenCalledTimes(1);
		});

		it('should retry on 5xx errors with exponential backoff', async () => {
			vi.spyOn(globalThis, 'setTimeout').mockImplementation((fn: any) => {
				fn();
				return 0 as any;
			});

			const mockAuthFetch: AuthFetch = vi
				.fn()
				.mockResolvedValueOnce(errorResponse(500, 'Server error'))
				.mockResolvedValueOnce(okResponse(makeAuthResponse()));

			const result = await requestUploadAuthorization(mockAuthFetch, sampleRequest);
			expect(result.photo_id).toBe('photo-123');
			expect(mockAuthFetch).toHaveBeenCalledTimes(2);

			vi.mocked(globalThis.setTimeout).mockRestore();
		});

		it('should retry on network errors up to maxRetries then throw RetryableUploadError', async () => {
			// Mock setTimeout to execute immediately (avoid real delays)
			const origSetTimeout = globalThis.setTimeout;
			vi.spyOn(globalThis, 'setTimeout').mockImplementation((fn: any) => {
				fn();
				return 0 as any;
			});

			const mockAuthFetch: AuthFetch = vi.fn().mockImplementation(async () => {
				throw new Error('Network error');
			});

			try {
				await requestUploadAuthorization(mockAuthFetch, sampleRequest);
				expect.unreachable('Should have thrown');
			} catch (error) {
				expect(error).toBeInstanceOf(RetryableUploadError);
				expect((error as Error).message).toBe('Network error');
			}
			// 4 total attempts (0, 1, 2, 3)
			expect(mockAuthFetch).toHaveBeenCalledTimes(4);

			vi.mocked(globalThis.setTimeout).mockRestore();
		});

		it('should pass through TokenExpiredError without wrapping', async () => {
			const tokenExpiredError = new Error('Token expired');
			tokenExpiredError.name = 'TokenExpiredError';

			const mockAuthFetch: AuthFetch = vi.fn().mockRejectedValue(tokenExpiredError);

			await expect(requestUploadAuthorization(mockAuthFetch, sampleRequest)).rejects.toThrow('Token expired');
			// Should NOT retry — only 1 call
			expect(mockAuthFetch).toHaveBeenCalledTimes(1);
		});
	});

	// ── uploadToWorker ──

	describe('uploadToWorker', () => {
		const file = new File(['photo data'], 'test.jpg', { type: 'image/jpeg' });
		const workerUrl = 'http://worker:8056';
		const uploadJwt = 'mock-upload-jwt';
		const signature = 'mock-signature';

		it('should perform health check before upload', async () => {
			mockFetch
				.mockResolvedValueOnce(okResponse({ status: 'ok' })) // health check
				.mockResolvedValueOnce(
					okResponse({ success: true, message: 'Uploaded', photo_id: 'p-1' })
				); // upload

			await uploadToWorker(file, uploadJwt, signature, workerUrl);

			expect(mockFetch).toHaveBeenCalledTimes(2);
			// First call = health check
			expect(mockFetch.mock.calls[0][0]).toBe('http://worker:8056/health');
			expect(mockFetch.mock.calls[0][1]).toMatchObject({ method: 'GET' });
		});

		it('should send JWT in Authorization header, not in FormData', async () => {
			mockFetch
				.mockResolvedValueOnce(okResponse({ status: 'ok' })) // health
				.mockResolvedValueOnce(
					okResponse({ success: true, message: 'Uploaded', photo_id: 'p-1' })
				); // upload

			await uploadToWorker(file, uploadJwt, signature, workerUrl);

			// Second call = upload
			const uploadCall = mockFetch.mock.calls[1];
			expect(uploadCall[1]?.headers).toEqual({ Authorization: 'Bearer mock-upload-jwt' });

			// FormData should NOT contain upload_jwt
			const formData = uploadCall[1]?.body as FormData;
			expect(formData.has('upload_jwt')).toBe(false);
			expect(formData.has('client_signature')).toBe(true);
			expect(formData.get('client_signature')).toBe('mock-signature');
		});

		it('should include file in FormData', async () => {
			mockFetch
				.mockResolvedValueOnce(okResponse({ status: 'ok' }))
				.mockResolvedValueOnce(
					okResponse({ success: true, message: 'Uploaded', photo_id: 'p-1' })
				);

			await uploadToWorker(file, uploadJwt, signature, workerUrl);

			const formData = mockFetch.mock.calls[1][1]?.body as FormData;
			expect(formData.has('file')).toBe(true);
		});

		it('should append metadata as JSON when browserMetadata is provided', async () => {
			mockFetch
				.mockResolvedValueOnce(okResponse({ status: 'ok' }))
				.mockResolvedValueOnce(
					okResponse({ success: true, message: 'Uploaded', photo_id: 'p-1' })
				);

			const metadata = {
				latitude: 50.08,
				longitude: 14.42,
				altitude: undefined,
				bearing: null,
				captured_at: 1700000000,
				orientation_code: 1,
				location_source: 'gps',
				bearing_source: 'compass',
				accuracy: 5
			};

			await uploadToWorker(file, uploadJwt, signature, workerUrl, metadata);

			const formData = mockFetch.mock.calls[1][1]?.body as FormData;
			expect(formData.has('metadata')).toBe(true);

			const parsed = JSON.parse(formData.get('metadata') as string);
			expect(parsed.latitude).toBe(50.08);
			expect(parsed.longitude).toBe(14.42);
			// captured_at should be converted to ISO string since it's a number
			expect(parsed.captured_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
		});

		it('should return parsed response on 200 OK', async () => {
			mockFetch
				.mockResolvedValueOnce(okResponse({ status: 'ok' }))
				.mockResolvedValueOnce(
					okResponse({ success: true, message: 'Upload complete', photo_id: 'p-1' })
				);

			const result = await uploadToWorker(file, uploadJwt, signature, workerUrl);
			expect(result.success).toBe(true);
			expect(result.photo_id).toBe('p-1');
		});

		it('should throw NonRetryableUploadError on 4xx upload response', async () => {
			mockFetch
				.mockResolvedValueOnce(okResponse({ status: 'ok' })) // health OK
				.mockResolvedValueOnce(errorResponse(403, 'Forbidden'));

			await expect(uploadToWorker(file, uploadJwt, signature, workerUrl)).rejects.toThrow(
				NonRetryableUploadError
			);
		});

		it('should retry on health check failure', async () => {
			vi.spyOn(globalThis, 'setTimeout').mockImplementation((fn: any) => {
				fn();
				return 0 as any;
			});

			mockFetch
				.mockResolvedValueOnce(errorResponse(503, 'Unavailable')) // health fail
				// retry
				.mockResolvedValueOnce(okResponse({ status: 'ok' })) // health OK
				.mockResolvedValueOnce(
					okResponse({ success: true, message: 'Uploaded', photo_id: 'p-1' })
				);

			const result = await uploadToWorker(file, uploadJwt, signature, workerUrl);
			expect(result.success).toBe(true);
			expect(mockFetch).toHaveBeenCalledTimes(3);

			vi.mocked(globalThis.setTimeout).mockRestore();
		});
	});
});

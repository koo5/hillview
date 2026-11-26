// Both uploaders send one stored capture with the SAME metadata. They used to
// build it from two key lists, and the Background Sync one never sent
// alt_location (confirmed 2026-11-16); buildUploadMetadata in uploadProtocol.ts
// is now the only list. This drives one photo through each path and compares
// what each hands to the worker.
import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('$lib/browser/settingsIndexedDb', () => ({
	readSettings: vi.fn().mockResolvedValue({ auto_upload_license: 'ccbysa4' }),
	writeSettings: vi.fn().mockResolvedValue(undefined)
}));

vi.mock('$lib/clientCrypto', () => ({
	clientCrypto: {
		getPublicKeyInfo: vi.fn().mockResolvedValue({ key_id: 'mock-key-id', public_key_pem: 'mock-pem' })
	}
}));

vi.mock('$lib/browser/authStorage', () => ({
	authStorage: { getValidToken: vi.fn().mockResolvedValue('mock-jwt-token') }
}));

vi.mock('$lib/uploadProtocol', async (importOriginal) => {
	const original = await importOriginal<typeof import('$lib/uploadProtocol')>();
	return {
		...original, // buildUploadMetadata stays real
		calculateFileHash: vi.fn().mockResolvedValue('mock-md5-hash'),
		generateClientSignature: vi.fn().mockResolvedValue({ signature: 'sig', keyId: 'mock-key-id' }),
		requestUploadAuthorization: vi.fn().mockResolvedValue({
			upload_jwt: 'jwt',
			photo_id: 'photo-xyz',
			expires_at: new Date().toISOString(),
			worker_url: 'http://worker:8056',
			upload_authorized_at: 1700000000
		}),
		uploadToWorker: vi.fn().mockResolvedValue({ success: true, message: 'ok' })
	};
});

vi.mock('$lib/secureUpload', () => ({
	secureUploadFile: vi.fn().mockResolvedValue({ success: true, photo_id: 'photo-xyz' }),
	mainThreadAuthFetch: vi.fn()
}));

import { swSecureUploader } from '$lib/sw/serviceWorkerSecureUpload';
import { foregroundUploader } from './photoSync';
import { secureUploadFile } from '$lib/secureUpload';
import { buildUploadMetadata, uploadToWorker } from '$lib/uploadProtocol';
import type { StoredPhoto } from './photoStorage';

const inertial = {
	gravity: [0.68147, 9.745536, 0.854699] as [number, number, number],
	age_ms: 40,
	gravity_source: 'deviceorientation' as const,
	sample_count: 18,
	window_ms: 300,
	gravity_spread_deg: 0.8
};

function storedPhoto(overrides: Partial<StoredPhoto['metadata']> = {}): StoredPhoto {
	return {
		id: 'capture-1',
		blob: new Blob(['jpeg'], { type: 'image/jpeg' }),
		width: 480,
		height: 640,
		metadata: {
			location: {
				latitude: 50.08,
				longitude: 14.42,
				altitude: null,
				accuracy: 5,
				bearing: 141,
				location_source: 'map',
				bearing_source: 'map',
				alt_location: { lat: 50.081, lng: 14.421, ts: 1700000000000, accuracy: 4, source: 'gps-background' }
			},
			captured_at: 1700000000123,
			orientation_code: 1,
			inertial,
			...overrides
		},
		license: 'ccbysa4',
		panoramax_share: true,
		status: 'pending',
		deleted: false,
		retry_count: 0,
		added_at: 1700000000200
	};
}

async function viaForeground(photo: StoredPhoto) {
	vi.mocked(secureUploadFile).mockClear();
	await foregroundUploader(photo);
	return vi.mocked(secureUploadFile).mock.calls[0][3];
}

async function viaServiceWorker(photo: StoredPhoto) {
	vi.mocked(uploadToWorker).mockClear();
	await swSecureUploader.uploadPhoto(photo);
	return vi.mocked(uploadToWorker).mock.calls[0][4];
}

describe('upload metadata, one builder for both uploaders', () => {
	beforeEach(() => vi.clearAllMocks());

	it('sends the same metadata through Background Sync as through the foreground', async () => {
		const photo = storedPhoto();
		const foreground = await viaForeground(photo);
		const background = await viaServiceWorker(photo);
		expect(background).toEqual(foreground);
		expect(foreground).toEqual(buildUploadMetadata(photo));
	});

	it('carries the gravity stamp and the alternative location', async () => {
		const sent = await viaServiceWorker(storedPhoto());
		expect(sent.inertial).toEqual(inertial);
		expect(sent.alt_location).toEqual(expect.objectContaining({ source: 'gps-background' }));
		expect(sent.captured_at).toBe('2023-11-14T22:13:20.123Z');
		// absent, not null
		expect('altitude' in sent).toBe(false);
	});

	it('leaves out what was not measured', async () => {
		const photo = storedPhoto({ inertial: null });
		photo.metadata.location.alt_location = null;
		const foreground = await viaForeground(photo);
		expect(await viaServiceWorker(photo)).toEqual(foreground);
		expect('inertial' in foreground).toBe(false);
		expect('alt_location' in foreground).toBe(false);
	});

	it('reads a capture stored before the stamp existed', () => {
		const photo = storedPhoto();
		delete (photo.metadata as Partial<StoredPhoto['metadata']>).inertial;
		expect(buildUploadMetadata(photo)).toEqual({
			latitude: 50.08,
			longitude: 14.42,
			bearing: 141,
			captured_at: '2023-11-14T22:13:20.123Z',
			orientation_code: 1,
			location_source: 'map',
			bearing_source: 'map',
			accuracy: 5,
			alt_location: photo.metadata.location.alt_location
		});
	});
});

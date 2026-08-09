import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the modules shareUtils depends on
vi.mock('$lib/tauri', () => ({
	TAURI: false,
	BROWSER: true,
}));

vi.mock('$lib/urlUtils', () => ({
	constructShareUrl: vi.fn(
		(photo: any, bounds?: any) =>
			`https://hillview.cz/?lat=${photo.coord?.lat || 0}&lon=${photo.coord?.lng || 0}&zoom=18${bounds ? `&x1=${bounds.x1}` : ''}`
	),
	extractCoordinates: vi.fn((photo: any) =>
		photo?.coord ? { lat: photo.coord.lat, lon: photo.coord.lng, bearing: photo.bearing } : null
	),
	HILLVIEW_BASE_URL: 'https://hillview.cz',
}));

vi.mock('$lib/mapState', async () => {
	const { writable } = await import('svelte/store');
	return { spatialState: writable({ zoom: 18 }) };
});

// Default: minting fails, so sharePhoto falls back to the long constructShareUrl form
vi.mock('$lib/http', () => ({
	http: { post: vi.fn().mockRejectedValue(new Error('backend unavailable')) },
}));

vi.mock('@tauri-apps/api/core', () => ({
	invoke: vi.fn(),
}));

import { sharePhoto } from './shareUtils';
import { http } from '$lib/http';

describe('shareUtils', () => {
	let writeTextSpy: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		writeTextSpy = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', {
			value: { writeText: writeTextSpy },
			writable: true,
			configurable: true,
		});
	});

	describe('sharePhoto', () => {
		it('returns empty result for null photo', async () => {
			const result = await sharePhoto(null);
			expect(result).toEqual({ message: '', error: false });
		});

		it('copies share URL to clipboard on web', async () => {
			const photo = {
				uid: 'hillview-123',
				coord: { lat: 50.0, lng: 14.0 },
			};
			const result = await sharePhoto(photo);
			expect(writeTextSpy).toHaveBeenCalledOnce();
			const copied = writeTextSpy.mock.calls[0][0];
			expect(copied).toContain('hillview.cz');
			expect(result.message).toBe('Share link copied to clipboard!');
			expect(result.error).toBe(false);
		});

		it('returns error result when clipboard fails', async () => {
			writeTextSpy.mockRejectedValue(new Error('Clipboard denied'));
			const photo = {
				uid: 'hillview-123',
				coord: { lat: 50.0, lng: 14.0 },
			};
			const result = await sharePhoto(photo);
			expect(result.error).toBe(true);
			expect(result.message).toBe('Failed to share photo');
		});

		it('uses the minted short link when the backend responds', async () => {
			vi.mocked(http.post).mockResolvedValueOnce({
				ok: true,
				json: async () => ({ slug: '7-vysoky-kotel', target: '/?lat=50&lon=14&zoom=18&photo=hillview-123' }),
			} as Response);
			const photo = {
				uid: 'hillview-123',
				coord: { lat: 50.0, lng: 14.0 },
			};
			const result = await sharePhoto(photo);
			expect(writeTextSpy).toHaveBeenCalledOnce();
			expect(writeTextSpy.mock.calls[0][0]).toBe('https://hillview.cz/shared/7-vysoky-kotel');
			expect(result.error).toBe(false);
		});

		it('falls back to the long URL when minting fails', async () => {
			const photo = {
				uid: 'hillview-123',
				coord: { lat: 50.0, lng: 14.0 },
			};
			const result = await sharePhoto(photo);
			expect(writeTextSpy).toHaveBeenCalledOnce();
			expect(writeTextSpy.mock.calls[0][0]).toContain('?lat=50');
			expect(result.error).toBe(false);
		});

		it('passes zoomViewBounds through to URL construction', async () => {
			const { constructShareUrl } = await import('$lib/urlUtils');
			const photo = {
				uid: 'hillview-123',
				coord: { lat: 50.0, lng: 14.0 },
			};
			const bounds = { x1: 0.1, y1: 0.2, x2: 0.8, y2: 0.9 };
			await sharePhoto(photo, bounds);
			expect(constructShareUrl).toHaveBeenCalledWith(photo, bounds);
		});
	});

	describe('getUserName (indirectly via share text)', () => {
		it('includes creator username in share text when available', async () => {
			// We can verify the share text by checking what's passed to clipboard
			// In web mode, shareUrl is copied directly (not the text), so this
			// is more of a smoke test that it doesn't crash with various photo shapes
			const photoWithCreator = {
				uid: 'test-1',
				coord: { lat: 50.0, lng: 14.0 },
				creator: { username: 'testuser' },
			};
			const result = await sharePhoto(photoWithCreator);
			expect(result.error).toBe(false);
		});

		it('uses owner_username fallback', async () => {
			const photoWithOwner = {
				uid: 'test-2',
				coord: { lat: 50.0, lng: 14.0 },
				owner_username: 'someowner',
			};
			const result = await sharePhoto(photoWithOwner);
			expect(result.error).toBe(false);
		});
	});
});

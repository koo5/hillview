import { describe, expect, it, vi } from 'vitest';
import { loadPhotoPreview } from './photoPreview.server';

vi.mock('$lib/config.server', () => ({ backendInternalUrl: 'http://api.test/api' }));

describe('public share preview loading', () => {
	it('uses the site card for external sources without fetching a Hillview photo', async () => {
		const fetch = vi.fn();
		expect(await loadPhotoPreview('mapillary-123', fetch, {}))
			.toEqual({ photo: null, annotations: [] });
		expect(fetch).not.toHaveBeenCalled();
	});

	it('keeps the preview usable when the photo is unavailable', async () => {
		const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 404 }));
		expect(await loadPhotoPreview('hillview-missing', fetch, {}))
			.toEqual({ photo: null, annotations: [] });
	});

	it('keeps the photo card when annotations fail and forwards the viewer ticket', async () => {
		const photo = { uid: 'hillview-photo', title: 'A view' };
		const fetch = vi.fn()
			.mockResolvedValueOnce(Response.json(photo))
			.mockResolvedValueOnce(new Response(null, { status: 503 }));
		expect(await loadPhotoPreview('hillview-photo', fetch, { ssrTicket: 'ticket' }))
			.toEqual({ photo, annotations: [] });
		expect(fetch).toHaveBeenCalledWith('http://api.test/api/photos/public/hillview-photo', {
			headers: { Authorization: 'Bearer ticket' }
		});
		expect(fetch).toHaveBeenCalledWith('http://api.test/api/annotations/photos/photo', {
			headers: { Authorization: 'Bearer ticket' }
		});
	});

	it('falls back to the site card on network failure', async () => {
		const fetch = vi.fn().mockRejectedValue(new Error('offline'));
		expect(await loadPhotoPreview('hillview-photo', fetch, {}))
			.toEqual({ photo: null, annotations: [] });
	});
});

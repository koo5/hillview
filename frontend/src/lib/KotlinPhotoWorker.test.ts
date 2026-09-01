/**
 * KotlinPhotoWorker relays the Kotlin PhotoWorkerService's events to the main
 * thread. Kotlin now publishes several photosUpdates per area (one per source
 * as it lands, then the settled set): all of them for the current generation
 * must reach onmessage, with `complete` intact; stale generations are dropped.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { writable } from 'svelte/store';
import { invoke } from '@tauri-apps/api/core';

const { handlers } = vi.hoisted(() => ({ handlers: new Map<string, (m: any) => void>() }));

vi.mock('./mapState', () => ({ spatialState: writable({}) }));
vi.mock('./data.svelte', () => ({
	sources: writable([]),
	sourceLoadingStatus: writable({}),
	maxPhotosInArea: writable(100)
}));
vi.mock('./components/filters-modal/filtersStore', () => ({ buildFiltersQueryParam: () => null }));
vi.mock('./KotlinMessageQueue', () => ({
	kotlinMessageQueue: {
		on: (type: string, handler: (m: any) => void) => handlers.set(type, handler),
		off: vi.fn(),
		startPolling: vi.fn()
	}
}));

import { KotlinPhotoWorker } from './KotlinPhotoWorker';

const update = (generation: number, complete: boolean, ids: string[]) => ({
	payload: {
		type: 'photosUpdate',
		generation,
		complete,
		photos_in_area: JSON.stringify(ids.map(id => ({ id, uid: `hillview-${id}` }))),
		photos_in_range: '[]',
		timestamp: 1
	}
});

describe('KotlinPhotoWorker photosUpdate relay', () => {
	let worker: KotlinPhotoWorker;
	let received: any[];

	beforeEach(async () => {
		handlers.clear();
		vi.mocked(invoke).mockResolvedValue({ success: true } as any);
		worker = new KotlinPhotoWorker();
		await worker.initialize();
		received = [];
		worker.onmessage = (e) => received.push(e.data);
	});

	it('relays a partial and then the settled publish of the same generation, complete flag intact', () => {
		const emit = handlers.get('photo-worker-update')!;
		emit(update(0, false, ['a']));
		emit(update(0, true, ['a', 'b']));

		expect(received.map(m => [m.type, m.complete, m.photos_in_area.map((p: any) => p.id)])).toEqual([
			['photosUpdate', false, ['a']],
			['photosUpdate', true, ['a', 'b']]
		]);
	});

	it('forwards removal / panoramax-invalidate messages to Kotlin (they used to fail validation)', async () => {
		const sentTypes = () => vi.mocked(invoke).mock.calls
			.filter(([cmd]) => cmd === 'plugin:hillview|photo_worker_process')
			.map(([, args]: any) => JSON.parse(args.messageJson).type);

		worker.postMessage({ frontendMessageId: 'f1', type: 'removePhoto', data: { photoId: 'p', source: 'panoramax' } });
		worker.postMessage({ frontendMessageId: 'f2', type: 'removeUserPhotos', data: { userId: 'u', source: 'panoramax' } });
		worker.postMessage({ frontendMessageId: 'f3', type: 'panoramaxHiddenInvalidate' });
		await Promise.resolve();

		expect(sentTypes()).toEqual(expect.arrayContaining(['REMOVE_PHOTO', 'REMOVE_USER_PHOTOS', 'PANORAMAX_HIDDEN_INVALIDATE']));
	});

	it('drops publishes from a generation superseded by abortArea', async () => {
		const emit = handlers.get('photo-worker-update')!;
		worker.postMessage({ frontendMessageId: 'f1', type: 'abortArea' });
		await Promise.resolve();

		emit(update(0, false, ['stale']));
		emit(update(1, false, ['fresh']));
		emit(update(1, true, ['fresh', 'settled']));

		expect(received.map(m => m.photos_in_area.map((p: any) => p.id))).toEqual([['fresh'], ['fresh', 'settled']]);
	});
});

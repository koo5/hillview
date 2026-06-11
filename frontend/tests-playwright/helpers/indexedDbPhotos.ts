/**
 * Shared IndexedDB photo helpers for Playwright tests.
 *
 * These run inside page.evaluate() to query the HillviewPhotoDB
 * that the app uses for browser-captured photos.
 *
 * Note: We omit the version parameter in indexedDB.open() so we
 * open the existing DB at whatever version the app created (currently v4).
 * Specifying a lower version would still work (it doesn't downgrade),
 * but omitting it is clearer.
 */

import type { Page } from '@playwright/test';

export interface PhotoInfo {
	id: string;
	blobSize: number;
	status: string;
	server_photo_id: string | null;
	latitude: number | undefined;
	longitude: number | undefined;
	captured_at: number | undefined;
}

/** Get photo count from IndexedDB */
export async function getPhotoCount(page: Page): Promise<number> {
	return page.evaluate(() => {
		return new Promise<number>((resolve) => {
			const request = indexedDB.open('HillviewPhotoDB');
			request.onerror = () => resolve(0);
			request.onsuccess = () => {
				const db = request.result;
				if (!db.objectStoreNames.contains('photos')) {
					db.close();
					resolve(0);
					return;
				}
				const tx = db.transaction('photos', 'readonly');
				const store = tx.objectStore('photos');
				const countReq = store.count();
				countReq.onsuccess = () => { db.close(); resolve(countReq.result); };
				countReq.onerror = () => { db.close(); resolve(0); };
			};
			request.onupgradeneeded = () => { request.result.close(); resolve(0); };
		});
	});
}

/** Wait for IndexedDB photo count to reach target */
export async function waitForPhotoCount(page: Page, target: number, timeoutMs = 10000): Promise<void> {
	await page.evaluate(async ({ target, timeoutMs }: { target: number; timeoutMs: number }) => {
		const interval = 1400;
		let elapsed = 0;
		while (elapsed < timeoutMs) {
			const count = await new Promise<number>((resolve) => {
				const request = indexedDB.open('HillviewPhotoDB');
				request.onerror = () => resolve(0);
				request.onsuccess = () => {
					const db = request.result;
					if (!db.objectStoreNames.contains('photos')) { db.close(); resolve(0); return; }
					const tx = db.transaction('photos', 'readonly');
					const store = tx.objectStore('photos');
					const c = store.count();
					c.onsuccess = () => { db.close(); resolve(c.result); };
					c.onerror = () => { db.close(); resolve(0); };
				};
				request.onupgradeneeded = () => { (request as IDBOpenDBRequest).result.close(); resolve(0); };
			});
			if (count >= target) return;
			console.log(`[waitForPhotoCount] ${elapsed}ms: count=${count}, waiting for ${target}`);
			await new Promise(r => setTimeout(r, interval));
			elapsed += interval;
		}
		throw new Error(`Timed out waiting for ${target} photos (waited ${timeoutMs}ms)`);
	}, { target, timeoutMs });
}

/** Get the latest photo from IndexedDB with correct field paths */
export async function getLatestPhoto(page: Page): Promise<PhotoInfo | null> {
	return page.evaluate(() => {
		return new Promise<any>((resolve) => {
			const request = indexedDB.open('HillviewPhotoDB');
			request.onerror = () => resolve(null);
			request.onsuccess = () => {
				const db = request.result;
				if (!db.objectStoreNames.contains('photos')) { db.close(); resolve(null); return; }
				const tx = db.transaction('photos', 'readonly');
				const store = tx.objectStore('photos');
				const allReq = store.getAll();
				allReq.onsuccess = () => {
					db.close();
					const photos = allReq.result;
					if (photos.length === 0) { resolve(null); return; }
					const newest = photos[photos.length - 1];
					resolve({
						id: newest.id,
						blobSize: newest.blob?.size ?? 0,
						status: newest.status,
						server_photo_id: newest.server_photo_id || null,
						latitude: newest.metadata?.location?.latitude,
						longitude: newest.metadata?.location?.longitude,
						captured_at: newest.metadata?.captured_at
					});
				};
				allReq.onerror = () => { db.close(); resolve(null); };
			};
			request.onupgradeneeded = () => { request.result.close(); resolve(null); };
		});
	});
}

/** Wait for N photos to reach 'uploaded' status in IndexedDB.
 *  Polls from Node.js side so we can log intermediate states. */
export async function waitForUploadedCount(page: Page, target: number, timeoutMs = 130000): Promise<void> {
	const interval = 1500;
	let elapsed = 0;
	let lastLog = '';

	while (elapsed < timeoutMs) {
		const statuses = await page.evaluate(() => {
			return new Promise<Array<{ id: string; status: string; server_photo_id: string | null; retry_count?: number; error?: string }>>((resolve) => {
				const request = indexedDB.open('HillviewPhotoDB');
				request.onerror = () => resolve([]);
				request.onsuccess = () => {
					const db = request.result;
					if (!db.objectStoreNames.contains('photos')) { db.close(); resolve([]); return; }
					const tx = db.transaction('photos', 'readonly');
					const store = tx.objectStore('photos');
					const allReq = store.getAll();
					allReq.onsuccess = () => {
						db.close();
						resolve(allReq.result.map((p: any) => ({
							id: p.id,
							status: p.status,
							server_photo_id: p.server_photo_id || null,
							retry_count: p.retry_count,
							error: p.last_error
						})));
					};
					allReq.onerror = () => { db.close(); resolve([]); };
				};
				request.onupgradeneeded = () => { (request as IDBOpenDBRequest).result.close(); resolve([]); };
			});
		});

		const uploadedCount = statuses.filter(p => p.status === 'processing' || p.status === 'completed').length;
		if (uploadedCount >= target) return;

		console.log(`[waitForUploadedCount] ${elapsed}ms: ${uploadedCount}/${target} uploaded`);
		// Log status changes (not every poll)
		const statusSummary = statuses.map(p => `${p.id.slice(-8)}:${p.status}${p.error ? '(' + p.error.slice(0, 40) + ')' : ''}`).join(', ');
		if (statusSummary !== lastLog) {
			console.log(`[waitForUploadedCount] ${elapsed}ms: ${statusSummary || '(no photos)'}`);
			lastLog = statusSummary;
		}

		await new Promise(r => setTimeout(r, interval));
		elapsed += interval;
	}

	// Final state dump on timeout
	const finalStatuses = await getAllPhotosDetailed(page);
	throw new Error(`Timed out waiting for ${target} uploaded photos (waited ${timeoutMs}ms). Final: ${JSON.stringify(finalStatuses)}`);
}

/**
 * Seed a photo into IndexedDB as if it had been captured with the browser
 * camera, so the upload pipeline picks it up. Returns the local photo ID.
 *
 * The versioned open mirrors DB_VERSION / the schema in
 * src/lib/browser/photoStorage.ts; the upgrade path only runs when the app
 * hasn't created the DB yet.
 */
export async function seedBrowserPhoto(
	page: Page,
	jpegBase64: string,
	location: { latitude: number; longitude: number; bearing: number } = {
		latitude: 50.11692,
		longitude: 14.48837,
		bearing: 141
	}
): Promise<string> {
	return page.evaluate(async ({ jpegBase64, location }: { jpegBase64: string; location: { latitude: number; longitude: number; bearing: number } }) => {
		const bytes = Uint8Array.from(atob(jpegBase64), c => c.charCodeAt(0));
		const blob = new Blob([bytes], { type: 'image/jpeg' });
		const bitmap = await createImageBitmap(blob);

		const photo = {
			id: crypto.randomUUID(),
			blob,
			width: bitmap.width,
			height: bitmap.height,
			metadata: {
				location: {
					latitude: location.latitude,
					longitude: location.longitude,
					altitude: null,
					accuracy: 10,
					bearing: location.bearing,
					location_source: 'map',
					bearing_source: 'map',
					alt_location: null
				},
				captured_at: Date.now(),
				orientation_code: 1
			},
			status: 'pending',
			deleted: false,
			retry_count: 0,
			added_at: Date.now()
		};

		await new Promise<void>((resolve, reject) => {
			const request = indexedDB.open('HillviewPhotoDB', 4);
			request.onupgradeneeded = (event) => {
				const db = (event.target as IDBOpenDBRequest).result;
				if (!db.objectStoreNames.contains('photos')) {
					const store = db.createObjectStore('photos', { keyPath: 'id' });
					store.createIndex('status', 'status');
					store.createIndex('captured_at', 'metadata.captured_at');
					store.createIndex('added_at', 'added_at');
				}
			};
			request.onerror = () => reject(request.error);
			request.onsuccess = () => {
				const db = request.result;
				const tx = db.transaction('photos', 'readwrite');
				const putReq = tx.objectStore('photos').put(photo);
				putReq.onerror = () => { db.close(); reject(putReq.error); };
				tx.oncomplete = () => { db.close(); resolve(); };
			};
		});

		return photo.id;
	}, { jpegBase64, location });
}

export interface ReuploadState {
	status: string;
	version: number | undefined;
	anonymization_override: string | null | undefined;
	server_photo_id: string | null;
}

/** Get a photo's re-upload-related fields from IndexedDB */
export async function getPhotoReuploadState(page: Page, photoId: string): Promise<ReuploadState | null> {
	return page.evaluate((photoId: string) => {
		return new Promise<any>((resolve) => {
			const request = indexedDB.open('HillviewPhotoDB');
			request.onerror = () => resolve(null);
			request.onsuccess = () => {
				const db = request.result;
				if (!db.objectStoreNames.contains('photos')) { db.close(); resolve(null); return; }
				const tx = db.transaction('photos', 'readonly');
				const getReq = tx.objectStore('photos').get(photoId);
				getReq.onsuccess = () => {
					db.close();
					const p = getReq.result;
					if (!p) { resolve(null); return; }
					resolve({
						status: p.status,
						version: p.version,
						anonymization_override: p.anonymization_override,
						server_photo_id: p.server_photo_id || null
					});
				};
				getReq.onerror = () => { db.close(); resolve(null); };
			};
			request.onupgradeneeded = () => { request.result.close(); resolve(null); };
		});
	}, photoId);
}

/** Wait for a photo to finish re-uploading at (or above) the given version */
export async function waitForReuploadedVersion(
	page: Page,
	photoId: string,
	version: number,
	timeoutMs = 130000
): Promise<ReuploadState> {
	const interval = 1500;
	let elapsed = 0;
	let lastLog = '';

	while (elapsed < timeoutMs) {
		const state = await getPhotoReuploadState(page, photoId);

		if (state && (state.version ?? 1) >= version &&
			(state.status === 'processing' || state.status === 'completed')) {
			return state;
		}

		const summary = JSON.stringify(state);
		if (summary !== lastLog) {
			console.log(`[waitForReuploadedVersion] ${elapsed}ms: ${summary}`);
			lastLog = summary;
		}

		await new Promise(r => setTimeout(r, interval));
		elapsed += interval;
	}

	const finalState = await getPhotoReuploadState(page, photoId);
	throw new Error(`Timed out waiting for photo ${photoId} to re-upload at version ${version} (waited ${timeoutMs}ms). Final: ${JSON.stringify(finalState)}`);
}

/** Get all photos with their status and server_photo_id */
export async function getAllPhotosDetailed(page: Page): Promise<Array<{ id: string; status: string; server_photo_id: string | null }>> {
	return page.evaluate(() => {
		return new Promise<any[]>((resolve) => {
			const request = indexedDB.open('HillviewPhotoDB');
			request.onerror = () => resolve([]);
			request.onsuccess = () => {
				const db = request.result;
				if (!db.objectStoreNames.contains('photos')) { db.close(); resolve([]); return; }
				const tx = db.transaction('photos', 'readonly');
				const store = tx.objectStore('photos');
				const allReq = store.getAll();
				allReq.onsuccess = () => {
					db.close();
					resolve(allReq.result.map((p: any) => ({
						id: p.id,
						status: p.status,
						server_photo_id: p.server_photo_id || null
					})));
				};
				allReq.onerror = () => { db.close(); resolve([]); };
			};
			request.onupgradeneeded = () => { request.result.close(); resolve([]); };
		});
	});
}

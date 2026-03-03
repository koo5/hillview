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
		const interval = 200;
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

/** Wait for N photos to reach 'uploaded' status in IndexedDB */
export async function waitForUploadedCount(page: Page, target: number, timeoutMs = 30000): Promise<void> {
	await page.evaluate(async ({ target, timeoutMs }: { target: number; timeoutMs: number }) => {
		const interval = 500;
		let elapsed = 0;
		while (elapsed < timeoutMs) {
			const uploadedCount = await new Promise<number>((resolve) => {
				const request = indexedDB.open('HillviewPhotoDB');
				request.onerror = () => resolve(0);
				request.onsuccess = () => {
					const db = request.result;
					if (!db.objectStoreNames.contains('photos')) { db.close(); resolve(0); return; }
					const tx = db.transaction('photos', 'readonly');
					const store = tx.objectStore('photos');
					const allReq = store.getAll();
					allReq.onsuccess = () => {
						db.close();
						const photos = allReq.result;
						const count = photos.filter((p: any) => p.status === 'uploaded').length;
						resolve(count);
					};
					allReq.onerror = () => { db.close(); resolve(0); };
				};
				request.onupgradeneeded = () => { (request as IDBOpenDBRequest).result.close(); resolve(0); };
			});
			if (uploadedCount >= target) return;
			await new Promise(r => setTimeout(r, interval));
			elapsed += interval;
		}
		throw new Error(`Timed out waiting for ${target} uploaded photos (waited ${timeoutMs}ms)`);
	}, { target, timeoutMs });
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

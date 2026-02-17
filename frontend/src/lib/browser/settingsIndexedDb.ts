// IndexedDB settings storage for service worker access
import type { Settings } from '../settings';

const DB_NAME = 'HillviewSettingsDB';
const DB_VERSION = 1;
const STORE_NAME = 'settings';

async function openDB(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(DB_NAME, DB_VERSION);
		request.onerror = () => reject(request.error);
		request.onsuccess = () => resolve(request.result);
		request.onupgradeneeded = (event) => {
			const db = (event.target as IDBOpenDBRequest).result;
			if (!db.objectStoreNames.contains(STORE_NAME)) {
				db.createObjectStore(STORE_NAME);
			}
		};
	});
}

export async function writeSettings(settings: Settings): Promise<void> {
	try {
		const db = await openDB();
		const transaction = db.transaction([STORE_NAME], 'readwrite');
		const store = transaction.objectStore(STORE_NAME);
		await new Promise<void>((resolve, reject) => {
			const request = store.put(settings, 'current');
			request.onsuccess = () => resolve();
			request.onerror = () => reject(request.error);
		});
	} catch (err) {
		console.error('[SettingsIndexedDb] Failed to write:', err);
	}
}

export async function readSettings(): Promise<Settings | null> {
	try {
		const db = await openDB();
		const transaction = db.transaction([STORE_NAME], 'readonly');
		const store = transaction.objectStore(STORE_NAME);
		return new Promise((resolve, reject) => {
			const request = store.get('current');
			request.onsuccess = () => resolve(request.result || null);
			request.onerror = () => reject(request.error);
		});
	} catch (err) {
		console.error('[SettingsIndexedDb] Failed to read:', err);
		return null;
	}
}

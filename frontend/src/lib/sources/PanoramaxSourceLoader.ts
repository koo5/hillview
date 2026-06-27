/**
 * Panoramax Source Loader - one-shot HTTP fetch against a Panoramax STAC instance.
 *
 * Throttle policy (see docs/todo/panoramax-source-integration.md): leading-edge
 * with a 1s minimum interval, enforced via the module-level `lastFireTime` shared
 * across loader instances. Each instance is one area-update; the worker creates a
 * new loader per area change and cancels the previous one, so the "pending bbox"
 * slot in the design is implicit — only the most recent instance survives to fire.
 */

import type { PhotoData, Bounds } from '../photoWorkerTypes';
import { BasePhotoSourceLoader, type PhotoSourceCallbacks } from './PhotoSourceLoader';
import type { PhotoSourceOptions } from './PhotoSourceFactory';
import { backendUrl } from '../config';

const LOG_PREFIX = '🢄🔍PanoramaxSourceLoader';
const doLog = false;

const MIN_INTERVAL_MS = 1000;
const DEFAULT_LIMIT = 1000;

let lastFireTime = 0;

// Hidden-content cache. The backend can't filter Panoramax results (they're
// fetched client → api.panoramax.xyz directly), so the worker pulls the user's
// hide list once per authenticated session and applies it client-side. Anonymous
// state is intentionally not cached so that logging in self-heals on the next
// fetch. `invalidatePanoramaxHidden()` is poked from the main thread after
// hide/unhide actions and on logout.
interface PanoramaxHidden {
	photoIds: Set<string>;
	userIds: Set<string>;
}
const EMPTY_HIDDEN: PanoramaxHidden = { photoIds: new Set(), userIds: new Set() };

let hiddenContent: PanoramaxHidden | null = null;
let hiddenInflight: Promise<PanoramaxHidden> | null = null;

export function invalidatePanoramaxHidden(): void {
	hiddenContent = null;
	hiddenInflight = null;
}

async function fetchPanoramaxHidden(token: string): Promise<PanoramaxHidden> {
	const headers = { Authorization: `Bearer ${token}` };
	const [photosResp, usersResp] = await Promise.all([
		fetch(`${backendUrl}/hidden/photos?photo_source=panoramax`, { headers }),
		fetch(`${backendUrl}/hidden/users?target_user_source=panoramax`, { headers })
	]);
	const photoIds = new Set<string>();
	const userIds = new Set<string>();
	if (photosResp.ok) {
		const rows = await photosResp.json();
		if (Array.isArray(rows)) for (const r of rows) if (r?.photo_id) photoIds.add(r.photo_id);
	}
	if (usersResp.ok) {
		const rows = await usersResp.json();
		if (Array.isArray(rows)) for (const r of rows) if (r?.target_user_id) userIds.add(r.target_user_id);
	}
	return { photoIds, userIds };
}

async function ensurePanoramaxHidden(
	getToken: (forceRefresh?: boolean) => Promise<string | null>
): Promise<PanoramaxHidden> {
	if (hiddenContent) return hiddenContent;
	if (hiddenInflight) return hiddenInflight;
	hiddenInflight = (async () => {
		try {
			const token = await getToken();
			if (!token) return EMPTY_HIDDEN; // not cached — login retries naturally
			const loaded = await fetchPanoramaxHidden(token);
			hiddenContent = loaded;
			return loaded;
		} catch (e) {
			console.warn(`${LOG_PREFIX}: failed to load hidden content, falling back to empty:`, e);
			return EMPTY_HIDDEN;
		} finally {
			hiddenInflight = null;
		}
	})();
	return hiddenInflight;
}

function getProducerIdFromItem(item: any): string | undefined {
	const providers: any[] = Array.isArray(item?.providers) ? item.providers : [];
	const producer =
		providers.find((p) => Array.isArray(p?.roles) && p.roles.includes('producer')) ||
		providers[0];
	return producer?.id;
}

// STAC Items (one per photo), returned by /api/search as GeoJSON Features. The
// "Item" naming follows STAC terminology and avoids collision with
// QueryOptions.features (the AI-analysis filter list).
export function convertPanoramaxItem(item: any, source: any): PhotoData | null {
	if (!item || !item.geometry || !Array.isArray(item.geometry.coordinates)) {
		return null;
	}
	const [lng, lat] = item.geometry.coordinates;
	if (typeof lat !== 'number' || typeof lng !== 'number') return null;

	const props = item.properties || {};
	const assets = item.assets || {};

	let bearing = props['view:azimuth'];
	if (bearing === undefined || bearing === null) bearing = props['pers:yaw'];
	if (typeof bearing !== 'number') bearing = 0;

	const thumbUrl: string = assets?.thumb?.href || props['geovisio:thumbnail'] || '';
	const sdUrl: string | undefined = assets?.sd?.href;
	const hdUrl: string | undefined = assets?.hd?.href || props['geovisio:image'];

	// We don't know exact pixel dimensions without an EXIF round-trip; emit 0/0 so
	// callers fall back to natural dimensions on image load.
	const sizes: Record<string, { url: string; width: number; height: number }> = {};
	if (thumbUrl) sizes.thumb = { url: thumbUrl, width: 0, height: 0 };
	if (sdUrl) sizes.sd = { url: sdUrl, width: 0, height: 0 };
	if (hdUrl) sizes.full = { url: hdUrl, width: 0, height: 0 };

	const capturedAtRaw = props.datetime || props.created;
	const captured_at = capturedAtRaw ? Date.parse(capturedAtRaw) : undefined;

	const filename: string = props['original_file:name'] || `${item.id}.jpg`;

	const persType: string | undefined = props['pers:type'];

	const photo: any = {
		id: item.id,
		uid: `${source.id}-${item.id}`,
		coord: { lat, lng },
		bearing,
		url: thumbUrl || hdUrl || sdUrl || '',
		filename,
		source_type: source.type,
		source,
		altitude: 0,
		captured_at: Number.isFinite(captured_at) ? captured_at : undefined,
		sizes: Object.keys(sizes).length > 0 ? sizes : undefined,
		...(persType ? { projection: persType } : {})
	};

	// Producer ID lives in providers[]; the geovisio:producer property is just the
	// display name. Pull both so the canonical user URL can use the ID.
	const providers: any[] = Array.isArray(item.providers) ? item.providers : [];
	const producerEntry =
		providers.find((p) => Array.isArray(p?.roles) && p.roles.includes('producer')) ||
		providers[0];
	const producerName = producerEntry?.name || props['geovisio:producer'];
	const producerId = producerEntry?.id;
	if (producerName || producerId) {
		photo.creator = {
			...(producerId ? { id: producerId } : {}),
			...(producerName ? { username: producerName } : {})
		};
	}

	if (props.license) photo.license = props.license;

	return photo;
}

function waitOrAbort(ms: number, signal: AbortSignal): Promise<void> {
	if (signal.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'));
	if (ms <= 0) return Promise.resolve();
	return new Promise<void>((resolve, reject) => {
		const timer = setTimeout(() => {
			signal.removeEventListener('abort', onAbort);
			resolve();
		}, ms);
		const onAbort = () => {
			clearTimeout(timer);
			reject(new DOMException('Aborted', 'AbortError'));
		};
		signal.addEventListener('abort', onAbort, { once: true });
	});
}

export class PanoramaxSourceLoader extends BasePhotoSourceLoader {
	private streamPhotos: PhotoData[] = [];
	private maxPhotos?: number;

	constructor(source: any, callbacks: PhotoSourceCallbacks, options?: PhotoSourceOptions) {
		super(source, callbacks);
		this.maxPhotos = options?.maxPhotos;
	}

	private updateLoadingStatus(isLoading: boolean, progress?: string, error?: string): void {
		if (typeof postMessage === 'function') {
			postMessage({
				type: 'sourceLoadingStatus',
				source_id: this.source.id,
				is_loading: isLoading,
				progress,
				error
			});
		}
	}

	async start(bounds?: Bounds): Promise<void> {
		if (!bounds) {
			// Config-time start with no bounds — wait for an area update.
			this.isComplete = true;
			return;
		}
		if (!this.source.url) {
			throw new Error('Panoramax source missing instance URL');
		}

		this.abortController = new AbortController();
		this.updateLoadingStatus(true, 'Queued');

		const elapsed = Date.now() - lastFireTime;
		const delay = Math.max(0, MIN_INTERVAL_MS - elapsed);

		if (delay > 0) {
			if (doLog) console.log(`${LOG_PREFIX}: throttle wait ${delay}ms for ${this.source.id}`);
			try {
				await waitOrAbort(delay, this.abortController.signal);
			} catch {
				this.isComplete = true;
				this.updateLoadingStatus(false, 'Cancelled');
				return;
			}
		}

		if (this.abortController.signal.aborted) {
			this.isComplete = true;
			this.updateLoadingStatus(false, 'Cancelled');
			return;
		}

		lastFireTime = Date.now();
		await this.performFetch(bounds);
	}

	private async performFetch(bounds: Bounds): Promise<void> {
		const instance = this.source.url!.replace(/\/+$/, '');
		const w = Math.min(bounds.top_left.lng, bounds.bottom_right.lng);
		const e = Math.max(bounds.top_left.lng, bounds.bottom_right.lng);
		const s = Math.min(bounds.top_left.lat, bounds.bottom_right.lat);
		const n = Math.max(bounds.top_left.lat, bounds.bottom_right.lat);
		const limit = this.maxPhotos ?? DEFAULT_LIMIT;

		const url = new URL(`${instance}/api/search`);
		url.searchParams.set('bbox', `${w},${s},${e},${n}`);
		url.searchParams.set('limit', String(limit));

		this.updateLoadingStatus(true, 'Loading photos...');
		if (doLog) console.log(`${LOG_PREFIX}: GET ${url.toString()}`);

		// Kick off hidden-content load in parallel with the search so they share
		// latency. First authenticated call hits the wire; subsequent calls hit
		// the module-level cache.
		const hiddenPromise = ensurePanoramaxHidden(this.callbacks.getValidToken);

		let response: Response;
		try {
			response = await fetch(url.toString(), {
				signal: this.abortController!.signal,
				headers: { 'Accept': 'application/json' }
			});
		} catch (e: any) {
			if (e?.name === 'AbortError') {
				this.isComplete = true;
				this.updateLoadingStatus(false, 'Cancelled');
				return;
			}
			console.error(`${LOG_PREFIX}: fetch error for ${this.source.id}:`, e);
			const errorMessage = e instanceof Error ? e.message : String(e);
			this.callbacks.onError?.(new Error(errorMessage));
			this.updateLoadingStatus(false, undefined, errorMessage);
			this.isComplete = true;
			return;
		}

		if (!response.ok) {
			const errorMessage = `Panoramax API ${response.status} ${response.statusText}`;
			console.error(`${LOG_PREFIX}: ${errorMessage} for ${this.source.id}`);
			this.callbacks.onError?.(new Error(errorMessage));
			this.updateLoadingStatus(false, undefined, errorMessage);
			this.isComplete = true;
			return;
		}

		let data: any;
		try {
			data = await response.json();
		} catch (e) {
			const errorMessage = 'Failed to parse Panoramax response';
			console.error(`${LOG_PREFIX}: ${errorMessage}:`, e);
			this.callbacks.onError?.(new Error(errorMessage));
			this.updateLoadingStatus(false, undefined, errorMessage);
			this.isComplete = true;
			return;
		}

		if (this.abortController!.signal.aborted) {
			this.isComplete = true;
			return;
		}

		const hidden = await hiddenPromise;
		if (this.abortController!.signal.aborted) {
			this.isComplete = true;
			return;
		}

		const items: any[] = Array.isArray(data?.features) ? data.features : [];
		let droppedHidden = 0;
		for (const item of items) {
			if (item?.id && hidden.photoIds.has(item.id)) {
				droppedHidden++;
				continue;
			}
			const producerId = getProducerIdFromItem(item);
			if (producerId && hidden.userIds.has(producerId)) {
				droppedHidden++;
				continue;
			}
			const photo = convertPanoramaxItem(item, this.source);
			if (photo) this.streamPhotos.push(photo);
		}

		if (doLog) console.log(`${LOG_PREFIX}: got ${this.streamPhotos.length} photos for ${this.source.id} (filtered ${droppedHidden} hidden)`);

		this.callbacks.enqueueMessage({
			type: 'photosAdded',
			source_id: this.source.id,
			photos: this.streamPhotos
		});

		const duration = Date.now() - this.startTime;
		this.isComplete = true;
		this.updateLoadingStatus(false, `Loaded ${this.streamPhotos.length} photos`);
		this.callbacks.enqueueMessage({
			type: 'streamComplete',
			source_id: this.source.id,
			totalPhotos: this.streamPhotos.length,
			duration
		});
	}

	cancel(): void {
		if (doLog) console.log(`${LOG_PREFIX}: cancel for ${this.source.id}`);
		super.cancel();
		this.updateLoadingStatus(false, 'Cancelled');
		this.streamPhotos = [];
	}

	getAllPhotos(): PhotoData[] {
		return [...this.streamPhotos];
	}

	getFilteredPhotos(_bounds: Bounds): PhotoData[] {
		return [...this.streamPhotos];
	}

	protected getLoaderType(): string {
		return 'PanoramaxSourceLoader';
	}
}

// Test-only hook to reset cross-instance throttle state.
export function __resetPanoramaxThrottleForTests(): void {
	lastFireTime = 0;
}

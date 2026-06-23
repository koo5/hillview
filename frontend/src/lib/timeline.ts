/**
 * Capture-time timeline ("walk photos by time").
 *
 * Holds an ordered window of a user's (or users') photos fetched from
 * GET /api/hillview/timeline, plus a cursor. Stepping the cursor selects the
 * target photo through the normal map/gallery path: Map.svelte subscribes to
 * `timelineCurrent` and routes it through handleMarkerClick (pan if off-screen,
 * just select if already in range). The loaded photos are also drawn as a route
 * polyline on the map.
 *
 * v1: single anchor user (owner of the photo you start on), fixed window,
 * in-memory for the session, Hillview photos only. `userIds` is already a list
 * so a future merged multi-user timeline is additive, not a rewrite.
 */
import { writable, derived, get } from 'svelte/store';
import type { PhotoData } from './types/photoTypes';
import { photoInFront, timelinePinned } from './mapState';
import { http } from './http';
import { addAlert } from './alertSystem.svelte';
import { localStorageSharedStore } from './svelte-shared-store';

export type WalkDirection = 'older' | 'newer';

// Fixed window size (photos fetched to each side of the anchor). Intentionally
// not user-variable for now; "see the whole route" later = raise these.
const TIMELINE_BEFORE = 100;
const TIMELINE_AFTER = 100;
// Start fetching the next chunk once the cursor gets within this many photos of a
// loaded end, so new items are usually already there before you reach the edge.
const TIMELINE_PREFETCH_MARGIN = 20;
// Keep this many photos to each side of the cursor pinned into `picks`, so the
// photo you step *to* is already loaded (picks are fetched regardless of bounds).
// Matches the server pick cap (MAX_HILLVIEW_PICKS, default 200 ≈ ±100), so the
// whole loaded window is effectively pinned.
const TIMELINE_PIN_MARGIN = 100;

// The timeline endpoint returns a lightweight navigation index, not a full photo
// feed. We build the minimal PhotoData the walk needs: uid `hillview-<id>` (to
// match worker-loaded photos in photosInRange), coord (flyTo + polyline), bearing
// (selection), captured_at + thumb + owner (panel). The gallery still renders the
// worker's copy of the selected photo.
interface TimelineIndexPhoto {
	id: string;
	lat: number;
	lng: number;
	bearing: number;
	captured_at: string | null;
	uploaded_at: string | null;
	thumb_url: string | null;
	owner_id: string;
	owner_username: string;
}

function indexToPhoto(p: TimelineIndexPhoto): PhotoData {
	return {
		id: p.id,
		uid: `hillview-${p.id}`,
		source_type: 'stream',
		filename: '',
		url: p.thumb_url || '',
		bearing: p.bearing ?? 0,
		altitude: 0,
		coord: { lat: p.lat, lng: p.lng },
		// Display/sort time: real capture time, else upload time. Flag the fallback
		// so the panel can mark it.
		captured_at: (p.captured_at ?? p.uploaded_at) as any,
		timeIsUpload: !p.captured_at,
		creator: { id: p.owner_id, username: p.owner_username },
	} as PhotoData;
}

export const timelineActive = writable<boolean>(false);
export const timelineLoading = writable<boolean>(false);
export const timelinePhotos = writable<PhotoData[]>([]);
export const timelineCursor = writable<number>(0);
export const timelineUserIds = writable<string[]>([]);
export const timelineHasMore = writable<{ before: boolean; after: boolean }>({ before: false, after: false });

// Panel width preference (persisted): true = wide (thumbs + text), false = narrow (thumbs only).
export const timelineWide = localStorageSharedStore<boolean>('timelineWide', true);
export function toggleTimelineWide() {
	timelineWide.update(v => !v);
}

// The photo the cursor currently points at (null when inactive/empty).
export const timelineCurrent = derived(
	[timelineActive, timelinePhotos, timelineCursor],
	([active, photos, cursor]) => (active && cursor >= 0 && cursor < photos.length) ? photos[cursor] : null
);

function ownerIdOf(photo: PhotoData): string | undefined {
	return (photo as any).creator?.id;
}

function isHillview(photo: PhotoData): boolean {
	return typeof photo.uid === 'string' && photo.uid.startsWith('hillview-');
}

/**
 * Pin a window of loaded photos around `cursor` so the server keeps them loaded
 * (picks are returned regardless of bounds, and the range culler keeps a pinned
 * photo once you fly near it). Pinning only the current photo meant the photo you
 * step *to* wasn't loaded yet, so the gallery briefly showed a bearing-closest
 * neighbour until the next area query returned the real target.
 */
function pinWindow(cursor: number) {
	const photos = get(timelinePhotos);
	if (photos.length === 0) {
		timelinePinned.set(new Set());
		return;
	}
	const lo = Math.max(0, cursor - TIMELINE_PIN_MARGIN);
	const hi = Math.min(photos.length - 1, cursor + TIMELINE_PIN_MARGIN);
	const uids = new Set<string>();
	for (let i = lo; i <= hi; i++) uids.add(photos[i].uid);
	timelinePinned.set(uids);
}

// Shared open-or-warn used by both the walk keys and the toggle key.
function openForCurrent(dir?: WalkDirection) {
	const anchor = get(photoInFront);
	if (!anchor) {
		addAlert('Select a photo first to open its timeline', 'info', { source: 'timeline', duration: 3000 });
		return;
	}
	if (!isHillview(anchor)) {
		addAlert('Timeline is only available for Hillview photos', 'info', { source: 'timeline', duration: 3000 });
		return;
	}
	startTimeline(anchor, dir);
}

/** Walk keys (',' / '.'): start on first press (anchored on the front photo), step thereafter. */
export function walkTimeline(dir: WalkDirection) {
	if (get(timelineActive)) {
		stepTimeline(dir);
		return;
	}
	openForCurrent(dir);
}

/** 't' key: toggle the panel; (re)load for the current front photo when opening. */
export function toggleTimeline() {
	if (get(timelineActive)) {
		stopTimeline();
		return;
	}
	openForCurrent();
}

function toPhotos(data: any): PhotoData[] {
	return (data.photos || []).map((p: TimelineIndexPhoto) => indexToPhoto(p));
}

async function fetchTimeline(userIds: string[], anchorId: string, before: number, after: number): Promise<any> {
	const params = new URLSearchParams({
		user_ids: userIds.join(','),
		anchor_id: anchorId,
		before: String(before),
		after: String(after),
	});
	const res = await http.get(`/hillview/timeline?${params.toString()}`);
	if (!res.ok) throw new Error(`timeline request failed: ${res.status}`);
	return res.json();
}

export async function startTimeline(anchor: PhotoData, dir?: WalkDirection) {
	const ownerId = ownerIdOf(anchor);
	if (!ownerId) {
		addAlert('Cannot build a timeline for this photo (unknown owner)', 'warning', { source: 'timeline', duration: 3000 });
		return;
	}

	const userIds = [ownerId];
	timelineUserIds.set(userIds);
	timelineActive.set(true);
	timelineLoading.set(true);
	timelinePhotos.set([]);
	timelineCursor.set(0);

	try {
		const data = await fetchTimeline(userIds, anchor.id, TIMELINE_BEFORE, TIMELINE_AFTER);

		// User may have closed the timeline while we were loading.
		if (!get(timelineActive)) return;

		const photos: PhotoData[] = toPhotos(data);
		const anchorIndex = typeof data.anchor_index === 'number' ? data.anchor_index : 0;
		const cursor = Math.min(Math.max(anchorIndex, 0), Math.max(photos.length - 1, 0));

		// Set cursor before photos so the first reactive selection lands on the
		// anchor (already the front photo) rather than briefly on photos[0].
		timelineCursor.set(cursor);
		timelineHasMore.set({ before: !!data.has_more_before, after: !!data.has_more_after });
		timelinePhotos.set(photos);
		pinWindow(cursor);

		// The first key press also steps once in the pressed direction.
		if (dir) stepTimeline(dir);
	} catch (e) {
		console.error('Timeline: failed to load', e);
		addAlert('Failed to load timeline', 'error', { source: 'timeline', duration: 4000 });
		stopTimeline();
	} finally {
		timelineLoading.set(false);
	}
}

export async function stepTimeline(dir: WalkDirection) {
	if (get(timelinePhotos).length === 0) return;
	const delta = dir === 'newer' ? 1 : -1;
	let next = get(timelineCursor) + delta;

	// At an end: pull the next chunk from the server (if it said there's more),
	// then re-derive `next` against the grown/shifted window.
	if (next < 0) {
		if (get(timelineLoading) || !get(timelineHasMore).before) return;
		await extendTimeline('before');
		next = get(timelineCursor) + delta;
	} else if (next >= get(timelinePhotos).length) {
		if (get(timelineLoading) || !get(timelineHasMore).after) return;
		await extendTimeline('after');
		next = get(timelineCursor) + delta;
	}

	if (next < 0 || next >= get(timelinePhotos).length) return;  // nothing new arrived
	jumpToIndex(next);
}

/**
 * Pull the next chunk older/newer than the loaded window, anchored on the
 * first/last loaded photo. Prepend/append the fresh photos (deduped by uid —
 * the response repeats the anchor) and keep the cursor on the same photo.
 */
async function extendTimeline(end: 'before' | 'after') {
	const photos = get(timelinePhotos);
	if (photos.length === 0) return;
	const anchor = end === 'before' ? photos[0] : photos[photos.length - 1];
	timelineLoading.set(true);
	try {
		const data = await fetchTimeline(
			get(timelineUserIds),
			anchor.id,
			end === 'before' ? TIMELINE_BEFORE : 0,
			end === 'after' ? TIMELINE_AFTER : 0,
		);
		if (!get(timelineActive)) return;

		const seen = new Set(get(timelinePhotos).map(p => p.uid));
		const fresh = toPhotos(data).filter(p => !seen.has(p.uid));

		if (end === 'before') {
			timelinePhotos.set([...fresh, ...get(timelinePhotos)]);
			timelineCursor.update(c => c + fresh.length);  // keep pointing at the same photo
			timelineHasMore.update(m => ({ ...m, before: !!data.has_more_before }));
		} else {
			timelinePhotos.set([...get(timelinePhotos), ...fresh]);
			timelineHasMore.update(m => ({ ...m, after: !!data.has_more_after }));
		}
	} catch (e) {
		console.error('Timeline: failed to extend', e);
	} finally {
		timelineLoading.set(false);
	}
}

// Prefetch the next chunk when the cursor nears a loaded end (non-blocking), so
// new items are usually present before you walk off the edge. The blocking
// extend in stepTimeline remains as a fallback (e.g. jumping straight to an end).
function maybePrefetch() {
	if (get(timelineLoading)) return;
	const cursor = get(timelineCursor);
	const len = get(timelinePhotos).length;
	const hasMore = get(timelineHasMore);
	if (hasMore.before && cursor <= TIMELINE_PREFETCH_MARGIN) {
		extendTimeline('before');
	} else if (hasMore.after && cursor >= len - 1 - TIMELINE_PREFETCH_MARGIN) {
		extendTimeline('after');
	}
}

export function jumpToIndex(i: number) {
	const photos = get(timelinePhotos);
	if (i < 0 || i >= photos.length) return;
	timelineCursor.set(i);
	pinWindow(i);
	maybePrefetch();
}

export function stopTimeline() {
	timelineActive.set(false);
	timelinePhotos.set([]);
	timelineCursor.set(0);
	timelineUserIds.set([]);
	timelineHasMore.set({ before: false, after: false });
	timelineLoading.set(false);
	timelinePinned.set(new Set());
}

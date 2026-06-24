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
import { photoInFront, timelinePinned, hunterMode, setHunterMode } from './mapState';
import { http } from './http';
import { addAlert } from './alertSystem.svelte';
import { localStorageSharedStore } from './svelte-shared-store';
import { filters, buildFiltersQueryParam } from './components/filters-modal/filtersStore';

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
export interface TimelineUser {
	id: string;
	username: string;
}

// Tracked users whose photos are merged into the timeline. Stored as {id, username}
// so the panel shows names directly — scanning loaded photos for a name fails for a
// user with no photo in the current window, and (because the each-block isn't
// re-run when photos arrive) even showed the raw UID in the single-user case.
export const timelineUsers = writable<TimelineUser[]>([]);
export const timelineHasMore = writable<{ before: boolean; after: boolean }>({ before: false, after: false });

// Panel width preference (persisted): true = wide (thumbs + text), false = narrow (thumbs only).
// Defaults to narrow; users who toggle keep their stored choice.
export const timelineWide = localStorageSharedStore<boolean>('timelineWide', false);
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

function ownerUsernameOf(photo: PhotoData): string | undefined {
	return (photo as any).creator?.username;
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
	// Same content filters as the map, so the walk only steps through matching photos.
	const fp = buildFiltersQueryParam();
	if (fp) params.set('analysis_filters', fp);
	const res = await http.get(`/hillview/timeline?${params.toString()}`);
	if (!res.ok) throw new Error(`timeline request failed: ${res.status}`);
	return res.json();
}

/**
 * Fetch the window around `anchorId` for the currently tracked users and install
 * it (photos + cursor + hasMore + pins). Shared by start and by add/remove user.
 */
async function loadWindow(anchorId: string): Promise<boolean> {
	// Remember the anchor so a filter that empties the list can still reload here.
	lastTimelineAnchorId = anchorId;
	timelineLoading.set(true);
	try {
		const userIds = get(timelineUsers).map(u => u.id);
		const data = await fetchTimeline(userIds, anchorId, TIMELINE_BEFORE, TIMELINE_AFTER);

		// User may have closed the timeline while we were loading.
		if (!get(timelineActive)) return false;

		const photos: PhotoData[] = toPhotos(data);
		const anchorIndex = typeof data.anchor_index === 'number' ? data.anchor_index : 0;
		const cursor = Math.min(Math.max(anchorIndex, 0), Math.max(photos.length - 1, 0));

		// Set cursor before photos so the first reactive selection lands on the
		// anchor rather than briefly on photos[0].
		timelineCursor.set(cursor);
		timelineHasMore.set({ before: !!data.has_more_before, after: !!data.has_more_after });
		timelinePhotos.set(photos);
		pinWindow(cursor);
		return true;
	} catch (e) {
		console.error('Timeline: failed to load', e);
		addAlert('Failed to load timeline', 'error', { source: 'timeline', duration: 4000 });
		return false;
	} finally {
		timelineLoading.set(false);
	}
}

// Hunter mode the user was in before the walk forced it on, so we can restore it
// on close (null = not currently overriding).
let hunterModeBeforeTimeline: boolean | null = null;

// The photo id the walk is anchored on, kept even when the loaded list is empty
// (e.g. a content filter hid every photo) so loosening the filter can reload here.
let lastTimelineAnchorId: string | null = null;

export async function startTimeline(anchor: PhotoData, dir?: WalkDirection) {
	const ownerId = ownerIdOf(anchor);
	if (!ownerId) {
		addAlert('Cannot build a timeline for this photo (unknown owner)', 'warning', { source: 'timeline', duration: 3000 });
		return;
	}

	// The walk visits a user's whole capture sequence — mostly non-featured photos,
	// which aren't navigable in tourist mode. So the timeline owns hunter mode while
	// open; remember the prior mode to restore on close.
	if (!get(timelineActive)) {
		hunterModeBeforeTimeline = get(hunterMode);
		setHunterMode(true);
	}

	timelineUsers.set([{ id: ownerId, username: ownerUsernameOf(anchor) || ownerId }]);
	timelineActive.set(true);
	timelinePhotos.set([]);
	timelineCursor.set(0);

	const ok = await loadWindow(anchor.id);
	if (!ok) {
		if (get(timelineActive)) stopTimeline();
		return;
	}
	// The first key press also steps once in the pressed direction.
	if (dir) stepTimeline(dir);
}

/** Re-anchor on the cursor photo and reload (after the tracked-user set changes). */
async function reloadAroundCursor() {
	const photos = get(timelinePhotos);
	// Fall back to the remembered anchor when the list is empty (a filter hid
	// everything) so loosening the filter can refill the walk.
	const anchorId = photos[get(timelineCursor)]?.id ?? photos[0]?.id ?? lastTimelineAnchorId;
	if (!anchorId) return;
	await loadWindow(anchorId);
}

/** Add a user to the merged timeline and reload around the current position. */
export async function addTimelineUser(user: TimelineUser) {
	const users = get(timelineUsers);
	if (users.some(u => u.id === user.id)) return;
	timelineUsers.set([...users, user]);
	await reloadAroundCursor();
}

/** Remove a tracked user (keeps at least one) and reload around the current position. */
export async function removeTimelineUser(id: string) {
	const users = get(timelineUsers);
	if (users.length <= 1) return;
	timelineUsers.set(users.filter(u => u.id !== id));
	await reloadAroundCursor();
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
			get(timelineUsers).map(u => u.id),
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
	lastTimelineAnchorId = photos[i].id;  // track position for filter-driven reloads
	pinWindow(i);
	maybePrefetch();
}

export function stopTimeline() {
	timelineActive.set(false);
	timelinePhotos.set([]);
	timelineCursor.set(0);
	timelineUsers.set([]);
	timelineHasMore.set({ before: false, after: false });
	timelineLoading.set(false);
	timelinePinned.set(new Set());
	lastTimelineAnchorId = null;

	// Restore the hunter mode we forced on at open.
	if (hunterModeBeforeTimeline !== null) {
		setHunterMode(hunterModeBeforeTimeline);
		hunterModeBeforeTimeline = null;
	}
}

// Content filters narrow the walk too: when they change during an active walk,
// reload the window around the current photo so filtered-out photos drop out (the
// map already hides them via navigablePhotos; this keeps the list in step). The
// immediate fire on subscribe is a no-op — no walk is active at module load.
filters.subscribe(() => {
	if (get(timelineActive)) reloadAroundCursor();
});

// Hunter mode is an invariant of an open walk (its mostly-non-featured photos
// aren't navigable in tourist mode). So leaving hunter mode while the walk is open
// closes it — and honours the choice: clear the saved mode so stopTimeline doesn't
// turn hunter back on. (setHunterMode(true) at open fires on=true → no-op here; the
// restore on a normal close runs after timelineActive is already false → no-op.)
hunterMode.subscribe(on => {
	if (!on && get(timelineActive)) {
		hunterModeBeforeTimeline = null;
		stopTimeline();
	}
});

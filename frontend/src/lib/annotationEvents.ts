// Shared types + pure helpers for the annotation event log, used by both the
// global admin log (/admin/annotations) and the per-photo history view
// (/photo/[uid]/annotations). Anything stateful (fetching, the undo dialog)
// stays in the pages; only pure, display-oriented logic lives here.

export interface ModInfo {
	action: string;
	reason: string | null;
	moderator_username: string | null;
}

export interface AnnotationEvent {
	id: string;
	photo_id: string;
	user_id: string;
	username: string | null;
	actor_role: string | null;
	event_type: 'created' | 'updated' | 'deleted' | string;
	body: string | null;
	target: unknown;
	is_current: boolean;
	superseded_by: string | null;
	created_at: string;
	photo_lat: number | null;
	photo_lon: number | null;
	photo_bearing: number | null;
	photo_width: number | null;
	prev_body: string | null;
	superseded_by_event: { id: string; event_type: string; username: string | null } | null;
	moderation: ModInfo | null;
	reverted: ModInfo | null;
}

// The prior text this event replaced/removed (label depends on the event kind).
export function prevLabel(ev: AnnotationEvent): string {
	return ev.event_type === 'deleted' ? 'removed' : 'was';
}

// "undo_create" → "undo create", for display.
export function modAction(m: ModInfo): string {
	return m.action.replace(/_/g, ' ');
}

// Events by ordinary users (anyone who isn't an admin or moderator) are the
// ones worth a moderator's attention, so their username is highlighted.
export function isOrdinary(ev: AnnotationEvent): boolean {
	return !['admin', 'moderator'].includes((ev.actor_role ?? '').toLowerCase());
}

// A tombstone (deleted) carries no body; created/updated show a short preview.
export function bodyPreview(ev: AnnotationEvent): string {
	if (ev.event_type === 'deleted') return '(annotation removed)';
	const b = (ev.body ?? '').trim();
	return b === '' ? '(empty)' : b;
}

// What the undo of this event will do, for the button/dialog wording. Only the
// current tip of a chain can be undone (backend enforces it too).
export function undoLabel(ev: AnnotationEvent): string {
	if (ev.event_type === 'created') return 'Remove this annotation';
	if (ev.event_type === 'deleted') return 'Restore this annotation';
	return 'Revert this edit';
}

// Pixel-space bbox of the annotation target. Handles both the Annotorious v3
// RECTANGLE selector (geometry.bounds in image pixels — what the app writes)
// and the older FragmentSelector `xywh=pixel:` form.
export function targetXywh(ev: AnnotationEvent): { x: number; y: number; w: number; h: number } | null {
	const sel = (ev.target as any)?.selector ?? ev.target;
	if (!sel) return null;

	const b = sel.geometry?.bounds;
	if (b && [b.minX, b.minY, b.maxX, b.maxY].every((n: unknown) => typeof n === 'number')) {
		return { x: b.minX, y: b.minY, w: b.maxX - b.minX, h: b.maxY - b.minY };
	}

	const value = typeof sel === 'string' ? sel : sel?.value;
	if (typeof value === 'string') {
		const m = value.match(/xywh=pixel:([\d.]+),([\d.]+),([\d.]+),([\d.]+)/);
		if (m) {
			const [, x, y, w, h] = m.map(Number);
			return { x, y, w, h };
		}
	}
	return null;
}

// A zoomview "share link": the map URL opens the photo zoomed to the annotation.
// OSD viewport bounds normalize BOTH axes by the image width, so px/width.
export function zoomLink(ev: AnnotationEvent): string | null {
	const xy = targetXywh(ev);
	if (!xy || !ev.photo_width || ev.photo_lat == null || ev.photo_lon == null) return null;
	const W = ev.photo_width;
	const b = { x1: xy.x / W, y1: xy.y / W, x2: (xy.x + xy.w) / W, y2: (xy.y + xy.h) / W };
	const p = new URLSearchParams({
		lat: String(ev.photo_lat),
		lon: String(ev.photo_lon),
		zoom: '20',
		photo: `hillview-${ev.photo_id}`,
		x1: b.x1.toFixed(6),
		y1: b.y1.toFixed(6),
		x2: b.x2.toFixed(6),
		y2: b.y2.toFixed(6),
	});
	if (ev.photo_bearing != null) p.set('bearing', String(ev.photo_bearing));
	return `/?${p.toString()}`;
}

// Group a flat event list into annotation chains. Each chain is one logical
// annotation's timeline, oldest → newest (created, then each edit, then the
// current tip or a delete tombstone), linked via superseded_by. Chains are
// returned most-recently-active first (by their tip's timestamp).
//
// superseded_by points from an OLD event to the NEW one that replaced it, so a
// chain root is any event no other event's superseded_by references. If the
// fetch was truncated a root may carry a prev_body (a predecessor we didn't
// receive) — the partial chain is shown as-is.
export function groupIntoChains(events: AnnotationEvent[]): AnnotationEvent[][] {
	const byId = new Map(events.map((e) => [e.id, e]));
	const referenced = new Set<string>();
	for (const e of events) {
		if (e.superseded_by) referenced.add(e.superseded_by);
	}

	const chains: AnnotationEvent[][] = [];
	for (const root of events) {
		if (referenced.has(root.id)) continue; // not a chain head
		const chain: AnnotationEvent[] = [];
		const seen = new Set<string>();
		let cur: AnnotationEvent | undefined = root;
		while (cur && !seen.has(cur.id)) {
			seen.add(cur.id);
			chain.push(cur);
			cur = cur.superseded_by ? byId.get(cur.superseded_by) : undefined;
		}
		chains.push(chain);
	}

	chains.sort((a, b) => {
		const ta = a[a.length - 1].created_at;
		const tb = b[b.length - 1].created_at;
		return tb < ta ? -1 : tb > ta ? 1 : 0;
	});
	return chains;
}

// The final, live version of a chain: its tip. This is the ONLY version safe to
// surface to ordinary users — an intermediate edit could itself be spam that was
// later replaced, so a user-facing history must show the current tip, never the
// replacer of their own edit.
export function chainTip(chain: AnnotationEvent[]): AnnotationEvent {
	return chain[chain.length - 1];
}

// A zoom link for the chain — the annotation's spot on the photo. A delete
// tombstone carries no target, so for a removed chain fall back to the most
// recent event that still had one (so a moderator can still see where it was).
export function chainZoomLink(chain: AnnotationEvent[]): string | null {
	for (let i = chain.length - 1; i >= 0; i--) {
		const link = zoomLink(chain[i]);
		if (link) return link;
	}
	return null;
}

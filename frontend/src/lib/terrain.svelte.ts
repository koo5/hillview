/**
 * Terrain mode — stores and API plumbing around the pure model in
 * terrainModel.ts (design record: docs/terrain-mode.md).
 *
 * The artifact/list API is the enrichment workbench's /terrain endpoints for
 * now, pointed at via VITE_TERRAIN_API (e.g. http://localhost:8070/api);
 * graduation to the main backend is an open question in the design doc. The
 * mode button only appears when a base is configured.
 */
import { derived, get, writable } from 'svelte/store';
import { spatialState } from '$lib/mapState';
import {
	gridMetaOf,
	nearestRenderWithin,
	type TerrainRender
} from '$lib/terrainModel';
import { normalizeRect, wedgeFromRect, type TerrainPick, type ViewRect } from '$terrain/depthPanoViewer';
import type { Peak } from '$terrain/peakLabels';

export const terrainApiBase: string | null = import.meta.env.VITE_TERRAIN_API || null;
export const terrainModeAvailable = !!terrainApiBase;

export const terrainRenders = writable<TerrainRender[]>([]);
export const terrainError = writable<string | null>(null);

/** The range circle's spatial selection — nearest render within range. */
export const selectedTerrainRender = derived(
	[terrainRenders, spatialState],
	([renders, spatial]) => nearestRenderWithin(renders, spatial.center, spatial.range)
);

/** A rect parsed from tx1..ty2 URL params at page load — the zoom view's
 * x1..y2 convention under a terrain-namespaced twin, so terrain deep links
 * can never be mistaken for photo zoom-view deep links (that was the URL
 * open question in the design doc; namespacing settles it). Consumed by the
 * FIRST viewer load after the pane mounts, then cleared. Parsed here at
 * module init (URL params are static at page load) so no component mount
 * ordering can race the capture. */
export const pendingTerrainRect = writable<ViewRect | null>(null);

export function parseTerrainRectParams(params: URLSearchParams): ViewRect | null {
	const [tx1, ty1, tx2, ty2] = ['tx1', 'ty1', 'tx2', 'ty2'].map((k) => params.get(k));
	if (tx1 === null || ty1 === null || tx2 === null || ty2 === null) return null;
	const r = {
		x1: parseFloat(tx1),
		y1: parseFloat(ty1),
		x2: parseFloat(tx2),
		y2: parseFloat(ty2)
	};
	if (![r.x1, r.y1, r.x2, r.y2].every(Number.isFinite) || r.x2 <= r.x1) return null;
	// "URL rect x may leave [0, 1] and is normalized on parse" — the seam
	return normalizeRect(r);
}

if (typeof window !== 'undefined') {
	pendingTerrainRect.set(parseTerrainRectParams(new URLSearchParams(window.location.search)));
}

/** The pane's viewport rect (zoom view convention), for the derived wedge
 * and — once the URL open question is settled — URL sync. Pane-owned. */
export const terrainViewRect = writable<ViewRect | null>(null);

/** The last depth click-back, for the map's ray + distance label. */
export const terrainPick = writable<TerrainPick | null>(null);

/** "The map shows a view wedge at the selected viewpoint, purely derived
 * from the rect: center-x → azimuth, width → wedge FOV. One-directional,
 * pane → map." Null until a viewable render is selected and its viewer has
 * reported a rect. */
export const terrainWedge = derived(
	[selectedTerrainRender, terrainViewRect],
	([sel, rect]) => {
		const meta = sel ? gridMetaOf(sel) : null;
		if (!sel || !meta || !rect) return null;
		const w = wedgeFromRect(meta, rect);
		return { lat: sel.lat, lon: sel.lon, ...w };
	}
);

// Selection change invalidates pane-derived state: the rect belongs to the
// outgoing render's viewer, and a stale pick would draw a ray from the wrong
// viewpoint.
let lastSelectedId: string | null = null;
selectedTerrainRender.subscribe((sel) => {
	const id = sel?.id ?? null;
	if (id !== lastSelectedId) {
		lastSelectedId = id;
		terrainViewRect.set(null);
		terrainPick.set(null);
	}
});

/** version: artifactVersion(render) — a stable cache key that changes only
 * when new artifact bytes exist (milestone partials / completion), so the
 * viewer reloads exactly then and never per poll tick. */
export function terrainPreviewUrl(id: string, version = '0'): string {
	return `${terrainApiBase}/terrain/renders/${id}/preview?v=${encodeURIComponent(version)}`;
}

export function terrainDepthUrl(id: string, version = '0'): string {
	return `${terrainApiBase}/terrain/renders/${id}/depth?v=${encodeURIComponent(version)}`;
}

export async function refreshTerrainRenders(): Promise<void> {
	if (!terrainApiBase) return;
	try {
		const r = await fetch(`${terrainApiBase}/terrain/renders`);
		if (!r.ok) throw new Error(`HTTP ${r.status}`);
		terrainRenders.set(((await r.json()) as { renders: TerrainRender[] }).renders);
		terrainError.set(null);
	} catch (e) {
		terrainError.set(e instanceof Error ? e.message : String(e));
	}
}

/** Progress ship-order step 1: the client polls while anything is pending
 * (renders are seconds-to-tens-of-seconds, % alone carries most of the UX).
 * Idle renders poll slowly too so freshly enqueued work appears. */
const POLL_PENDING_MS = 3000;
const POLL_IDLE_MS = 15000;
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let polling = false;

function scheduleNextPoll(): void {
	if (!polling) return;
	const pending = get(terrainRenders).some(
		(r) => r.status !== 'done' && r.status !== 'error' && r.status !== 'failed'
	);
	pollTimer = setTimeout(async () => {
		await refreshTerrainRenders();
		scheduleNextPoll();
	}, pending ? POLL_PENDING_MS : POLL_IDLE_MS);
}

export function startTerrainPolling(): void {
	if (polling) return;
	polling = true;
	refreshTerrainRenders().then(scheduleNextPoll);
}

export function stopTerrainPolling(): void {
	polling = false;
	if (pollTimer) clearTimeout(pollTimer);
	pollTimer = null;
}

export async function enqueueTerrainRender(lat: number, lon: number): Promise<void> {
	if (!terrainApiBase) return;
	const r = await fetch(`${terrainApiBase}/terrain/enqueue`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ lat, lon })
	});
	if (!r.ok) throw new Error(`enqueue failed: HTTP ${r.status}`);
	await refreshTerrainRenders();
}

/** OSM natural=peak candidates around a render's viewpoint, cached per
 * render id for the session (peaks don't move; the API caches upstream of
 * Overpass too). Visibility against the depth buffer is the viewer's job —
 * this list is just "peaks in range". */
const peaksCache = new Map<string, Peak[]>();

export async function terrainPeaksFor(r: TerrainRender): Promise<Peak[]> {
	if (!terrainApiBase) return [];
	const hit = peaksCache.get(r.id);
	if (hit) return hit;
	const radius = Math.min(
		200_000,
		typeof (r.meta as { max_distance_m?: number } | null)?.max_distance_m === 'number'
			? (r.meta as { max_distance_m: number }).max_distance_m
			: 100_000
	);
	const resp = await fetch(
		`${terrainApiBase}/terrain/peaks?lat=${r.lat}&lon=${r.lon}&radius_m=${radius}`
	);
	if (!resp.ok) throw new Error(`peaks: HTTP ${resp.status}`);
	const peaks = ((await resp.json()) as { peaks: Peak[] }).peaks;
	peaksCache.set(r.id, peaks);
	return peaks;
}

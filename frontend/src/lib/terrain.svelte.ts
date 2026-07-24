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
	nearestRenderWithin,
	type TerrainRender
} from '$lib/terrainModel';
import { wedgeFromRect, type TerrainPick, type ViewRect } from '$terrain/depthPanoViewer';

export const terrainApiBase: string | null = import.meta.env.VITE_TERRAIN_API || null;
export const terrainModeAvailable = !!terrainApiBase;

export const terrainRenders = writable<TerrainRender[]>([]);
export const terrainError = writable<string | null>(null);

/** The range circle's spatial selection — nearest render within range. */
export const selectedTerrainRender = derived(
	[terrainRenders, spatialState],
	([renders, spatial]) => nearestRenderWithin(renders, spatial.center, spatial.range)
);

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
		if (!sel?.meta || !rect) return null;
		const w = wedgeFromRect(sel.meta, rect);
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

export function terrainPreviewUrl(id: string): string {
	return `${terrainApiBase}/terrain/renders/${id}/preview`;
}

export function terrainDepthUrl(id: string): string {
	return `${terrainApiBase}/terrain/renders/${id}/depth`;
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

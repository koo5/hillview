<script lang="ts">
	// EXPERIMENT: overlay a terrain render's skyline onto its source pano.
	//
	// Horizontal alignment is automatic where a calibration exists (pie:
	// centre bearing + fov, assumed 90° otherwise); the VERTICAL anchor has
	// no data behind it — horizon line position and °/px scale are manual
	// sliders, initialized with the equirectangular square-pixel guess
	// (px/deg vertical = px/deg horizontal). Note: a good manual fit here IS
	// a vertical calibration — saving it is the obvious next step once this
	// UX proves out.
	//
	// The fit is a piecewise-linear warp: N handles ride the dashed horizon
	// line, each dragging its neighborhood up/down (`warp`) AND sideways
	// (`hwarp`, azimuth offset — Shift-drag locks to vertical); both stored
	// in DEGREES so they survive zoom/rescale. Two handles = plain
	// roll+offset; more handles absorb per-seam pano stitching wobble, and
	// the sideways axis is what a stitched pano's local stretch needs — a
	// vertical warp alone can put the curve on the ridge at the handle while
	// the peaks left and right of it stay displaced. A global roll slider
	// (shear approximation) sits on top for fine trim.
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { apiBase } from '$lib/config';
	import { azimuthForColumn, parseDepthBlob, pickFromDepthOrHorizon, type TerrainMeta, type TerrainPick } from '$terrain/depthPanoViewer';
	import {
		hitSkyLabel,
		labelEvidence,
		labelText,
		layoutSkyLabels,
		PLACE_KINDS,
		projectPeaks,
		type Peak,
		type PeakMark,
		type SkyLabel
	} from '$terrain/peakLabels';
	import { paintSkyPills } from '$terrain/labelPills';
	// the pano layer is an OpenSeadragon viewer over the photo's DZI pyramid:
	// sizes.full is capped at 8192 px wide by the worker, the pyramid has
	// every pixel — same tile-source glue as the main app's zoom view
	import { buildTileSource, type DziPyramid } from '$zoomview/tileSource';
	import { OSD_VIEWER_DEFAULTS } from '$zoomview/viewerInit';
	// the fit's geometry is SHARED with the main app's zoom view, so a
	// graduated overlay draws exactly where it was fitted here
	import {
		createOverlayProjector,
		resampleWarp,
		skylineFromDepth,
		resampleSteps,
		uniformKnots,
		warpAt as warpAtShared,
		wrapDelta,
		type OverlayFit
	} from '$terrain/overlayFit';

	interface PhotoInfo {
		id: string;
		title: string | null;
		sizes: Record<string, { url?: string; pyramid?: DziPyramid }> | null;
		width: number | null;
		height: number | null;
		pie: {
			bearing: number;
			half: number;
			calibrated: boolean;
			/** from calibratedProjection/calibratedX0 facts, when accepted */
			projection?: string;
			x0?: number;
			/** from a piecewise (stitched) calibration: seams + per-panel
			 * shift/scale, the handle model verbatim */
			stitch?: { knots: number[]; hwarp: number[]; hscale: number[] };
		} | null;
	}
	interface RenderRow {
		id: string;
		status: string;
		enqueued_at: string;
		meta: (TerrainMeta & { dsm_stack?: string }) | null;
	}

	let photoId = $state('');
	let photo = $state<PhotoInfo | null>(null);
	let render = $state<RenderRow | null>(null);
	let depth: Uint16Array | null = null;
	let err = $state<string | null>(null);
	let status = $state('');
	let saving = $state(false);
	let saveMsg = $state('');
	// graduation: approving the saved fit fact is what publishes this overlay
	// to the main app (docs/terrain-overlay-graduation.md). No separate flag —
	// the export derives its work list from approved facts.
	let fitFact = $state<string | null>(null);
	let fitApproved = $state(false);
	let gradBusy = $state(false);
	let gradMsg = $state('');
	let draftState = $state('');
	let suppressDraft = true; // no autosave until a photo's state is restored
	let draftTimer: ReturnType<typeof setTimeout> | undefined;
	// cross-tab live sync: every alignment change writes a per-photo
	// localStorage key (instant `storage` events in the OTHER tabs), so the
	// same pano can be open in several windows zoomed at different sections
	// while one shared fit is adjusted. Each tab keeps its own zoom/pan.
	// `lastSync` breaks echo loops: applying a received state re-runs the
	// write effect with an identical serialization, which is skipped.
	const liveKey = (id: string) => `overlay-fit-live:${id}`;
	let lastSync = '';
	let lastTs = 0; // saved_at of the newest state written or applied here
	// render the saved fit / draft was made against — preferred over the newest
	let preferRender: string | null = null;
	/** canonical alignment serialization WITHOUT identity/timestamp — echo
	 * detection must ignore saved_at, since every local write re-stamps it */
	const bareOf = (f: Record<string, unknown>) => {
		const { saved_at: _s, photo_id: _p, render_id: _r, ...rest } = f;
		return JSON.stringify(rest);
	};
	// BroadcastChannel is the delivery mechanism (explicit postMessage — no
	// storage-event value-changed quirks); localStorage keeps the freshest
	// state for load-time restore, and its storage event doubles as fallback
	let bc: BroadcastChannel | null = null;

	// phone-home debug log: batched to the API (POST /terrain/client-log) so
	// mobile sessions are inspectable without tethered devtools — read back
	// with GET /terrain/client-log?session=<id> or `docker logs enrich_api`
	const dbgSession = Math.random().toString(36).slice(2, 8);
	let dbgQueue: { t: string; msg: string }[] = [];
	let dbgTimer: ReturnType<typeof setTimeout> | undefined;
	function flushDlog() {
		if (!dbgQueue.length) return;
		const body = JSON.stringify({
			session: dbgSession,
			page: location.pathname + location.search,
			ua: navigator.userAgent,
			messages: dbgQueue
		});
		dbgQueue = [];
		try {
			fetch(`${apiBase}/terrain/client-log`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body,
				keepalive: true
			}).catch(() => {});
		} catch {
			/* offline — local console still has it */
		}
	}
	function dlog(msg: string) {
		console.log(`overlay[${dbgSession}]: ${msg}`);
		dbgQueue.push({ t: new Date().toISOString().slice(11, 23), msg });
		if (dbgQueue.length >= 40) flushDlog();
		else {
			clearTimeout(dbgTimer);
			dbgTimer = setTimeout(flushDlog, 1000);
		}
	}

	/** apply a live snapshot broadcast by a sibling window */
	function applyRemote(raw: string) {
		if (!photo) return;
		try {
			const f = JSON.parse(raw) as OverlayFit;
			lastSync = bareOf(f as unknown as Record<string, unknown>);
			lastTs = f.saved_at ?? Date.now();
			const vk = applyFitState(f);
			if (vk === null) visLog = visLogMax;
			else setFogKm(vk);
		} catch {
			/* malformed live state — ignore */
		}
	}

	// OverlayFit (the saved manual alignment, hv:terrainOverlayFit) is defined
	// in $terrain/overlayFit — the main app reads the same shape.

	// manual alignment: bearing trim + fov (horizontal, for uncalibrated
	// panos), horizon position + vertical scale (always manual)
	let bearingOffset = $state(0);
	let fovDeg = $state(90);
	let horizonPct = $state(50);
	let vScale = $state(1);
	// pano output projection — from the stitch .pto p-line (f0 rectilinear,
	// f1 cylindrical, f2 equirect); it VARIES per pano, never assume (see
	// docs/pano-source-archaeology.md — e.g. board pano 333e8851 is f0)
	let proj = $state<'equirect' | 'cylindrical' | 'rectilinear'>('equirect');
	let rollDeg = $state(0);
	let showCurve = $state(true);
	// peak labels: candidates from /terrain/peaks, visibility decided against
	// the depth buffer (projectPeaks) exactly like the viewer — named anchors
	// make the manual fit tractable
	let showLabels = $state(true);
	// the photo's own annotations as alignment evidence: a tick at each rect's
	// x on the pano (cyan) and, where the annotation has an anchor, a tick at
	// that anchor's azimuth under the current fit (magenta) — the two coincide
	// when the fit is right (same rows as the calibration bench, effective rect)
	let showAnns = $state(true);
	interface CalRow {
		annotation_id: string;
		body: string;
		rect_x: number | null;
		azimuth: number | null;
		km: number | null;
		rule: string;
		usable: boolean;
	}
	let annRows = $state<CalRow[]>([]);
	// click anywhere on the pano: the direction it looks under the current fit,
	// resolved through the depth buffer to a place (or the horizon there)
	let pick = $state<(TerrainPick & { elev_deg: number }) | null>(null);
	let pickPt: { x: number; y: number } | null = null;
	let showPlaces = $state(true);
	let peaks: Peak[] = [];
	let marks = $state<PeakMark[]>([]);
	// pills currently on screen (for tap → evidence) and the last tapped one
	let placedPills: (SkyLabel & { kind?: string; cls?: PeakMark['class']; mark: PeakMark })[] = [];
	let labelInfo = $state<PeakMark | null>(null);
	// fog: visibility cutoff for the skyline (log10 metres on the slider;
	// at the top end = the render's full max_distance = no cutoff)
	let visLog = $state(6);
	const maxDistM = $derived(render?.meta?.max_distance_m ?? 200000);
	const visLogMax = $derived(Math.log10(maxDistM));
	const visCutoffM = $derived(visLog >= visLogMax - 0.005 ? null : Math.pow(10, visLog));
	const visKm = $derived(+((visCutoffM ?? maxDistM) / 1000).toFixed(1));
	function setFogKm(km: number) {
		if (!Number.isFinite(km) || km <= 0) return;
		visLog = Math.min(visLogMax, Math.log10(km * 1000));
	}
	// vertical warp: control-point offsets in degrees (index 0 = left edge,
	// last = right edge), linearly interpolated between; always reassigned
	// (never mutated in place) so the redraw effect tracks it by reference
	let warp = $state<number[]>([0, 0]);
	// horizontal (azimuth) shift per SEGMENT, degrees (hwarp[k] = the panel
	// starting at handle k; last entry unused): dragging a handle sideways
	// says "the terrain the model draws here actually sits THERE" and moves
	// that panel and every panel to its right rigidly (Alt: this panel only)
	// — a stitched pano's seams are steps, which the vertical warp cannot
	// absorb. Kept the same length as `warp`.
	let hwarp = $state<number[]>([0, 0]);
	// per-panel SCALE (about the panel's centre, both axes) — a frame stitched
	// at the wrong focal length: Ctrl-drag a handle sideways to pull the
	// panel's edge in/out, or type it in the panel editor
	let hscale = $state<number[]>([1, 1]);
	// how far the baked document reaches (labels), km — the ceiling of the
	// zoom view's fog slider. 150 unless changed; the fog slider is the
	// DEFAULT the viewer opens with
	const DEFAULT_MAX_VIS_KM = 180; // matches the default render range
	let maxVisKm = $state(DEFAULT_MAX_VIS_KM);
	// handle positions (fractions of the width). Equally spaced by default;
	// double-click the pano to put a seam exactly where the stitch has one,
	// double-click a handle to remove it
	let knots = $state<number[]>([0, 1]);
	const isUniform = (k: number[]) => k.every((v, i) => Math.abs(v - i / (k.length - 1)) < 1e-6);
	// the panel whose numbers the inline editor shows (set by clicking a handle)
	let selectedSeg = $state<number | null>(null);
	const MAX_SEGMENTS = 48;
	/** equal spacing with n segments — resamples every per-handle array */
	function setSegments(n: number) {
		const handles = Math.max(2, Math.min(MAX_SEGMENTS + 1, Math.round(n) + 1));
		if (handles === warp.length && isUniform(knots)) return;
		const oldKnots = knots;
		const nk = uniformKnots(handles);
		warp = nk.map((f) => warpAtShared(warp, f, oldKnots));
		hwarp = resampleSteps(hwarp, handles, 0, oldKnots);
		hscale = resampleSteps(hscale, handles, 1, oldKnots);
		knots = nk;
		selectedSeg = null;
	}
	/** put a seam at horizontal fraction f: the panel it splits keeps its
	 * shift/scale on both sides, the vertical warp is interpolated there */
	function insertKnot(f: number) {
		f = Math.min(0.999, Math.max(0.001, f));
		if (knots.length >= MAX_SEGMENTS + 1) return;
		let k = 0;
		while (k < knots.length - 1 && f >= knots[k + 1]) k++;
		if (Math.abs(f - knots[k]) < 0.002 || Math.abs(f - knots[k + 1]) < 0.002) return; // on a knot already
		const w = warpAtShared(warp, f, knots);
		knots = [...knots.slice(0, k + 1), f, ...knots.slice(k + 1)];
		warp = [...warp.slice(0, k + 1), w, ...warp.slice(k + 1)];
		hwarp = [...hwarp.slice(0, k + 1), hwarp[k], ...hwarp.slice(k + 1)];
		hscale = [...hscale.slice(0, k + 1), hscale[k], ...hscale.slice(k + 1)];
		selectedSeg = k + 1;
	}
	/** remove an interior handle: the two panels merge, the left one's
	 * shift/scale win */
	function removeKnot(i: number) {
		if (i <= 0 || i >= knots.length - 1) return;
		knots = knots.filter((_, j) => j !== i);
		warp = warp.filter((_, j) => j !== i);
		hwarp = hwarp.filter((_, j) => j !== i);
		hscale = hscale.filter((_, j) => j !== i);
		selectedSeg = null;
	}
	/** the panel a handle acts on: the one to its right, or for the last
	 * handle the one to its left */
	const panelOf = (i: number) => Math.min(i, warp.length - 2);

	// ---- explicit save / revert / undo: what is SAVED (the fact), whether
	// the live alignment differs from it, and a history of settled states.
	// The auto-draft keeps running underneath (it is what lets two windows
	// share the working state) — but it is no longer the only state you can
	// see, and a stray drag is one Ctrl+Z away.
	let savedFit = $state<OverlayFit | null>(null);
	const dirty = $derived.by(() => {
		void proj; void bearingOffset; void fovDeg; void horizonPct; void vScale; void rollDeg; void warp; void hwarp; void visLog;
		if (!photo) return false;
		const live = bareOf(liveFit() as unknown as Record<string, unknown>);
		return live !== (savedFit ? bareOf(savedFit as unknown as Record<string, unknown>) : '');
	});
	let history = $state<string[]>([]);
	let histIdx = $state(-1);
	let skipHistory = false; // set while applying a snapshot, so it isn't re-pushed
	let histTimer: ReturnType<typeof setTimeout> | undefined;
	/** one history entry per SETTLED change: a drag's stream of moves or a
	 * slider's run of inputs coalesce into the state 500 ms after the last */
	function scheduleHistory() {
		clearTimeout(histTimer);
		histTimer = setTimeout(() => {
			if (!skipHistory) pushHistory(JSON.stringify(liveFit()));
		}, 500);
	}
	/** history starts at the state a load landed on, so the first Ctrl+Z
	 * after the first change goes back to it */
	function seedHistory() {
		history = [JSON.stringify(liveFit())];
		histIdx = 0;
	}
	function pushHistory(snapshot: string) {
		if (skipHistory) return;
		if (histIdx >= 0 && history[histIdx] === snapshot) return;
		const next = history.slice(0, histIdx + 1);
		next.push(snapshot);
		if (next.length > 100) next.shift();
		history = next;
		histIdx = next.length - 1;
	}
	function applySnapshot(raw: string) {
		clearTimeout(histTimer); // a pending push would re-record the state we are leaving
		skipHistory = true;
		try {
			applyRemoteFit(JSON.parse(raw) as OverlayFit);
		} finally {
			// the autosave effect runs after this tick; release the guard then
			setTimeout(() => (skipHistory = false), 0);
		}
	}
	function undo() {
		if (histIdx <= 0) return;
		histIdx -= 1;
		applySnapshot(history[histIdx]);
	}
	function redo() {
		if (histIdx >= history.length - 1) return;
		histIdx += 1;
		applySnapshot(history[histIdx]);
	}
	/** back to the last SAVED fit: the draft and this tab's live key go
	 * with it (undoable like any other change) */
	function revertToSaved() {
		if (!photo || !savedFit) return;
		applyRemoteFit(savedFit);
		api.del(`/terrain/overlay-draft?photo_id=${photo.id}`).catch(() => {});
		try {
			localStorage.removeItem(liveKey(photo.id));
		} catch {
			/* fine */
		}
		lastSync = '';
		draftState = '';
		saveMsg = 'reverted to the saved fit';
	}
	/** apply a fit to the knobs the way a remote/live snapshot is applied
	 * (fog included), without touching sync bookkeeping */
	function applyRemoteFit(f: OverlayFit) {
		const vk = applyFitState(f);
		if (vk === null) visLog = visLogMax;
		else setFogKm(vk);
	}

	// view transform: screen = base * z + (tx, ty). Base = the image
	// contain-fitted into the fixed-height stage at zoom 1 (baseW × baseH
	// CSS px, centered by the clamp), so a wide pano gets vertical room to
	// zoom into instead of staying a fit-to-width noodle. OpenSeadragon owns
	// the pan/zoom; (z, tx, ty) mirror its viewport (syncView) so the overlay
	// canvas and every hit-test keep working in base space unchanged.
	let z = $state(1);
	let tx = $state(0);
	let ty = $state(0);
	let baseW = $state(0);
	let baseH = $state(0);
	let naturalW = $state(0); // image native px (the pyramid's true size)
	let naturalH = $state(0);

	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let viewer: any = null; // OpenSeadragon.Viewer, alive while the stage is
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let OSD: any = null;
	let overlay: HTMLCanvasElement;
	let stageEl: HTMLDivElement;

	const HANDLE_R = 7;
	const HANDLE_HIT = 14;

	const imgUrl = $derived.by(() => {
		const s = photo?.sizes;
		if (!s) return null;
		for (const k of ['full', '1600', '1024', '640', '320']) {
			const u = s[k]?.url;
			if (u) return u;
		}
		return null;
	});
	/** the DZI pyramid (worker skips it below 2048 px; older photos may lack
	 * one) — without it the viewer opens imgUrl as a single image */
	const pyramid = $derived.by((): DziPyramid | null => {
		const p = photo?.sizes?.full?.pyramid;
		return p && p.type === 'dzi' ? p : null;
	});

	async function load() {
		preferRender = null;
		err = null;
		photo = null;
		render = null;
		depth = null;
		peaks = [];
		marks = [];
		saveMsg = '';
		draftState = '';
		suppressDraft = true;
		savedFit = null;
		history = [];
		histIdx = -1;
		resetView();
		warp = warp.map(() => 0);
		rollDeg = 0;
		horizonPct = 50;
		vScale = 1;
		if (!photoId) return;
		try {
			dlog(`load start photo=${photoId}`);
			status = 'loading photo…';
			const pd = await api.get<{ photo: PhotoInfo }>(`/photos/${photoId}`);
			photo = pd.photo;
			dlog(`photo ok "${photo.title}" pie=${JSON.stringify(photo.pie)}`);
			try {
				annRows = (await api.get<{ rows: CalRow[] }>(`/panos/${photoId}/calibration`)).rows.filter(
					(r) => r.rect_x != null
				);
			} catch {
				annRows = [];
			}
			pick = null;
			pickPt = null;
			pieDefaults();
			// restore order: pie defaults → saved fit → draft (newest working
			// state wins; fog applies later — the render load below resets
			// the slider to full first)
			let savedVisKm: number | null = null;
			const applyFit = (f: OverlayFit) => {
				savedVisKm = applyFitState(f);
			};
			try {
				const sf = await api.get<{
					render_id?: string | null;
					fit: OverlayFit | null;
					fact?: string;
					approved?: boolean;
				}>(`/terrain/overlay-fit?photo_id=${photoId}`);
				if (sf.render_id) preferRender = sf.render_id;
				if (sf.fit) {
					applyFit(sf.fit);
					savedFit = sf.fit;
					fitFact = sf.fact ?? null;
					fitApproved = !!sf.approved;
					saveMsg = 'restored saved fit';
				}
			} catch {
				/* no saved fit is fine */
			}
			// draft (server) vs live key (this browser): NEWEST wins — this
			// tab's live key may be staler than a draft another window kept
			// writing after this one went quiet
			let restored: { f: OverlayFit; src: string } | null = null;
			try {
				const dr = await api.get<{ draft: OverlayFit | null }>(
					`/terrain/overlay-draft?photo_id=${photoId}`
				);
				if (dr.draft) restored = { f: dr.draft, src: 'draft' };
			} catch {
				/* no draft is fine */
			}
			try {
				const raw = localStorage.getItem(liveKey(photoId));
				if (raw) {
					const f = JSON.parse(raw) as OverlayFit;
					if (!restored || (f.saved_at ?? 0) >= (restored.f.saved_at ?? 0))
						restored = { f, src: 'live tab state' };
				}
			} catch {
				/* no cross-tab state is fine */
			}
			if (restored) {
				applyFit(restored.f);
				lastSync = bareOf(restored.f as unknown as Record<string, unknown>);
				lastTs = restored.f.saved_at ?? 0;
				const differs =
					!savedFit ||
					bareOf(restored.f as unknown as Record<string, unknown>) !==
						bareOf(savedFit as unknown as Record<string, unknown>);
				saveMsg = differs
					? `restored ${restored.src} — unsaved changes since the last save (revert to drop them)`
					: `restored ${restored.src} (same as the saved fit)`;
				dlog(`restored ${restored.src} (saved_at=${restored.f.saved_at ?? 'none'})`);
			}

			status = 'loading render…';
			const rs = await api.get<{ renders: RenderRow[] }>(
				`/terrain/renders?photo_id=${photoId}`
			);
			const isDone = (r: RenderRow) => r.status === 'done' && !!r.meta && 'width' in r.meta;
			const done = (preferRender && rs.renders.find((r) => r.id === preferRender && isDone(r))) || rs.renders.find(isDone);
			if (!done) {
				status = '';
				err = 'no finished render for this photo — enqueue one on the terrain bench first';
				suppressDraft = false; // controls still usable; keep drafting
				seedHistory();
				return;
			}
			render = done;
			dlog(
				`render ${done.id.slice(0, 8)} ${done.meta?.width}x${done.meta?.height} ` +
					`max_d=${done.meta?.max_distance_m}`
			);
			skyCaches.clear();
			visLog = Math.log10(done.meta?.max_distance_m ?? 200000);
			if (savedVisKm !== null) setFogKm(savedVisKm);
			status = 'loading depth…';
			dlog('depth fetch…');
			const buf = await (await fetch(`${apiBase}/terrain/renders/${done.id}/depth`)).arrayBuffer();
			depth = parseDepthBlob(buf, done.meta!); // HVD1 header, or a legacy buffer at meta's size
			dlog(`depth ok ${(buf.byteLength / 1048576).toFixed(1)} MB`);
			// the fit is fully workable now — labels are cosmetic. Drafting/
			// sync must NOT wait for the peaks fetch (a cold Overpass pass can
			// take minutes; sitting at "loading peaks" used to silently
			// disable all persistence)
			suppressDraft = false;
			seedHistory();
			requestAnimationFrame(draw);
			status = 'loading peak labels… (fitting already works)';
			// label candidates arrive CHUNKED, nearest tiles first: small
			// individually-retryable requests with progressive label paint —
			// the monolithic pool fetch kept timing out on phones. A failed
			// chunk just thins the pool.
			try {
				const meta = done.meta!;
				const radius = Math.min(200_000, meta.max_distance_m ?? 100_000);
				const CHUNKS = 8;
				dlog(`peaks fetch… radius=${radius} chunks=${CHUNKS}`);
				peaks = [];
				let failedChunks = 0;
				for (let i = 0; i < CHUNKS; i++) {
					if (render?.id !== done.id) return; // superseded by a new load
					try {
						const resp = await fetch(
							`${apiBase}/terrain/peaks?lat=${meta.lat}&lon=${meta.lon}` +
								`&radius_m=${radius}&chunk=${i}&chunks=${CHUNKS}`,
							{ signal: AbortSignal.timeout(30_000) }
						);
						if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
						const pr = (await resp.json()) as { peaks?: Peak[] };
						peaks = peaks.concat(pr.peaks ?? []);
						marks = projectPeaks(meta, depth!, peaks);
						status = `loading peak labels ${i + 1}/${CHUNKS}… (fitting already works)`;
					} catch (e) {
						failedChunks++;
						dlog(`peaks chunk ${i + 1}/${CHUNKS} FAILED: ${e}`);
					}
				}
				dlog(`peaks done: ${peaks.length} candidates (${failedChunks} chunk(s) failed)`);
			} catch (e) {
				dlog(`peaks FAILED: ${e}`);
				peaks = [];
			}
			marks = done.meta && depth ? projectPeaks(done.meta, depth, peaks) : [];
			dlog(`marks placed: ${marks.length}`);
			status = '';
		} catch (e) {
			status = '';
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
			dlog(`load FAILED: ${err}`);
			// a failed load must not silently disable drafting/sync for the
			// session — the controls that DID restore are still adjustable
			suppressDraft = false;
		}
	}

	/** render skyline: per column, elevation angle of the topmost row whose
	 * terrain lies within cutoffM (null cutoff = any terrain; null entry =
	 * nothing visible in that column). Memoized per (render, cutoff): the
	 * scan is O(W×H) worst case and draw() runs per pan/zoom frame. */
	const skyCaches = new Map<string, (number | null)[]>();
	function skylineFor(
		meta: TerrainMeta,
		d: Uint16Array,
		cutoffM: number | null
	): (number | null)[] {
		const key = `${render?.id}:${cutoffM ?? 'full'}`;
		const hit = skyCaches.get(key);
		if (hit) return hit;
		const out = skylineFromDepth(meta, d, cutoffM);
		// scrubbing the fog slider caches one array per stop — cap the map
		if (skyCaches.size >= 8) skyCaches.delete(skyCaches.keys().next().value!);
		skyCaches.set(key, out);
		return out;
	}

	/** apply a fit/draft/live snapshot to the alignment knobs; returns its
	 * visibility_km (null = full) for the caller to apply once the render's
	 * fog range is known */
	function applyFitState(f: OverlayFit): number | null {
		// a fit made against a specific render (e.g. a refraction test) opens on it
		const rid = (f as { render_id?: string | null }).render_id;
		if (rid) preferRender = rid;
		proj = f.projection as typeof proj;
		fovDeg = f.fov_deg;
		bearingOffset = +wrapDelta(f.centre_bearing - (photo?.pie?.bearing ?? 0)).toFixed(2);
		horizonPct = f.horizon_pct;
		vScale = f.v_scale;
		rollDeg = f.roll_deg;
		if (f.warp?.length >= 2) warp = f.warp.slice();
		hwarp = f.hwarp && f.hwarp.length === warp.length ? f.hwarp.slice() : warp.map(() => 0);
		hscale = f.hscale && f.hscale.length === warp.length ? f.hscale.slice() : warp.map(() => 1);
		knots = f.knots && f.knots.length === warp.length ? f.knots.slice() : uniformKnots(warp.length);
		selectedSeg = null;
		maxVisKm = f.max_visibility_km ?? DEFAULT_MAX_VIS_KM;
		return f.visibility_km ?? null;
	}

	/** best-known defaults: bearing/fov/projection from the accepted
	 * calibration (via the pie — incl. the calibratedProjection fact),
	 * neutral vertical/warp/roll/fog */
	function pieDefaults() {
		if (photo?.pie) fovDeg = +(photo.pie.half * 2).toFixed(1);
		bearingOffset = 0;
		// never a stale projection from the previously loaded photo
		proj =
			photo?.pie?.projection === 'rectilinear' || photo?.pie?.projection === 'cylindrical'
				? photo.pie.projection
				: 'equirect';
		horizonPct = 50;
		vScale = 1;
		rollDeg = 0;
		// a piecewise calibration seeds the seams and per-panel shift/scale;
		// otherwise a neutral equally-spaced warp
		const st = photo?.pie?.stitch;
		if (st && st.knots?.length >= 2 && st.hwarp?.length === st.knots.length && st.hscale?.length === st.knots.length) {
			knots = st.knots.slice();
			warp = st.knots.map(() => 0);
			hwarp = st.hwarp.slice();
			hscale = st.hscale.slice();
		} else {
			// no stitch in the accepted calibration → a clean two-handle model;
			// keeping the current handle COUNT here left hand-placed seams alive
			// across "defaults"
			warp = [0, 0];
			hwarp = [0, 0];
			hscale = [1, 1];
			knots = uniformKnots(2);
			selectedSeg = null;
		}
		visLog = visLogMax;
		maxVisKm = DEFAULT_MAX_VIS_KM;
	}

	function resetToDefaults() {
		pieDefaults();
		saveMsg = '';
		draftState = '';
		if (photo) {
			api.del(`/terrain/overlay-draft?photo_id=${photo.id}`).catch(() => {});
			try {
				localStorage.removeItem(liveKey(photo.id));
			} catch {
				/* fine */
			}
			lastSync = '';
		}
	}

	function fitPayload() {
		return {
			...liveFit(),
			photo_id: photo!.id,
			render_id: render?.id ?? null,
			saved_at: Date.now()
		};
	}

	async function saveFit() {
		if (!photo) return;
		saving = true;
		saveMsg = '';
		try {
			const r = await api.post<{ run_id: string; fact: string }>(
				'/terrain/overlay-fit',
				fitPayload()
			);
			saveMsg = `saved ✓ run ${r.run_id.slice(0, 8)}`;
			savedFit = liveFit();
			// fits are content-addressed, so re-saving an alignment that was
			// already graduated lands on the SAME fact and keeps its approval;
			// a genuinely new alignment starts unapproved and has to be
			// graduated deliberately
			const wasFact = fitFact;
			fitFact = r.fact;
			if (wasFact !== r.fact) {
				fitApproved = false;
				gradMsg = '';
			}
			// the fact now carries this state — draft and live key are redundant
			draftState = '';
			api.del(`/terrain/overlay-draft?photo_id=${photo.id}`).catch(() => {});
			try {
				localStorage.removeItem(liveKey(photo.id));
			} catch {
				/* fine */
			}
			lastSync = '';
		} catch (e) {
			saveMsg =
				e instanceof ApiError ? `save failed: ${e.status} ${e.message}` : 'save failed';
		} finally {
			saving = false;
		}
	}

	/** publish (or unpublish) the saved fit: approving the fact is what puts
	 * this overlay in the graduation export's work list */
	async function toggleGraduate() {
		if (!photo || !fitFact) return;
		const want = !fitApproved;
		gradBusy = true;
		gradMsg = '';
		try {
			await api.post('/terrain/overlay-fit/graduate', {
				photo_id: photo.id,
				fact: fitFact,
				graduate: want
			});
			fitApproved = want;
			gradMsg = want ? 'queued for graduation' : 'withdrawn';
			dlog(`graduate=${want} fact=${fitFact.slice(-16)}`);
		} catch (e) {
			gradMsg = e instanceof ApiError ? `failed: ${e.status} ${e.message}` : 'failed';
		} finally {
			gradBusy = false;
		}
	}

	/** warp offset (degrees, + = up) at horizontal fraction 0..1 */
	const warpAt = (frac: number) => warpAtShared(warp, frac, knots);

	/** the live alignment as an OverlayFit — the shared projector's input, and
	 * the exact shape that gets saved, drafted and eventually graduated */
	function liveFit(): OverlayFit {
		return {
			projection: proj,
			centre_bearing: (photo?.pie?.bearing ?? 0) + bearingOffset,
			fov_deg: fovDeg,
			horizon_pct: horizonPct,
			v_scale: vScale,
			roll_deg: rollDeg,
			warp: [...warp],
			// only when they do something — an untouched fit keeps its shape
			...(hwarp.some((v) => v !== 0) ? { hwarp: [...hwarp] } : {}),
			...(hscale.some((v, i) => i < hscale.length - 1 && v !== 1) ? { hscale: [...hscale] } : {}),
			...(!isUniform(knots) ? { knots: [...knots] } : {}),
			visibility_km: visCutoffM === null ? null : +(visCutoffM / 1000).toFixed(1),
			...(Math.abs(maxVisKm - DEFAULT_MAX_VIS_KM) > 1e-9 ? { max_visibility_km: +maxVisKm.toFixed(1) } : {})
		};
	}

	/** the fit's geometry over the contain-fitted base box */
	const baseProjector = () => createOverlayProjector(liveFit(), baseW, baseH);

	function pxPerDegBase(): number {
		return baseProjector().pxPerDeg;
	}

	function resetView() {
		if (viewer?.viewport) viewer.viewport.goHome(true);
		else {
			z = 1;
			tx = 0;
			ty = 0;
		}
	}

	/** double-click: on a handle → remove that seam; elsewhere on the pano →
	 * put a seam there (the panel it splits keeps its numbers on both
	 * sides). Zoom reset moved to the "reset" button. */
	function onStageDblClick(p: { x: number; y: number }) {
		if (!photo) return;
		const hi = hitHandle(p);
		if (hi !== null) {
			removeKnot(hi);
			return;
		}
		const xb = (p.x - tx) / z; // base-space x
		if (xb < 0 || xb > baseW) return;
		insertKnot(xb / baseW);
	}

	/** contain-fit the image into the stage box → base dimensions */
	function fit() {
		if (!stageEl || !naturalW || !naturalH) return;
		const a = naturalW / naturalH;
		baseW = Math.min(stageEl.clientWidth, stageEl.clientHeight * a);
		baseH = baseW / a;
		// zoom cap relative to the image's NATIVE pixels: allow up to ~8×
		// beyond 1:1 (over-zoom is genuinely useful when nudging the curve by
		// 0.01°), with ×16 over the fit as the floor for small images
		if (viewer?.viewport) viewer.viewport.maxZoomPixelRatio = Math.max(8, (16 * baseW) / naturalW);
		syncView();
	}

	/** mirror OSD's viewport into the (z, tx, ty) view transform the overlay
	 * draws with — viewport x ≡ image width, so the screen span of [0, 1] is
	 * the displayed image width. Runs per animated frame (viewport-change). */
	function syncView() {
		if (!viewer?.viewport || !OSD || !(baseW > 0)) return;
		const vp = viewer.viewport;
		const p0 = vp.viewportToViewerElementCoordinates(new OSD.Point(0, 0));
		const p1 = vp.viewportToViewerElementCoordinates(new OSD.Point(1, 0));
		const w = p1.x - p0.x;
		if (!(w > 0)) return;
		z = w / baseW;
		tx = p0.x;
		ty = p0.y;
	}

	// --- stage interactions: OSD owns pan / wheel-zoom / pinch (edge-clamped,
	// no zoom-out past the fit); a press on a handle or a label pill takes the
	// gesture over via preventDefaultAction on the drag events ---
	let press: { kind: 'handle'; idx: number } | { kind: 'pill' } | null = null;

	/** base-space position of warp handle i on the (warped) horizon line —
	 * drawn where the knot's ideal azimuth now sits, so a sideways drag moves
	 * the handle with the content it re-aligned */
	function handleBase(i: number, proj = baseProjector()): { x: number; y: number } {
		const xb = (knots[i] ?? i / (warp.length - 1)) * baseW; // the seam itself
		return { x: xb, y: proj.horizonY(xb) };
	}

	function hitHandle(p: { x: number; y: number }): number | null {
		const proj = baseProjector();
		for (let i = 0; i < warp.length; i++) {
			const h = handleBase(i, proj);
			if (Math.hypot(h.x * z + tx - p.x, h.y * z + ty - p.y) <= HANDLE_HIT) return i;
		}
		return null;
	}

	// OSD canvas-* event shapes (position/delta are px relative to the viewer
	// element, which fills the stage — same frame as the overlay canvas)
	type OsdPt = { x: number; y: number };
	type OsdPress = { position: OsdPt };
	type OsdDrag = {
		delta: OsdPt;
		originalEvent: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean; altKey?: boolean };
		preventDefaultAction: boolean;
	};

	/** a quick click (no drag) anywhere on the pano that is not a label or a
	 * handle: what direction is that under the current fit, and what is there */
	function onCanvasClick(e: { position: OsdPt; quick: boolean }) {
		if (!e.quick || !photo || !render?.meta || !depth || !(baseW > 0)) return;
		const p = e.position;
		if (hitSkyLabel(placedPills, p.x, p.y) || hitHandle(p) !== null) return;
		const xb = (p.x - tx) / z;
		const yb = (p.y - ty) / z;
		if (xb < 0 || xb > baseW || yb < 0 || yb > baseH) return;
		const meta = render.meta;
		const ray = createOverlayProjector(liveFit(), baseW, baseH).unproject(xb, yb);
		const step = meta.az_step_deg ?? (meta.width > 1 ? (meta.az_end - meta.az_start) / (meta.width - 1) : 0);
		if (!(step > 0)) return;
		const col = Math.round(((((ray.azimuth_deg - meta.az_start) % 360) + 360) % 360) / step);
		const span = meta.elev_max_deg - meta.elev_min_deg;
		const row = Math.round(((meta.elev_max_deg - ray.elev_deg) / span) * (meta.height - 1));
		const got = pickFromDepthOrHorizon(meta, depth, col, Math.min(meta.height - 1, Math.max(0, row)));
		dlog(`pick az=${ray.azimuth_deg.toFixed(2)} el=${ray.elev_deg.toFixed(2)} col=${col} row=${row} → ${got ? `${got.lat.toFixed(5)},${got.lon.toFixed(5)} ${(got.distance_m / 1000).toFixed(2)} km` : 'nothing'}`);
		pick = got ? { ...got, elev_deg: ray.elev_deg } : null;
		pickPt = { x: xb, y: yb };
		if (!got) status = `az ${ray.azimuth_deg.toFixed(2)}° · el ${ray.elev_deg.toFixed(2)}° — outside the render (${meta.az_start.toFixed(0)}–${meta.az_end.toFixed(0)}°) or sky with no terrain below`;
		draw();
	}

	function onCanvasPress(e: OsdPress) {
		const p = e.position;
		// a tap on a label pill reveals what the label is claiming
		const pill = hitSkyLabel(placedPills, p.x, p.y);
		if (pill) {
			labelInfo = pill.mark;
			press = { kind: 'pill' };
			return;
		}
		const hi = hitHandle(p);
		if (hi !== null) selectedSeg = panelOf(hi);
		press = hi !== null ? { kind: 'handle', idx: hi } : null;
	}

	function onCanvasDrag(e: OsdDrag) {
		if (!press) return; // plain drag → OSD pans
		e.preventDefaultAction = true;
		if (press.kind !== 'handle') return;
		const ppd = pxPerDegBase();
		if (ppd <= 0) return;
		const mods = e.originalEvent ?? {};
		const dx = e.delta.x;
		const dy = e.delta.y;
		const idx = press.idx;
		const seg = panelOf(idx);
		const sc = hscale[seg] || 1;
		const dDeg = dy / z / (ppd * sc);
		warp = warp.map((v, i) => (i === idx ? v - dDeg : v));
		if (mods.ctrlKey || mods.metaKey) {
			// Ctrl: SCALE the panel about its centre — pull its edge at
			// the handle in (drag toward the centre) or out; the content
			// at the handle follows the pointer
			const half = ((knots[seg + 1] - knots[seg]) / 2) * baseW;
			if (half > 1) {
				const dxb = dx / z;
				const towardCentre = idx <= seg ? dxb : -dxb; // left edge: right = in
				const f = Math.max(0.5, Math.min(2, 1 - towardCentre / half));
				hscale = hscale.map((v, i) => (i === seg ? +(v * f).toFixed(5) : v));
			}
		} else if (!mods.shiftKey) {
			// sideways: content dragged right ⇒ the pano shows a LOWER
			// azimuth here than the model thought ⇒ negative offset — for
			// this handle's panel and every panel to its right (a stitched
			// pano's error accumulates seam by seam); Alt = this panel
			// only; Shift = vertical only.
			const dxDeg = dx / z / ppd;
			hwarp = hwarp.map((v, i) =>
				(mods.altKey ? i === seg : i >= seg && i < hwarp.length - 1) ? v - dxDeg : v
			);
		}
	}

	/** release / drag-end / a second finger (pinch) all end a handle drag */
	function onCanvasRelease() {
		press = null;
	}

	function draw() {
		if (!overlay || !stageEl || !render?.meta || !depth || !photo) return;
		const sw = stageEl.clientWidth;
		const sh = stageEl.clientHeight;
		const W = baseW;
		const H = baseH;
		if (!sw || !sh || !W || !H) return;
		const dpr = globalThis.devicePixelRatio ?? 1;
		overlay.width = Math.round(sw * dpr);
		overlay.height = Math.round(sh * dpr);
		overlay.style.width = `${sw}px`;
		overlay.style.height = `${sh}px`;
		const ctx = overlay.getContext('2d')!;
		ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		ctx.clearRect(0, 0, sw, sh);

		// the fit's geometry, shared with the main app's zoom view: (azimuth
		// delta, elevation)° → a point in base space. All three projections
		// share px/deg = W/fov at the centre of the horizon, so switching
		// projections keeps the rough fit.
		const centre = (photo.pie?.bearing ?? 0) + bearingOffset;
		const projector = createOverlayProjector(liveFit(), W, H);
		const hyBase = projector.horizonY;
		const project = projector.project;
		const toX = (x: number) => x * z + tx;
		const toY = (y: number) => y * z + ty;

		// reference horizon polyline (straight between handles: warp is
		// piecewise-linear and the roll shear is linear)
		ctx.setLineDash([6, 6]);
		ctx.strokeStyle = 'rgba(255,255,255,0.35)';
		ctx.lineWidth = 1;
		ctx.beginPath();
		for (let i = 0; i < warp.length; i++) {
			const xb = (knots[i] ?? i / (warp.length - 1)) * W;
			if (i) ctx.lineTo(toX(xb), toY(hyBase(xb)));
			else ctx.moveTo(toX(xb), toY(hyBase(xb)));
		}
		ctx.stroke();
		ctx.setLineDash([]);

		if (showAnns && annRows.length) {
			ctx.font = '10px system-ui, sans-serif';
			ctx.textAlign = 'center';
			for (const r of annRows) {
				const xb = r.rect_x! * W;
				const y = hyBase(xb);
				const sx = toX(xb), sy = toY(y);
				// pano side: where the annotator drew the rect
				ctx.strokeStyle = 'rgba(80,220,255,0.95)';
				ctx.lineWidth = 1.5;
				ctx.beginPath();
				ctx.moveTo(sx, sy - 14);
				ctx.lineTo(sx, sy + 4);
				ctx.stroke();
				// names only once zoomed in — at fit zoom 80 labels on a thin
				// strip are noise; the ticks alone still show the alignment
				if (z >= 2.5) {
					const label = (r.body || '?').split('|')[0].trim().slice(0, 22) || '?';
					ctx.fillStyle = 'rgba(0,0,0,0.6)';
					const tw = ctx.measureText(label).width;
					ctx.fillRect(sx - tw / 2 - 2, sy + 5, tw + 4, 12);
					ctx.fillStyle = 'rgba(80,220,255,0.95)';
					ctx.fillText(label, sx, sy + 15);
				}
				// terrain side: where its anchor lands under the current fit
				if (r.azimuth != null) {
					const p = projector.projectAzimuth(r.azimuth, 0);
					if (p) {
						const ax = toX(p.x), ay = toY(p.y);
						ctx.strokeStyle = 'rgba(255,110,220,0.95)';
						ctx.beginPath();
						ctx.moveTo(ax, ay - 14);
						ctx.lineTo(ax, ay + 4);
						ctx.stroke();
						// the connector is a "nudge this way" hint — only when the two
						// ticks are reasonably close; an anchor that wraps to the far
						// end of a 360° strip would otherwise draw a line across it
						if (Math.abs(p.x - xb) < W * 0.25) {
							ctx.strokeStyle = 'rgba(255,110,220,0.55)';
							ctx.setLineDash([3, 3]);
							ctx.beginPath();
							ctx.moveTo(sx, sy - 10);
							ctx.lineTo(ax, ay - 10);
							ctx.stroke();
							ctx.setLineDash([]);
						}
					}
				}
			}
			ctx.textAlign = 'start';
		}
		if (pickPt) {
			const px = toX(pickPt.x), py = toY(pickPt.y);
			ctx.strokeStyle = 'rgba(255,255,255,0.9)';
			ctx.lineWidth = 1.5;
			ctx.beginPath();
			ctx.moveTo(px - 10, py); ctx.lineTo(px + 10, py);
			ctx.moveTo(px, py - 10); ctx.lineTo(px, py + 10);
			ctx.stroke();
			ctx.beginPath();
			ctx.arc(px, py, 5, 0, Math.PI * 2);
			ctx.stroke();
		}

		const meta = render.meta;
		if (showCurve) {
			const sky = skylineFor(meta, depth, visCutoffM);
			// with fog active, ghost the full-distance skyline behind the cut
			// one so what the fog hides stays visible for reference
			const passes: [(number | null)[], number, string][] =
				visCutoffM !== null
					? [
							[skylineFor(meta, depth, null), 1, 'rgba(255,220,50,0.28)'],
							[sky, 4, 'rgba(0,0,0,0.55)'],
							[sky, 1.8, 'rgba(255,220,50,0.95)']
						]
					: [
							[sky, 4, 'rgba(0,0,0,0.55)'],
							[sky, 1.8, 'rgba(255,220,50,0.95)']
						];
			// draw as segments, breaking where columns leave the photo's fov or
			// have no terrain
			for (const [curve, width, color] of passes) {
				ctx.lineWidth = width;
				ctx.strokeStyle = color;
				ctx.beginPath();
				let pen = false;
				let prevX = 0;
				for (let c = 0; c < meta.width; c++) {
					const elev = curve[c];
					if (elev === null) {
						pen = false;
						continue;
					}
					const delta = wrapDelta(azimuthForColumn(meta, c) - centre);
					const pt = project(delta, elev);
					if (!pt) {
						pen = false;
						continue;
					}
					// a 360° strip wraps: the column at +180° sits at the right edge
					// and the next one, at −180°, at the left — never join those
					if (pen && Math.abs(pt.x - prevX) > W / 2) pen = false;
					if (pen) ctx.lineTo(toX(pt.x), toY(pt.y));
					else ctx.moveTo(toX(pt.x), toY(pt.y));
					pen = true;
					prevX = pt.x;
				}
				ctx.stroke();
			}
		}

		// peak labels: same transform as the curve (bearing/fov horizontal,
		// warped horizon + pxPerDeg vertical), pills laid out in screen space
		// above their summits — marks come prominence-first, so the layouter's
		// per-neighborhood thinning keeps the best name per column
		if (showLabels && marks.length) {
			ctx.font = '11px system-ui, sans-serif';
			const inputs: {
				label: string; cx: number; cy: number; pillW: number;
				kind?: string; cls?: PeakMark['class']; mark: PeakMark;
			}[] = [];
			for (const m of marks) {
				if (!showPlaces && m.kind && PLACE_KINDS.has(m.kind)) continue;
				if (visCutoffM !== null && m.distance_m > visCutoffM) continue;
				const delta = wrapDelta(m.azimuth_deg - centre);
				const elev =
					meta.elev_max_deg - m.v * (meta.elev_max_deg - meta.elev_min_deg);
				const pt = project(delta, elev);
				if (!pt) continue;
				const xb = pt.x;
				const yb = pt.y;
				// what the label CLAIMS decides its text: summit → name + OSM
				// elevation, mass → name, direction → name, dim
				const label = labelText(m, { km: true });
				inputs.push({
					label,
					cx: toX(xb),
					cy: toY(yb),
					pillW: Math.ceil(ctx.measureText(label).width) + 12,
					kind: m.kind,
					cls: m.class,
					mark: m
				});
			}
			ctx.textBaseline = 'middle';
			placedPills = layoutSkyLabels(inputs, sw, sh, { pillH: 18, leader: 14 });
			paintSkyPills(ctx, placedPills);
		} else {
			placedPills = [];
		}

		// warp handles (constant screen size)
		for (let i = 0; i < warp.length; i++) {
			const h = handleBase(i);
			const hx = toX(h.x);
			const hy = toY(h.y);
			ctx.beginPath();
			ctx.arc(hx, hy, HANDLE_R, 0, Math.PI * 2);
			ctx.fillStyle = 'rgba(0,0,0,0.55)';
			ctx.fill();
			ctx.lineWidth = 1.5;
			ctx.strokeStyle = 'rgba(255,255,255,0.9)';
			ctx.stroke();
			ctx.beginPath();
			ctx.arc(hx, hy, 1.6, 0, Math.PI * 2);
			ctx.fillStyle = 'rgba(255,220,50,0.95)';
			ctx.fill();
			// the panel to the right: its numbers, when it has any; the
			// selected panel's handle is ringed
			const seg = panelOf(i);
			if (i < warp.length - 1 && (hwarp[seg] !== 0 || hscale[seg] !== 1)) {
				ctx.font = '10px ui-monospace, monospace';
				ctx.textAlign = 'left';
				ctx.fillStyle = 'rgba(255,255,255,0.85)';
				const parts = [];
				if (hwarp[seg] !== 0) parts.push(`${hwarp[seg] > 0 ? '+' : ''}${hwarp[seg].toFixed(2)}°`);
				if (hscale[seg] !== 1) parts.push(`×${hscale[seg].toFixed(3)}`);
				ctx.fillText(parts.join(' '), hx + HANDLE_R + 3, hy + HANDLE_R + 10);
			}
			if (selectedSeg !== null && i === selectedSeg) {
				ctx.beginPath();
				ctx.arc(hx, hy, HANDLE_R + 3, 0, Math.PI * 2);
				ctx.strokeStyle = 'rgba(255,220,50,0.9)';
				ctx.lineWidth = 1;
				ctx.stroke();
			}
		}
	}

	// redraw on any alignment change
	$effect(() => {
		void bearingOffset;
		void fovDeg;
		void proj;
		void horizonPct;
		void vScale;
		void rollDeg;
		void warp;
		void hwarp;
		void hscale;
		void knots;
		void selectedSeg;
		void showCurve;
		void showLabels;
		void showAnns;
		void annRows;
		void showPlaces;
		void marks;
		void visLog;
		void z;
		void tx;
		void ty;
		void baseW;
		void baseH;
		draw();
	});

	// auto-save the working state as a per-photo draft (debounced). Restore
	// order on load is saved fit → draft, so a reload resumes exactly here;
	// "save fit" promotes to a fact and clears the draft.
	$effect(() => {
		void proj;
		void bearingOffset;
		void fovDeg;
		void horizonPct;
		void vScale;
		void rollDeg;
		void warp;
		void hwarp;
		void hscale;
		void knots;
		void selectedSeg;
		void visLog;
		if (!photo || suppressDraft) {
			if (photo && suppressDraft)
				dlog('sync: change while suppressed (load not finished?)');
			return;
		}
		const payload = fitPayload();
		const bare = bareOf(payload);
		scheduleHistory();
		// identical alignment to one just received from another window → the
		// writer already persisted it; rewriting would ping-pong events
		if (bare === lastSync) return;
		lastSync = bare;
		lastTs = payload.saved_at;
		const raw = JSON.stringify(payload);
		try {
			localStorage.setItem(liveKey(photo.id), raw);
			dlog('sync: wrote live key + broadcast');
		} catch (e) {
			dlog(`sync: localStorage write FAILED: ${e}`);
		}
		bc?.postMessage({ key: liveKey(photo.id), raw });
		draftState = `synced ${new Date().toLocaleTimeString()}`;
		clearTimeout(draftTimer);
		draftTimer = setTimeout(() => {
			api.put('/terrain/overlay-draft', payload)
				.then(() => (draftState = 'draft ✓'))
				.catch(() => (draftState = 'draft save failed'));
		}, 800);
	});

	// action on the stage div: it lives behind {#if imgUrl}, so it doesn't
	// exist yet at onMount — wire listeners when the element itself appears.
	function stageSetup(node: HTMLElement) {
		const ro = new ResizeObserver(() => {
			fit();
			draw();
		});
		ro.observe(node);
		return {
			destroy: () => {
				ro.disconnect();
			}
		};
	}

	/** the pano layer: an OpenSeadragon viewer on the host div, opened on the
	 * DZI pyramid (single full image when there is none). Also an action —
	 * the host appears/disappears with {#if imgUrl}, and load() nulls the
	 * photo first, so a photo switch is always destroy → fresh viewer. */
	function osdSetup(node: HTMLElement) {
		let destroyed = false;
		let fellBack = false;
		const url = imgUrl!;
		const pyr = pyramid;
		const source = pyr ? buildTileSource(pyr, url) : { type: 'image', url };
		dlog(pyr ? `osd: dzi ${pyr.width}x${pyr.height} tile ${pyr.tile_size}` : `osd: single image ${url}`);
		import('openseadragon').then((mod) => {
			if (destroyed) return;
			OSD = mod.default;
			viewer = new OSD.Viewer({
				...OSD_VIEWER_DEFAULTS,
				element: node,
				tileSources: source,
				// bench overrides: fine wheel steps (this is a 0.01° tool);
				// double-click is seam add/remove, not zoom; no touch flick;
				// pans may run past the image edges (labels sit above the
				// skyline, i.e. above the top edge of a thin pano — keep ≥30 %
				// of the image in view); no zoom-out past the fit (the old
				// clampPan); no keyboard nav — r rotates and f flips, which
				// would break the affine view mirror (ctrl+z still bubbles to
				// the window handler)
				zoomPerScroll: 1.2,
				gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: false, dblClickDragToZoom: false },
				gestureSettingsTouch: {
					clickToZoom: false,
					dblClickToZoom: false,
					dblClickDragToZoom: false,
					flickEnabled: false
				},
				constrainDuringPan: true,
				visibilityRatio: 0.3,
				minZoomImageRatio: 1,
				maxZoomPixelRatio: 8,
				keyboardNavEnabled: false,
				imageLoaderLimit: 4
			});
			viewer.addHandler('open', () => {
				const size = viewer.world.getItemAt(0)?.getContentSize?.();
				if (size) {
					naturalW = size.x;
					naturalH = size.y;
				}
				dlog(`osd open ${naturalW}x${naturalH}`);
				fit();
				draw();
			});
			viewer.addHandler('open-failed', (e: { message?: string }) => {
				dlog(`osd open FAILED: ${e?.message ?? '?'}`);
				if (pyr && !fellBack) {
					fellBack = true;
					dlog('osd: falling back to the single image');
					viewer.open({ type: 'image', url });
				}
			});
			viewer.addHandler('viewport-change', syncView);
			viewer.addHandler('animation-finish', syncView);
			viewer.addHandler('canvas-press', onCanvasPress);
			viewer.addHandler('canvas-drag', onCanvasDrag);
			viewer.addHandler('canvas-drag-end', onCanvasRelease);
			viewer.addHandler('canvas-release', onCanvasRelease);
			viewer.addHandler('canvas-pinch', onCanvasRelease);
			viewer.addHandler('canvas-double-click', (e: OsdPress) => onStageDblClick(e.position));
			viewer.addHandler('canvas-click', onCanvasClick);
		});
		return {
			destroy: () => {
				destroyed = true;
				viewer?.destroy();
				viewer = null;
			}
		};
	}

	onMount(() => {
		dlog(`page open ${navigator.userAgent}`);
		const onErr = (e: ErrorEvent) =>
			dlog(`JS ERROR: ${e.message} @ ${e.filename?.split('/').pop()}:${e.lineno}`);
		const onRej = (e: PromiseRejectionEvent) => dlog(`UNHANDLED REJECTION: ${e.reason}`);
		const onHide = () => flushDlog();
		window.addEventListener('error', onErr);
		window.addEventListener('unhandledrejection', onRej);
		window.addEventListener('pagehide', onHide);
		const pid = page.url.searchParams.get('photo');
		if (pid) {
			photoId = pid;
			load();
		}
		// receive live state from sibling windows: BroadcastChannel is the
		// primary channel (explicit delivery, no storage-event quirks); the
		// storage event stays as fallback. Neither fires in the sender.
		bc = 'BroadcastChannel' in globalThis ? new BroadcastChannel('terrain-overlay-fit') : null;
		if (bc)
			bc.onmessage = (e: MessageEvent) => {
				if (!photo || e.data?.key !== liveKey(photo.id)) return;
				dlog('sync: received via BroadcastChannel');
				applyRemote(e.data.raw as string);
			};
		const onStorage = (e: StorageEvent) => {
			if (!photo || !e.newValue || e.key !== liveKey(photo.id)) return;
			dlog('sync: received via storage event');
			applyRemote(e.newValue);
		};
		window.addEventListener('storage', onStorage);
		// cross-browser/device live sync: the backend draft is the only
		// channel that crosses origins and browsers — poll it lightly and
		// apply anything newer than what this window has seen
		const poll = setInterval(async () => {
			if (!photo || suppressDraft || document.hidden) return;
			try {
				const dr = await api.get<{ draft: OverlayFit | null }>(
					`/terrain/overlay-draft?photo_id=${photo.id}`
				);
				const f = dr.draft;
				if (f?.saved_at && f.saved_at > lastTs + 1) {
					dlog('sync: received via draft poll');
					applyRemote(JSON.stringify(f));
				}
			} catch {
				/* api hiccup — next tick */
			}
		}, 2500);
		return () => {
			bc?.close();
			clearInterval(poll);
			window.removeEventListener('storage', onStorage);
			window.removeEventListener('error', onErr);
			window.removeEventListener('unhandledrejection', onRej);
			window.removeEventListener('pagehide', onHide);
		};
	});
	// keyboard: undo/redo like any editor — but not while typing in a field
	function onKey(e: KeyboardEvent) {
		const t = e.target as HTMLElement | null;
		if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
		if (!(e.ctrlKey || e.metaKey)) return;
		if (e.key === 'z' || e.key === 'Z') {
			e.preventDefault();
			if (e.shiftKey) redo();
			else undo();
		} else if (e.key === 'y' || e.key === 'Y') {
			e.preventDefault();
			redo();
		}
	}
</script>

<svelte:window onkeydown={onKey} />

<h1 style="font-size:16px">Terrain ⧉ pano overlay <small style="opacity:.6">(experiment)</small></h1>

<section class="pick">
	<input placeholder="photo id" bind:value={photoId} style="width:24rem" />
	<button onclick={load}>load</button>
	{#if photo}
		<span class="info">
			{photo.title ?? photo.id.slice(0, 8)}
			· pie {photo.pie ? `${photo.pie.bearing.toFixed(1)}° ± ${photo.pie.half.toFixed(1)}°
				${photo.pie.calibrated ? '(calibrated)' : '(assumed)'}` : '— none'}
			{#if render}· render {render.meta?.dsm_stack ?? '?'} · {new Date(render.enqueued_at).toLocaleString()}{/if}
		</span>
	{/if}
	{#if status}<span class="info">{status}</span>{/if}
	{#if labelInfo}
		<span class="info" data-testid="overlay-label-evidence" title="tap a label to see what it claims">
			<b>{labelInfo.name}</b> · {labelInfo.class} — {labelEvidence(labelInfo)}
			{#if labelInfo.lat != null && labelInfo.lon != null}
				· <span class="mono">{labelInfo.lat.toFixed(5)}, {labelInfo.lon.toFixed(5)}</span>
				· az {labelInfo.azimuth_deg.toFixed(1)}° · {(labelInfo.distance_m / 1000).toFixed(1)} km
				· <a href="https://www.openstreetmap.org/?mlat={labelInfo.lat}&mlon={labelInfo.lon}#map=14/{labelInfo.lat}/{labelInfo.lon}" target="_blank" rel="noreferrer">osm ↗</a>
				· <a href="https://hillview.cz/?lat={labelInfo.lat}&lon={labelInfo.lon}&zoom=14" target="_blank" rel="noreferrer">hillview ↗</a>
			{/if}
			<button class="linkish" onclick={() => (labelInfo = null)} aria-label="dismiss">×</button>
		</span>
	{/if}
	{#if pick}
		<span class="info" data-testid="overlay-pick" title="what the clicked pixel looks at under the current fit, resolved through the depth buffer (a sky click snaps to the horizon in that direction)">
			📍 az {pick.azimuth_deg.toFixed(2)}° · el {pick.elev_deg.toFixed(2)}° ·
			<span class="mono">{pick.lat.toFixed(5)}, {pick.lon.toFixed(5)}</span> · {(pick.distance_m / 1000).toFixed(2)} km
			· <a href="https://www.openstreetmap.org/?mlat={pick.lat}&mlon={pick.lon}#map=15/{pick.lat}/{pick.lon}" target="_blank" rel="noreferrer">osm ↗</a>
			· <a href="https://hillview.cz/?lat={pick.lat}&lon={pick.lon}&zoom=15" target="_blank" rel="noreferrer">hillview ↗</a>
			<button class="linkish" onclick={() => { pick = null; pickPt = null; draw(); }} aria-label="dismiss">×</button>
		</span>
	{/if}
	{#if err}<span class="err">{err}</span>{/if}
</section>

{#if imgUrl}
	<section class="controls">
		<label><input type="checkbox" bind:checked={showCurve} /> skyline</label>
		<label><input type="checkbox" bind:checked={showLabels} /> labels</label>
		<label title="the photo's annotations: cyan tick = where the rect was drawn, magenta tick = where its anchor lands under this fit — they coincide when the fit is right"><input type="checkbox" bind:checked={showAnns} data-testid="overlay-show-anns" /> annotations ({annRows.length})<span class="info" style="margin-left:4px">names when zoomed ≥ 2.5×</span></label>
		{#if showLabels}
			<label title="include settlement names (city/town/village/district)">
				<input type="checkbox" bind:checked={showPlaces} /> places
			</label>
		{/if}
		<label>
			proj
			<select bind:value={proj}>
				<option value="equirect">equirect (f2)</option>
				<option value="cylindrical">cylindrical (f1)</option>
				<option value="rectilinear">rectilinear (f0)</option>
			</select>
		</label>
		<label>
			bearing
			<input class="num" type="number" step="0.01" bind:value={bearingOffset} />°
			<input type="range" min="-20" max="20" step="0.01" bind:value={bearingOffset} />
		</label>
		<label>
			fov
			<input class="num" type="number" min="5" max="400" step="0.1" bind:value={fovDeg} title="horizontal field of view; a stitched pano may exceed 360° by its closing overlap" />°
			<input type="range" min="20" max="400" step="0.1" bind:value={fovDeg} />
		</label>
		<label>
			horizon
			<input class="num" type="number" min="0" max="100" step="0.1" bind:value={horizonPct} />%
			<input type="range" min="0" max="100" step="0.1" bind:value={horizonPct} />
		</label>
		<label>
			v-scale ×
			<input class="num" type="number" min="0.1" max="5" step="0.01" bind:value={vScale} />
			<input type="range" min="0.4" max="2.5" step="0.01" bind:value={vScale} />
		</label>
		<label>
			roll
			<input class="num" type="number" min="-10" max="10" step="0.05" bind:value={rollDeg} />°
			<input type="range" min="-8" max="8" step="0.05" bind:value={rollDeg} />
		</label>
		<label>
			<span title="the DEFAULT visibility visitors open with — cut the skyline and labels where the photo's haze cuts them; the zoom view can then slide fog between here and 'max'">fog</span>
			<input
				class="num"
				type="number"
				min="1"
				max={Math.ceil(maxDistM / 1000)}
				step="1"
				value={visKm}
				oninput={(e) => setFogKm(e.currentTarget.valueAsNumber)}
			/>km
			<input type="range" min="3" max={visLogMax} step="0.01" bind:value={visLog} />
		</label>
		<label title="how far the graduated document reaches: labels are baked out to this, CAPPED BY THE RENDER'S OWN RANGE — asking for more than the render covers cannot invent terrain, so re-render further if you need it. The fog slider on the left is the DEFAULT visitors open with — tune it to the photo's haze.">
			max
			<input class="num" type="number" min="5" max="400" step="5" bind:value={maxVisKm} data-testid="overlay-max-vis" />km
			{#if maxVisKm > maxDistM / 1000 + 0.05}
				<span class="info warn" data-testid="overlay-max-vis-capped"
					>→ {Math.round(maxDistM / 1000)} km (render's range)</span
				>
			{/if}
		</label>
		<span class="group" title="handles sit on seams. Drag up/down: lift the horizon there. Sideways: SHIFT the panel to the right of the handle and every panel beyond it (a stitched pano's error accumulates seam by seam) — Alt: this panel only, Shift: vertical only. Ctrl-drag: SCALE that panel about its centre (both axes — a frame stitched at the wrong focal length). Double-click the pano to add a seam where the stitch has one, double-click a handle to remove it; click a handle to edit its panel's numbers.">
			segments
			<input
				class="num"
				type="number"
				min="1"
				max={MAX_SEGMENTS}
				step="1"
				value={warp.length - 1}
				data-testid="overlay-segments"
				onchange={(e) => setSegments(e.currentTarget.valueAsNumber)}
			/>
			<button onclick={() => setSegments(warp.length)} disabled={warp.length >= MAX_SEGMENTS + 1}>+</button>
			<button onclick={() => setSegments(warp.length - 2)} disabled={warp.length <= 2}>−</button>
			<button onclick={() => { warp = warp.map(() => 0); hwarp = hwarp.map(() => 0); hscale = hscale.map(() => 1); rollDeg = 0; }} title="zero all handle offsets (vertical and sideways), reset panel scales and roll — seams stay">level</button>
			{#if !isUniform(knots)}<span class="info" title="seams are where you put them (double-click the pano to add, a handle to remove); the number field re-spaces them equally">seams placed</span>{/if}
			{#if selectedSeg !== null && selectedSeg < warp.length - 1}
				<span class="panel-editor" title="the panel to the right of the clicked handle: sideways shift in degrees and scale about its centre (both axes)">
					panel {selectedSeg + 1}
					shift <input class="num" type="number" step="0.01" value={hwarp[selectedSeg]} data-testid="overlay-panel-shift"
						onchange={(e) => { const v = e.currentTarget.valueAsNumber; if (Number.isFinite(v)) hwarp = hwarp.map((h, i) => (i === selectedSeg ? v : h)); }} />°
					scale <input class="num" type="number" step="0.001" min="0.5" max="2" value={hscale[selectedSeg]} data-testid="overlay-panel-scale"
						onchange={(e) => { const v = e.currentTarget.valueAsNumber; if (Number.isFinite(v) && v > 0) hscale = hscale.map((h, i) => (i === selectedSeg ? v : h)); }} />
				</span>
			{/if}
		</span>
		<span class="group">
			zoom <span class="val">×{z.toFixed(2)}</span>
			<button onclick={resetView} disabled={z <= 1.001}>reset</button>
		</span>
		<span class="group">
			<button
				onclick={resetToDefaults}
				disabled={!photo}
				title="reset all alignment to the calibration-derived defaults and discard the draft"
			>defaults</button>
			<button onclick={undo} disabled={histIdx <= 0} title="undo (Ctrl+Z)">↶</button>
			<button onclick={redo} disabled={histIdx >= history.length - 1} title="redo (Ctrl+Shift+Z)">↷</button>
			<button
				onclick={revertToSaved}
				disabled={!photo || !savedFit || !dirty}
				data-testid="overlay-revert"
				title="back to the last saved fit — drops the draft and this tab's live state (undoable)"
			>revert</button>
			<button onclick={saveFit} disabled={saving || !photo || (!dirty && !!fitFact)} data-testid="overlay-save">save fit</button>
			<span class="info state" class:dirty data-testid="overlay-fit-state">
				{#if !photo}—{:else if !savedFit}never saved{:else if dirty}unsaved changes{:else}saved ✓{/if}
			</span>
			{#if saveMsg}<span class="info">{saveMsg}</span>{/if}
			<span class="info draft" data-testid="overlay-draft-state">{draftState}</span>
		</span>
		<span class="group">
			<label
				title={fitFact
					? 'approve this fit so the graduation export carries the overlay into Hillview'
					: 'save the fit first — graduation publishes a saved fit'}
			>
				<input
					type="checkbox"
					data-testid="overlay-graduate"
					checked={fitApproved}
					disabled={gradBusy || !fitFact}
					onchange={toggleGraduate}
				/>
				graduate
			</label>
			{#if gradMsg}<span class="info">{gradMsg}</span>{/if}
		</span>
	</section>

	<div class="stage" bind:this={stageEl} use:stageSetup>
		<div class="osd" use:osdSetup data-testid="overlay-osd"></div>
		<canvas bind:this={overlay}></canvas>
	</div>
	<p class="hint">
		<b>proj</b> must match the pano's stitch output projection — read the .pto p-line's f-value
		(f0 rectilinear / f1 cylindrical / f2 equirect); it varies per pano, see
		docs/pano-source-archaeology.md. Wrong projection = unfittable by design.
		<b>wheel / pinch</b> zooms about the cursor (into the full-resolution pyramid), <b>drag</b> pans,
		<b>double-click</b> adds/removes a seam, <b>reset</b> refits.
		The dashed line is the horizon reference — drag its <b>round handles</b> up/down to bend the
		fit locally (offsets interpolate between handles; <b>segments ±</b> adds or removes them —
		with just two, dragging the ends IS a roll). The <b>roll</b> slider tilts globally on top.
		Horizontal comes from the pie (trim with bearing/fov if it's assumed); set <b>horizon</b>
		roughly, then handles + <b>v-scale</b> until near and far skyline match at once. A good fit
		here is a vertical calibration — worth saving once this proves useful.
	</p>
{/if}

<style>
	.pick { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.5rem; }
	.info { font-size: 12px; opacity: 0.7; }
	.info.state { opacity: 0.9; }
	/* "draft ✓" / "synced 12:34:56" flips several times per fit — a fixed box
	   keeps the graduate checkbox from jumping */
	.info.draft { display: inline-block; width: 10em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.panel-editor { display: inline-flex; gap: 4px; align-items: center; font-size: 12px; margin-left: 6px; }
	.panel-editor .num { width: 5.5em; }
	.info.state.dirty { color: #f2d55c; }
	.info.warn { color: #f2d55c; opacity: 0.95; }
	.linkish { background: none; border: 0; color: inherit; cursor: pointer; padding: 0 4px; font: inherit; }
	.err { color: #d33; font-size: 12px; }
	.controls {
		display: flex;
		gap: 1.1rem;
		align-items: center;
		flex-wrap: wrap;
		font-size: 12px;
		margin-bottom: 0.4rem;
	}
	.controls label { display: flex; align-items: center; gap: 0.35rem; white-space: nowrap; }
	/* fixed-width readouts: a value changing width mid-drag would reflow the
	   row and move the slider under the pointer (drag → label → drag loop) */
	.controls .val {
		display: inline-block;
		min-width: 3.4em;
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	/* editable readouts: exact entry + spinner-arrow single steps; fixed
	   width keeps the row from reflowing mid-drag */
	.controls .num {
		width: 4.6em;
		font-size: 12px;
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	/* longer track = finer °/px — the sliders were heavy-handed */
	.controls input[type='range'] { width: 150px; }
	.controls .group { display: flex; align-items: center; gap: 0.35rem; white-space: nowrap; }
	.controls .group button { font-size: 12px; padding: 0 0.45rem; }
	.stage {
		position: relative;
		height: min(72dvh, 48rem);
		background: #0d1117;
		overflow: hidden;
		touch-action: none;
		cursor: grab;
		user-select: none;
	}
	.stage:active { cursor: grabbing; }
	/* the OSD host fills the stage; the overlay canvas sits above it and never
	 * takes pointer events — OSD's canvas-* events drive handle drags */
	.stage .osd { position: absolute; inset: 0; }
	.stage canvas { position: absolute; inset: 0; pointer-events: none; }
	.hint { font-size: 12px; opacity: 0.6; max-width: 60rem; }
</style>

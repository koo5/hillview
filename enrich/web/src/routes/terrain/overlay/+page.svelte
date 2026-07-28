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
	// The vertical fit is a piecewise-linear warp: N handles ride the dashed
	// horizon line, each dragging its neighborhood up/down (offsets stored in
	// DEGREES so they survive zoom/rescale). Two handles = plain roll+offset;
	// more handles absorb per-seam pano stitching wobble. A global roll
	// slider (shear approximation) sits on top for fine trim.
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { apiBase } from '$lib/config';
	import { azimuthForColumn, type TerrainMeta } from '$terrain/depthPanoViewer';
	import {
		layoutSkyLabels,
		PLACE_KINDS,
		projectPeaks,
		type Peak,
		type PeakMark
	} from '$terrain/peakLabels';

	interface PhotoInfo {
		id: string;
		title: string | null;
		sizes: Record<string, { url?: string }> | null;
		width: number | null;
		height: number | null;
		pie: {
			bearing: number;
			half: number;
			calibrated: boolean;
			/** from calibratedProjection/calibratedX0 facts, when accepted */
			projection?: string;
			x0?: number;
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

	/** saved manual alignment (hv:terrainOverlayFit fact via the API) */
	interface OverlayFit {
		projection: string;
		centre_bearing: number;
		fov_deg: number;
		horizon_pct: number;
		v_scale: number;
		roll_deg: number;
		warp: number[];
		/** atmospheric visibility that day, km; null/absent = full */
		visibility_km?: number | null;
		/** client wall-clock of the change (epoch ms) — drafts/live only */
		saved_at?: number;
	}

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
	let showPlaces = $state(true);
	let peaks: Peak[] = [];
	let marks = $state<PeakMark[]>([]);
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

	// view transform: screen = base * z + (tx, ty). Base = the image
	// contain-fitted into the fixed-height stage at zoom 1 (baseW × baseH
	// CSS px, centered by the clamp), so a wide pano gets vertical room to
	// zoom into instead of staying a fit-to-width noodle.
	let z = $state(1);
	let tx = $state(0);
	let ty = $state(0);
	let baseW = $state(0);
	let baseH = $state(0);

	let img: HTMLImageElement;
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

	async function load() {
		err = null;
		photo = null;
		render = null;
		depth = null;
		peaks = [];
		marks = [];
		saveMsg = '';
		draftState = '';
		suppressDraft = true;
		resetView();
		warp = warp.map(() => 0);
		rollDeg = 0;
		horizonPct = 50;
		vScale = 1;
		if (!photoId) return;
		try {
			status = 'loading photo…';
			const pd = await api.get<{ photo: PhotoInfo }>(`/photos/${photoId}`);
			photo = pd.photo;
			pieDefaults();
			// restore order: pie defaults → saved fit → draft (newest working
			// state wins; fog applies later — the render load below resets
			// the slider to full first)
			let savedVisKm: number | null = null;
			const applyFit = (f: OverlayFit) => {
				savedVisKm = applyFitState(f);
			};
			try {
				const sf = await api.get<{ fit: OverlayFit | null }>(
					`/terrain/overlay-fit?photo_id=${photoId}`
				);
				if (sf.fit) {
					applyFit(sf.fit);
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
				saveMsg = `restored ${restored.src}`;
			}
			status = 'loading render…';
			const rs = await api.get<{ renders: RenderRow[] }>(
				`/terrain/renders?photo_id=${photoId}`
			);
			const done = rs.renders.find(
				(r) => r.status === 'done' && r.meta && 'width' in r.meta
			);
			if (!done) {
				status = '';
				err = 'no finished render for this photo — enqueue one on the terrain bench first';
				suppressDraft = false; // controls still usable; keep drafting
				return;
			}
			render = done;
			skyCaches.clear();
			visLog = Math.log10(done.meta?.max_distance_m ?? 200000);
			if (savedVisKm !== null) setFogKm(savedVisKm);
			status = 'loading depth…';
			const buf = await (await fetch(`${apiBase}/terrain/renders/${done.id}/depth`)).arrayBuffer();
			depth = new Uint16Array(buf);
			// the fit is fully workable now — labels are cosmetic. Drafting/
			// sync must NOT wait for the peaks fetch (a cold Overpass pass can
			// take minutes; sitting at "loading peaks" used to silently
			// disable all persistence)
			suppressDraft = false;
			requestAnimationFrame(draw);
			status = 'loading peak labels… (fitting already works)';
			// label candidates; failures/timeouts degrade to an unlabeled overlay
			try {
				const meta = done.meta!;
				const radius = Math.min(200_000, meta.max_distance_m ?? 100_000);
				const pr = (await (
					await fetch(
						`${apiBase}/terrain/peaks?lat=${meta.lat}&lon=${meta.lon}&radius_m=${radius}`,
						{ signal: AbortSignal.timeout(45_000) }
					)
				).json()) as { peaks?: Peak[] };
				peaks = pr.peaks ?? [];
			} catch {
				peaks = [];
			}
			marks = done.meta && depth ? projectPeaks(done.meta, depth, peaks) : [];
			status = '';
		} catch (e) {
			status = '';
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
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
		const step = (meta.elev_max_deg - meta.elev_min_deg) / meta.height;
		const out: (number | null)[] = new Array(meta.width).fill(null);
		const maxQ = cutoffM === null ? 0xffff : Math.floor(cutoffM / meta.depth_scale_m);
		for (let c = 0; c < meta.width; c++) {
			// top-down to the first terrain pixel (rows above are sky = 0)
			let r0 = -1;
			for (let r = 0; r < meta.height; r++) {
				if (d[r * meta.width + c] !== 0) {
					r0 = r;
					break;
				}
			}
			if (r0 < 0) continue;
			// below r0 depth is non-increasing (a lower ray hits terrain at or
			// before a higher one), so the fog crossing binary-searches; near-
			// clip sky (0) at the bottom passes the predicate and is rejected
			// after the search
			let lo = r0;
			if (d[r0 * meta.width + c] > maxQ) {
				let hi = meta.height;
				while (lo < hi) {
					const mid = (lo + hi) >> 1;
					if (d[mid * meta.width + c] <= maxQ) hi = mid;
					else lo = mid + 1;
				}
			}
			if (lo >= meta.height || d[lo * meta.width + c] === 0) continue;
			out[c] = meta.elev_max_deg - (lo + 0.5) * step;
		}
		// scrubbing the fog slider caches one array per stop — cap the map
		if (skyCaches.size >= 8) skyCaches.delete(skyCaches.keys().next().value!);
		skyCaches.set(key, out);
		return out;
	}

	const wrapDelta = (d: number) => ((((d + 180) % 360) + 360) % 360) - 180;

	/** apply a fit/draft/live snapshot to the alignment knobs; returns its
	 * visibility_km (null = full) for the caller to apply once the render's
	 * fog range is known */
	function applyFitState(f: OverlayFit): number | null {
		proj = f.projection as typeof proj;
		fovDeg = f.fov_deg;
		bearingOffset = +wrapDelta(f.centre_bearing - (photo?.pie?.bearing ?? 0)).toFixed(2);
		horizonPct = f.horizon_pct;
		vScale = f.v_scale;
		rollDeg = f.roll_deg;
		if (f.warp?.length >= 2) warp = f.warp.slice();
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
		warp = warp.map(() => 0);
		visLog = visLogMax;
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
			photo_id: photo!.id,
			render_id: render?.id ?? null,
			projection: proj,
			centre_bearing: (photo!.pie?.bearing ?? 0) + bearingOffset,
			fov_deg: fovDeg,
			horizon_pct: horizonPct,
			v_scale: vScale,
			roll_deg: rollDeg,
			warp: [...warp],
			visibility_km: visCutoffM === null ? null : +(visCutoffM / 1000).toFixed(1),
			saved_at: Date.now()
		};
	}

	async function saveFit() {
		if (!photo) return;
		saving = true;
		saveMsg = '';
		try {
			const r = await api.post<{ run_id: string }>('/terrain/overlay-fit', fitPayload());
			saveMsg = `saved ✓ run ${r.run_id.slice(0, 8)}`;
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

	/** warp offset (degrees, + = up) at horizontal fraction 0..1 */
	function warpAt(frac: number): number {
		const n = warp.length;
		const pos = Math.min(1, Math.max(0, frac)) * (n - 1);
		const i0 = Math.floor(pos);
		const i1 = Math.min(n - 1, i0 + 1);
		return warp[i0] + (warp[i1] - warp[i0]) * (pos - i0);
	}

	/** change control-point count, preserving the current warp shape */
	function resampleWarp(old: number[], n: number): number[] {
		n = Math.min(9, Math.max(2, n));
		if (old.length === n) return old.slice();
		const out: number[] = [];
		for (let i = 0; i < n; i++) {
			const pos = (i / (n - 1)) * (old.length - 1);
			const i0 = Math.floor(pos);
			const i1 = Math.min(old.length - 1, i0 + 1);
			out.push(old[i0] + (old[i1] - old[i0]) * (pos - i0));
		}
		return out;
	}

	function pxPerDegBase(): number {
		return (baseW / fovDeg) * vScale;
	}

	function resetView() {
		z = 1;
		tx = 0;
		ty = 0;
		if (stageEl) clampPan();
	}

	/** contain-fit the image into the stage box → base dimensions */
	function fit() {
		if (!stageEl || !img?.naturalWidth || !img.naturalHeight) return;
		const a = img.naturalWidth / img.naturalHeight;
		baseW = Math.min(stageEl.clientWidth, stageEl.clientHeight * a);
		baseH = baseW / a;
		clampPan();
	}

	/** clamp one axis: center when it fits, edge-clamp when it overflows */
	function clampAxis(t: number, extent: number, avail: number): number {
		if (extent <= avail) return (avail - extent) / 2;
		return Math.min(0, Math.max(avail - extent, t));
	}

	function clampPan() {
		tx = clampAxis(tx, baseW * z, stageEl?.clientWidth ?? 0);
		ty = clampAxis(ty, baseH * z, stageEl?.clientHeight ?? 0);
	}

	function zoomAt(px: number, py: number, factor: number) {
		const z2 = Math.min(16, Math.max(1, z * factor));
		const f = z2 / z;
		tx = px - (px - tx) * f;
		ty = py - (py - ty) * f;
		z = z2;
		clampPan();
	}

	// --- stage interactions: pan / wheel-zoom / pinch / handle drag ---
	const pointers = new Map<number, { x: number; y: number }>();
	let drag: { kind: 'pan' } | { kind: 'handle'; idx: number } | null = null;

	function stagePos(e: PointerEvent | WheelEvent) {
		const r = stageEl.getBoundingClientRect();
		return { x: e.clientX - r.left, y: e.clientY - r.top };
	}

	/** base-space position of warp handle i on the (warped) horizon line */
	function handleBase(i: number): { x: number; y: number } {
		const W = baseW;
		const H = baseH;
		const xb = (i / (warp.length - 1)) * W;
		const rollK = Math.tan((rollDeg * Math.PI) / 180);
		const yb = (horizonPct / 100) * H + (xb - W / 2) * rollK - warpAt(xb / W) * pxPerDegBase();
		return { x: xb, y: yb };
	}

	function hitHandle(p: { x: number; y: number }): number | null {
		for (let i = 0; i < warp.length; i++) {
			const h = handleBase(i);
			if (Math.hypot(h.x * z + tx - p.x, h.y * z + ty - p.y) <= HANDLE_HIT) return i;
		}
		return null;
	}

	function onPointerDown(e: PointerEvent) {
		stageEl.setPointerCapture(e.pointerId);
		const p = stagePos(e);
		pointers.set(e.pointerId, p);
		if (pointers.size === 1) {
			const hi = hitHandle(p);
			drag = hi !== null ? { kind: 'handle', idx: hi } : { kind: 'pan' };
		} else {
			drag = null; // second finger cancels handle/pan → pinch
		}
	}

	function onPointerMove(e: PointerEvent) {
		const prev = pointers.get(e.pointerId);
		if (!prev) return;
		const p = stagePos(e);
		if (pointers.size === 2) {
			let other: { x: number; y: number } | null = null;
			for (const [id, q] of pointers) if (id !== e.pointerId) other = q;
			if (other) {
				const d0 = Math.hypot(prev.x - other.x, prev.y - other.y);
				const d1 = Math.hypot(p.x - other.x, p.y - other.y);
				if (d0 > 0) zoomAt((p.x + other.x) / 2, (p.y + other.y) / 2, d1 / d0);
				tx += (p.x - prev.x) / 2;
				ty += (p.y - prev.y) / 2;
				clampPan();
			}
		} else if (drag?.kind === 'handle') {
			const ppd = pxPerDegBase();
			if (ppd > 0) {
				const dDeg = (p.y - prev.y) / z / ppd;
				const idx = drag.idx;
				warp = warp.map((v, i) => (i === idx ? v - dDeg : v));
			}
		} else if (drag?.kind === 'pan') {
			tx += p.x - prev.x;
			ty += p.y - prev.y;
			clampPan();
		}
		pointers.set(e.pointerId, p);
	}

	function onPointerUp(e: PointerEvent) {
		pointers.delete(e.pointerId);
		drag = pointers.size === 1 ? { kind: 'pan' } : null;
	}

	function onWheel(e: WheelEvent) {
		e.preventDefault();
		const p = stagePos(e);
		zoomAt(p.x, p.y, Math.exp(-e.deltaY * 0.0018));
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

		const centre = (photo.pie?.bearing ?? 0) + bearingOffset;
		const horizonY = (horizonPct / 100) * H;
		const pxPerDeg = (W / fovDeg) * vScale; // equirect square-pixel guess × trim
		const rollK = Math.tan((rollDeg * Math.PI) / 180);
		// warped+rolled horizon in base space, then base → screen
		const hyBase = (x: number) => horizonY + (x - W / 2) * rollK - warpAt(x / W) * pxPerDeg;
		// projection: (azimuth delta, elevation)° → base x + px displacement
		// above the horizon. All three share px/deg = W/fov at the centre of
		// the horizon, so switching projections keeps the rough fit.
		const fovRad = (Math.min(fovDeg, 358) * Math.PI) / 180;
		const fCyl = (W / fovRad) * vScale;
		const fRectH = W / 2 / Math.tan(Math.min(fovRad, (178 * Math.PI) / 180) / 2);
		const project = (deltaDeg: number, elevDeg: number): { xb: number; dy: number } | null => {
			const a = (deltaDeg * Math.PI) / 180;
			const e = (elevDeg * Math.PI) / 180;
			switch (proj) {
				case 'equirect':
					if (Math.abs(deltaDeg) > fovDeg / 2 + 2) return null;
					return { xb: W * (0.5 + deltaDeg / fovDeg), dy: elevDeg * pxPerDeg };
				case 'cylindrical':
					if (Math.abs(deltaDeg) > fovDeg / 2 + 2) return null;
					return { xb: W * (0.5 + deltaDeg / fovDeg), dy: fCyl * Math.tan(e) };
				case 'rectilinear': {
					if (Math.abs(deltaDeg) >= 89) return null;
					const xb = W / 2 + fRectH * Math.tan(a);
					if (xb < -0.1 * W || xb > 1.1 * W) return null;
					return { xb, dy: (fRectH * vScale * Math.tan(e)) / Math.cos(a) };
				}
			}
		};
		const toX = (x: number) => x * z + tx;
		const toY = (y: number) => y * z + ty;

		// reference horizon polyline (straight between handles: warp is
		// piecewise-linear and the roll shear is linear)
		ctx.setLineDash([6, 6]);
		ctx.strokeStyle = 'rgba(255,255,255,0.35)';
		ctx.lineWidth = 1;
		ctx.beginPath();
		for (let i = 0; i < warp.length; i++) {
			const xb = (i / (warp.length - 1)) * W;
			if (i) ctx.lineTo(toX(xb), toY(hyBase(xb)));
			else ctx.moveTo(toX(xb), toY(hyBase(xb)));
		}
		ctx.stroke();
		ctx.setLineDash([]);

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
					const yb = hyBase(pt.xb) - pt.dy;
					if (pen) ctx.lineTo(toX(pt.xb), toY(yb));
					else ctx.moveTo(toX(pt.xb), toY(yb));
					pen = true;
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
			const inputs: { label: string; cx: number; cy: number; pillW: number; id?: string }[] = [];
			for (const m of marks) {
				if (!showPlaces && m.kind && PLACE_KINDS.has(m.kind)) continue;
				if (visCutoffM !== null && m.distance_m > visCutoffM) continue;
				const delta = wrapDelta(m.azimuth_deg - centre);
				const elev =
					meta.elev_max_deg - m.v * (meta.elev_max_deg - meta.elev_min_deg);
				const pt = project(delta, elev);
				if (!pt) continue;
				const xb = pt.xb;
				const yb = hyBase(xb) - pt.dy;
				const km = m.distance_m / 1000;
				const label = `${m.name} · ${km >= 10 ? Math.round(km) : km.toFixed(1)} km`;
				inputs.push({
					label,
					cx: toX(xb),
					cy: toY(yb),
					pillW: Math.ceil(ctx.measureText(label).width) + 12,
					id: m.kind
				});
			}
			ctx.textBaseline = 'middle';
			for (const l of layoutSkyLabels(inputs, sw, sh, { pillH: 18, leader: 14 })) {
				// settlements tinted blue vs terrain features' yellow/black
				const isPlace = !!l.id && PLACE_KINDS.has(l.id);
				ctx.strokeStyle = 'rgba(255,255,255,0.55)';
				ctx.lineWidth = 1;
				ctx.beginPath();
				ctx.moveTo(l.cx, l.ty + l.pillH);
				ctx.lineTo(l.cx, l.cy - 3);
				ctx.stroke();
				ctx.beginPath();
				ctx.arc(l.cx, l.cy, 2.2, 0, Math.PI * 2);
				ctx.fillStyle = isPlace ? 'rgba(143,180,217,0.95)' : 'rgba(255,220,50,0.95)';
				ctx.fill();
				ctx.beginPath();
				ctx.roundRect(l.tx, l.ty, l.pillW, l.pillH, 4);
				ctx.fillStyle = isPlace ? 'rgba(20,44,74,0.68)' : 'rgba(0,0,0,0.62)';
				ctx.fill();
				ctx.strokeStyle = 'rgba(255,255,255,0.35)';
				ctx.stroke();
				ctx.fillStyle = '#fff';
				ctx.fillText(l.label, l.tx + 6, l.ty + l.pillH / 2 + 0.5);
			}
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
		void showCurve;
		void showLabels;
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
		void visLog;
		if (!photo || suppressDraft) {
			if (photo && suppressDraft)
				console.log('overlay-sync: change while suppressed (load not finished?)');
			return;
		}
		const payload = fitPayload();
		const bare = bareOf(payload);
		// identical alignment to one just received from another window → the
		// writer already persisted it; rewriting would ping-pong events
		if (bare === lastSync) return;
		lastSync = bare;
		lastTs = payload.saved_at;
		const raw = JSON.stringify(payload);
		try {
			localStorage.setItem(liveKey(photo.id), raw);
			console.log(`overlay-sync: wrote ${liveKey(photo.id)}`);
		} catch (e) {
			console.log('overlay-sync: localStorage write failed', e);
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
	// Wheel must be a manual non-passive listener to preventDefault scroll.
	function stageSetup(node: HTMLElement) {
		node.addEventListener('wheel', onWheel, { passive: false });
		const ro = new ResizeObserver(() => {
			fit();
			draw();
		});
		ro.observe(node);
		return {
			destroy: () => {
				node.removeEventListener('wheel', onWheel);
				ro.disconnect();
			}
		};
	}

	onMount(() => {
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
				console.log('overlay-sync: received via BroadcastChannel');
				applyRemote(e.data.raw as string);
			};
		const onStorage = (e: StorageEvent) => {
			if (!photo || !e.newValue || e.key !== liveKey(photo.id)) return;
			console.log('overlay-sync: received via storage event');
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
					console.log('overlay-sync: received via draft poll');
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
		};
	});
</script>

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
	{#if err}<span class="err">{err}</span>{/if}
</section>

{#if imgUrl}
	<section class="controls">
		<label><input type="checkbox" bind:checked={showCurve} /> skyline</label>
		<label><input type="checkbox" bind:checked={showLabels} /> labels</label>
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
			<input class="num" type="number" min="5" max="360" step="0.1" bind:value={fovDeg} />°
			<input type="range" min="20" max="360" step="0.1" bind:value={fovDeg} />
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
			fog
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
		<span class="group">
			segments <span class="val">{warp.length - 1}</span>
			<button onclick={() => (warp = resampleWarp(warp, warp.length + 1))} disabled={warp.length >= 9}>+</button>
			<button onclick={() => (warp = resampleWarp(warp, warp.length - 1))} disabled={warp.length <= 2}>−</button>
			<button onclick={() => { warp = warp.map(() => 0); rollDeg = 0; }} title="zero all handle offsets and roll">level</button>
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
			<button onclick={saveFit} disabled={saving || !photo}>save fit</button>
			{#if saveMsg}<span class="info">{saveMsg}</span>{/if}
			{#if draftState}<span class="info">{draftState}</span>{/if}
		</span>
	</section>

	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="stage"
		bind:this={stageEl}
		use:stageSetup
		onpointerdown={onPointerDown}
		onpointermove={onPointerMove}
		onpointerup={onPointerUp}
		onpointercancel={onPointerUp}
		ondblclick={resetView}
	>
		<img
			bind:this={img}
			src={imgUrl}
			alt={photo?.title ?? 'pano'}
			draggable="false"
			style="width: {baseW}px; transform: translate({tx}px, {ty}px) scale({z})"
			onload={() => {
				fit();
				draw();
			}}
		/>
		<canvas bind:this={overlay}></canvas>
	</div>
	<p class="hint">
		<b>proj</b> must match the pano's stitch output projection — read the .pto p-line's f-value
		(f0 rectilinear / f1 cylindrical / f2 equirect); it varies per pano, see
		docs/pano-source-archaeology.md. Wrong projection = unfittable by design.
		<b>wheel / pinch</b> zooms about the cursor, <b>drag</b> pans, <b>double-click</b> resets.
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
	.stage img {
		position: absolute;
		top: 0;
		left: 0;
		display: block;
		max-width: none;
		height: auto;
		transform-origin: 0 0;
		will-change: transform;
	}
	.stage canvas { position: absolute; inset: 0; pointer-events: none; }
	.hint { font-size: 12px; opacity: 0.6; max-width: 60rem; }
</style>

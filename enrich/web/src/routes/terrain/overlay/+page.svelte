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
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { apiBase } from '$lib/config';
	import { azimuthForColumn, type TerrainMeta } from '$terrain/depthPanoViewer';

	interface PhotoInfo {
		id: string;
		title: string | null;
		sizes: Record<string, { url?: string }> | null;
		width: number | null;
		height: number | null;
		pie: { bearing: number; half: number; calibrated: boolean } | null;
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

	// manual alignment: bearing trim + fov (horizontal, for uncalibrated
	// panos), horizon position + vertical scale (always manual)
	let bearingOffset = $state(0);
	let fovDeg = $state(90);
	let horizonFrac = $state(0.5);
	let vScale = $state(1);
	let showCurve = $state(true);

	let img: HTMLImageElement;
	let overlay: HTMLCanvasElement;

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
		if (!photoId) return;
		try {
			status = 'loading photo…';
			const pd = await api.get<{ photo: PhotoInfo }>(`/photos/${photoId}`);
			photo = pd.photo;
			if (photo.pie) {
				fovDeg = Math.round(photo.pie.half * 2);
				bearingOffset = 0;
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
				return;
			}
			render = done;
			status = 'loading depth…';
			const buf = await (await fetch(`${apiBase}/terrain/renders/${done.id}/depth`)).arrayBuffer();
			depth = new Uint16Array(buf);
			status = '';
			requestAnimationFrame(draw);
		} catch (e) {
			status = '';
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
	}

	/** render skyline: per column, elevation angle of the topmost non-sky
	 * row (null for all-sky columns) */
	function skyline(meta: TerrainMeta, d: Uint16Array): (number | null)[] {
		const step =
			(meta.elev_max_deg - meta.elev_min_deg) / meta.height;
		const out: (number | null)[] = new Array(meta.width).fill(null);
		for (let c = 0; c < meta.width; c++) {
			for (let r = 0; r < meta.height; r++) {
				if (d[r * meta.width + c] !== 0) {
					out[c] = meta.elev_max_deg - (r + 0.5) * step;
					break;
				}
			}
		}
		return out;
	}

	const wrapDelta = (d: number) => ((((d + 180) % 360) + 360) % 360) - 180;

	function draw() {
		if (!overlay || !img || !render?.meta || !depth || !photo) return;
		const W = img.clientWidth;
		const H = img.clientHeight;
		if (!W || !H) return;
		const dpr = globalThis.devicePixelRatio ?? 1;
		overlay.width = Math.round(W * dpr);
		overlay.height = Math.round(H * dpr);
		overlay.style.width = `${W}px`;
		overlay.style.height = `${H}px`;
		const ctx = overlay.getContext('2d')!;
		ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		ctx.clearRect(0, 0, W, H);

		const centre = (photo.pie?.bearing ?? 0) + bearingOffset;
		const horizonY = horizonFrac * H;
		const pxPerDeg = (W / fovDeg) * vScale; // equirect square-pixel guess × trim

		// reference horizon line
		ctx.setLineDash([6, 6]);
		ctx.strokeStyle = 'rgba(255,255,255,0.35)';
		ctx.lineWidth = 1;
		ctx.beginPath();
		ctx.moveTo(0, horizonY);
		ctx.lineTo(W, horizonY);
		ctx.stroke();
		ctx.setLineDash([]);

		if (!showCurve) return;
		const meta = render.meta;
		const sky = skyline(meta, depth);
		// draw as segments, breaking where columns leave the photo's fov or
		// have no terrain
		for (const [width, color] of [
			[4, 'rgba(0,0,0,0.55)'],
			[1.8, 'rgba(255,220,50,0.95)']
		] as const) {
			ctx.lineWidth = width;
			ctx.strokeStyle = color;
			ctx.beginPath();
			let pen = false;
			for (let c = 0; c < meta.width; c++) {
				const elev = sky[c];
				const delta = wrapDelta(azimuthForColumn(meta, c) - centre);
				if (elev === null || Math.abs(delta) > fovDeg / 2 + 2) {
					pen = false;
					continue;
				}
				const x = W * (0.5 + delta / fovDeg);
				const y = horizonY - elev * pxPerDeg;
				if (pen) ctx.lineTo(x, y);
				else ctx.moveTo(x, y);
				pen = true;
			}
			ctx.stroke();
		}
	}

	// redraw on any alignment change
	$effect(() => {
		void bearingOffset;
		void fovDeg;
		void horizonFrac;
		void vScale;
		void showCurve;
		draw();
	});

	onMount(() => {
		const pid = page.url.searchParams.get('photo');
		if (pid) {
			photoId = pid;
			load();
		}
		const ro = new ResizeObserver(() => draw());
		if (img) ro.observe(img);
		return () => ro.disconnect();
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
		<label>
			bearing {bearingOffset >= 0 ? '+' : ''}{bearingOffset.toFixed(1)}°
			<input type="range" min="-20" max="20" step="0.1" bind:value={bearingOffset} />
		</label>
		<label>
			fov {fovDeg}°
			<input type="range" min="20" max="360" step="1" bind:value={fovDeg} />
		</label>
		<label>
			horizon {(horizonFrac * 100).toFixed(1)}%
			<input type="range" min="0" max="1" step="0.002" bind:value={horizonFrac} />
		</label>
		<label>
			v-scale ×{vScale.toFixed(2)}
			<input type="range" min="0.4" max="2.5" step="0.01" bind:value={vScale} />
		</label>
	</section>

	<div class="stage">
		<img bind:this={img} src={imgUrl} alt={photo?.title ?? 'pano'} onload={() => draw()} />
		<canvas bind:this={overlay}></canvas>
	</div>
	<p class="hint">
		horizontal comes from the pie (trim with bearing/fov if it's assumed); the vertical
		anchor is yours: drag <b>horizon</b> until the dashed line sits on the photo's true
		horizon, then <b>v-scale</b> until near and far skyline match at once. A good fit here
		is a vertical calibration — worth saving once this proves useful.
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
	.stage { position: relative; }
	.stage img { display: block; width: 100%; height: auto; }
	.stage canvas { position: absolute; inset: 0; pointer-events: none; }
	.hint { font-size: 12px; opacity: 0.6; max-width: 60rem; }
</style>

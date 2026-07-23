<script lang="ts">
	// Terrain bench: view synthetic depth panoramas rendered from photo
	// viewpoints. The depth channel makes fog a LIVE per-pixel shader effect
	// (Koschmieder: fog = 1 − exp(−3.912·d/V) for meteorological visibility V)
	// and makes every click reversible into geo coordinates:
	// pixel → (azimuth, depth) → forward geodesic → lat/lon.
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import { apiBase } from '$lib/config';

	interface RenderRow {
		id: string;
		photo_id: string | null;
		lat: number;
		lon: number;
		status: string;
		error: string | null;
		meta: Record<string, number> | null;
		has_depth: boolean;
		has_preview: boolean;
		enqueued_at: string;
	}

	let renders = $state<RenderRow[]>([]);
	let sel = $state<RenderRow | null>(null);
	let err = $state<string | null>(null);
	let busy = $state(false);

	// enqueue form
	let photoId = $state('');
	let adhocLat = $state('');
	let adhocLon = $state('');

	// fog controls
	let visibilityKm = $state(80); // meteorological visibility
	let skyColor = $state('#a7cdf0');

	// clicked point
	let picked = $state<{
		lat: number;
		lon: number;
		distance_m: number;
		azimuth_deg: number;
	} | null>(null);

	let canvas: HTMLCanvasElement;
	let gl: WebGL2RenderingContext | null = null;
	let prog: WebGLProgram | null = null;
	let depthData: Float32Array | null = null;
	let meta: Record<string, number> | null = null;
	// view transform in texture UV space
	let scale = 1,
		offX = 0,
		offY = 0;

	async function load() {
		try {
			renders = (await api.get<{ renders: RenderRow[] }>('/terrain/renders')).renders;
			err = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
	}

	async function enqueue() {
		busy = true;
		try {
			const body = photoId
				? { photo_id: photoId }
				: { lat: parseFloat(adhocLat), lon: parseFloat(adhocLon) };
			await api.post('/terrain/enqueue', body);
			await load();
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			busy = false;
		}
	}

	const VS = `#version 300 es
	in vec2 aPos; out vec2 vUV;
	uniform vec3 uView; // offX, offY, scale
	void main(){ vUV = (aPos * 0.5 + 0.5) / uView.z + uView.xy;
		gl_Position = vec4(aPos.x, -aPos.y, 0.0, 1.0); }`;

	const FS = `#version 300 es
	precision highp float;
	in vec2 vUV; out vec4 frag;
	uniform sampler2D uColor; uniform sampler2D uDepth;
	uniform float uDensity; uniform vec3 uSky;
	void main(){
		if (vUV.x < 0.0 || vUV.x > 1.0 || vUV.y < 0.0 || vUV.y > 1.0) {
			frag = vec4(0.08, 0.09, 0.11, 1.0); return; }
		float d = texture(uDepth, vUV).r;
		vec3 c = texture(uColor, vUV).rgb;
		if (d <= 0.0) { // sky: subtle vertical gradient
			frag = vec4(mix(uSky * 1.08, uSky * 0.92, vUV.y), 1.0); return; }
		float fog = 1.0 - exp(-d * uDensity);
		frag = vec4(mix(c, uSky, fog), 1.0);
	}`;

	function compile(type: number, src: string): WebGLShader {
		const s = gl!.createShader(type)!;
		gl!.shaderSource(s, src);
		gl!.compileShader(s);
		if (!gl!.getShaderParameter(s, gl!.COMPILE_STATUS))
			throw new Error(gl!.getShaderInfoLog(s) ?? 'shader error');
		return s;
	}

	function initGL() {
		gl = canvas.getContext('webgl2');
		if (!gl) throw new Error('WebGL2 required for the fog viewer');
		prog = gl.createProgram()!;
		gl.attachShader(prog, compile(gl.VERTEX_SHADER, VS));
		gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FS));
		gl.linkProgram(prog);
		gl.useProgram(prog);
		const buf = gl.createBuffer();
		gl.bindBuffer(gl.ARRAY_BUFFER, buf);
		gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
		const loc = gl.getAttribLocation(prog, 'aPos');
		gl.enableVertexAttribArray(loc);
		gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
	}

	function tex(unit: number) {
		const t = gl!.createTexture();
		gl!.activeTexture(gl!.TEXTURE0 + unit);
		gl!.bindTexture(gl!.TEXTURE_2D, t);
		for (const p of [gl!.TEXTURE_WRAP_S, gl!.TEXTURE_WRAP_T])
			gl!.texParameteri(gl!.TEXTURE_2D, p, gl!.CLAMP_TO_EDGE);
		return t;
	}

	async function select(r: RenderRow) {
		sel = r;
		picked = null;
		if (r.status !== 'done' || !r.meta) return;
		meta = r.meta;
		const [img, depthBuf] = await Promise.all([
			new Promise<HTMLImageElement>((res, rej) => {
				const i = new Image();
				i.crossOrigin = 'anonymous';
				i.onload = () => res(i);
				i.onerror = rej;
				i.src = `${apiBase}/terrain/renders/${r.id}/preview`;
			}),
			fetch(`${apiBase}/terrain/renders/${r.id}/depth`).then((x) => x.arrayBuffer())
		]);
		const u16 = new Uint16Array(depthBuf);
		depthData = new Float32Array(u16.length);
		const s = meta.depth_scale_m ?? 4;
		for (let i = 0; i < u16.length; i++) depthData[i] = u16[i] * s; // 0 stays 0 = sky
		if (!gl) initGL();
		const W = meta.width,
			H = meta.height;
		tex(0);
		gl!.pixelStorei(gl!.UNPACK_FLIP_Y_WEBGL, false);
		gl!.texImage2D(gl!.TEXTURE_2D, 0, gl!.RGBA, gl!.RGBA, gl!.UNSIGNED_BYTE, img);
		gl!.texParameteri(gl!.TEXTURE_2D, gl!.TEXTURE_MIN_FILTER, gl!.LINEAR);
		gl!.texParameteri(gl!.TEXTURE_2D, gl!.TEXTURE_MAG_FILTER, gl!.LINEAR);
		tex(1);
		gl!.texImage2D(gl!.TEXTURE_2D, 0, gl!.R32F, W, H, 0, gl!.RED, gl!.FLOAT, depthData);
		for (const p of [gl!.TEXTURE_MIN_FILTER, gl!.TEXTURE_MAG_FILTER])
			gl!.texParameteri(gl!.TEXTURE_2D, p, gl!.NEAREST);
		gl!.uniform1i(gl!.getUniformLocation(prog!, 'uColor'), 0);
		gl!.uniform1i(gl!.getUniformLocation(prog!, 'uDepth'), 1);
		canvas.width = canvas.clientWidth * devicePixelRatio;
		canvas.height = (canvas.clientWidth * (H / W)) * devicePixelRatio;
		canvas.style.height = `${canvas.width / devicePixelRatio / (W / H)}px`;
		scale = 1;
		offX = offY = 0;
		draw();
	}

	function hex2rgb(h: string): [number, number, number] {
		return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as [
			number, number, number];
	}

	function draw() {
		if (!gl || !prog || !meta) return;
		gl.viewport(0, 0, canvas.width, canvas.height);
		gl.uniform3f(gl.getUniformLocation(prog, 'uView'), offX, offY, scale);
		// Koschmieder: extinction for 2% contrast threshold at visibility V
		gl.uniform1f(gl.getUniformLocation(prog, 'uDensity'), 3.912 / (visibilityKm * 1000));
		gl.uniform3f(gl.getUniformLocation(prog, 'uSky'), ...hex2rgb(skyColor));
		gl.drawArrays(gl.TRIANGLES, 0, 3);
	}

	$effect(() => {
		void visibilityKm;
		void skyColor;
		draw();
	});

	// ---- pan / zoom / click ----
	let dragging = false,
		moved = false,
		lastX = 0,
		lastY = 0;
	function uvAt(e: MouseEvent): [number, number] {
		const r = canvas.getBoundingClientRect();
		return [
			(e.clientX - r.left) / r.width / scale + offX,
			(e.clientY - r.top) / r.height / scale + offY
		];
	}
	function onWheel(e: WheelEvent) {
		e.preventDefault();
		const [ux, uy] = uvAt(e);
		scale = Math.min(40, Math.max(1, scale * (e.deltaY < 0 ? 1.2 : 1 / 1.2)));
		const r = canvas.getBoundingClientRect();
		offX = ux - (e.clientX - r.left) / r.width / scale;
		offY = uy - (e.clientY - r.top) / r.height / scale;
		draw();
	}
	function onDown(e: MouseEvent) {
		dragging = true;
		moved = false;
		lastX = e.clientX;
		lastY = e.clientY;
	}
	function onMove(e: MouseEvent) {
		if (!dragging) return;
		const r = canvas.getBoundingClientRect();
		offX -= (e.clientX - lastX) / r.width / scale;
		offY -= (e.clientY - lastY) / r.height / scale;
		if (Math.abs(e.clientX - lastX) + Math.abs(e.clientY - lastY) > 2) moved = true;
		lastX = e.clientX;
		lastY = e.clientY;
		draw();
	}
	function onUp(e: MouseEvent) {
		dragging = false;
		if (moved || !meta || !depthData) return;
		const [u, v] = uvAt(e);
		if (u < 0 || u > 1 || v < 0 || v > 1) return;
		const col = Math.min(meta.width - 1, Math.floor(u * meta.width));
		const row = Math.min(meta.height - 1, Math.floor(v * meta.height));
		const d = depthData[row * meta.width + col];
		if (d <= 0) {
			picked = null; // sky
			return;
		}
		const azStep = (meta.az_step_deg as number) ?? 0.05;
		const az = (((meta.az_start as number) + col * azStep) % 360 + 360) % 360;
		const p = destinationPoint(meta.lat, meta.lon, az, d);
		picked = { lat: p.lat, lon: p.lon, distance_m: d, azimuth_deg: az };
	}

	// forward geodesic — mirrors frontend/src/lib/geo.ts destinationPoint
	function destinationPoint(lat: number, lng: number, bearing: number, distM: number) {
		const R = 6371000;
		const d = distM / R;
		const br = (bearing * Math.PI) / 180;
		const la1 = (lat * Math.PI) / 180;
		const lo1 = (lng * Math.PI) / 180;
		const la2 = Math.asin(
			Math.sin(la1) * Math.cos(d) + Math.cos(la1) * Math.sin(d) * Math.cos(br)
		);
		const lo2 =
			lo1 +
			Math.atan2(
				Math.sin(br) * Math.sin(d) * Math.cos(la1),
				Math.cos(d) - Math.sin(la1) * Math.sin(la2)
			);
		return { lat: (la2 * 180) / Math.PI, lon: ((((lo2 * 180) / Math.PI + 540) % 360) - 180) };
	}

	onMount(load);
</script>

<h1>Terrain — synthetic depth panoramas</h1>
{#if err}<p class="err">{err}</p>{/if}

<section class="enqueue">
	<input placeholder="photo id (viewpoint from photo_mirror)" bind:value={photoId} />
	<span>or</span>
	<input placeholder="lat" size="9" bind:value={adhocLat} />
	<input placeholder="lon" size="9" bind:value={adhocLon} />
	<button onclick={enqueue} disabled={busy}>Enqueue render</button>
	<button onclick={load}>↻</button>
</section>

<section class="split">
	<ul class="renders">
		{#each renders as r (r.id)}
			<li class:active={sel?.id === r.id}>
				<button onclick={() => select(r)}>
					<b>{r.status}</b>
					{r.photo_id ?? `${r.lat.toFixed(4)}, ${r.lon.toFixed(4)}`}
					<small>{new Date(r.enqueued_at).toLocaleString()}</small>
					{#if r.error}<small class="err">{r.error}</small>{/if}
				</button>
			</li>
		{/each}
	</ul>

	<div class="viewer">
		<canvas
			bind:this={canvas}
			onwheel={onWheel}
			onmousedown={onDown}
			onmousemove={onMove}
			onmouseup={onUp}
			onmouseleave={() => (dragging = false)}
		></canvas>
		<div class="controls">
			<label>
				Visibility {visibilityKm} km
				<input type="range" min="2" max="300" bind:value={visibilityKm} />
			</label>
			<label>Sky / fog <input type="color" bind:value={skyColor} /></label>
			{#if picked}
				<div class="picked">
					📍 {picked.lat.toFixed(5)}, {picked.lon.toFixed(5)}
					· {(picked.distance_m / 1000).toFixed(1)} km @ {picked.azimuth_deg.toFixed(1)}°
					<a
						href={`https://hillview.cz/?lat=${picked.lat}&lon=${picked.lon}&zoom=14`}
						target="_blank">open on map</a
					>
					<button
						onclick={() =>
							navigator.clipboard.writeText(`${picked!.lat}, ${picked!.lon}`)}
						>copy</button
					>
				</div>
			{:else if sel?.status === 'done'}
				<div class="hint">scroll = zoom · drag = pan · click terrain = geo coords</div>
			{/if}
		</div>
	</div>
</section>

<style>
	.enqueue { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 1rem; }
	.split { display: grid; grid-template-columns: 320px 1fr; gap: 1rem; }
	.renders { list-style: none; padding: 0; margin: 0; overflow-y: auto; max-height: 70vh; }
	.renders li button { width: 100%; text-align: left; display: flex; flex-direction: column; }
	.renders li.active button { outline: 2px solid var(--accent, #4a90e2); }
	canvas { width: 100%; display: block; background: #16181c; cursor: crosshair; }
	.controls { display: flex; gap: 1.2rem; align-items: center; flex-wrap: wrap; padding: 0.5rem 0; }
	.picked { font-variant-numeric: tabular-nums; }
	.hint { opacity: 0.6; }
	.err { color: #d33; }
</style>

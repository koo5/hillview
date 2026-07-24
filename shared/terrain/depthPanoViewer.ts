/**
 * Depth-panorama viewer core — extracted from the enrichment workbench's
 * terrain bench so the SAME viewer runs in the main app's photo pane (the
 * "click a mountain, get its coords" story) and in enrich/web.
 *
 * Deliberately dependency-free (cf. $zoomview modules): no Svelte, no stores,
 * no $lib imports — a canvas goes in, WebGL2 + pointer handling come out.
 * Each app wraps it thinly (frontend: TerrainViewer.svelte; enrich/web:
 * routes/terrain/+page.svelte).
 *
 * What the depth channel buys us:
 *   - fog is a LIVE fragment-shader effect — Koschmieder extinction
 *     `1 − exp(−3.912·d/V)` for meteorological visibility V; sliders
 *     re-shade instantly, nothing re-renders;
 *   - a click is (azimuth, depth) → forward geodesic → geo coordinates —
 *     pure functions below, unit-tested without a GL context.
 *
 * Input artifacts (produced by enrich/terrain/renderer.py, served by the
 * workbench API today; graduation path: the main backend serves them next
 * to the photo pyramids):
 *   - preview:  shaded RGB JPEG, fog NOT baked in
 *   - depth:    row-major little-endian uint16, metres = value·depth_scale_m,
 *               0 = sky (raw buffer on purpose: canvases truncate PNG16 to 8)
 *   - meta:     grid geometry + viewpoint, see TerrainMeta
 *
 * Viewport model (terrain mode = "the zoom view over a synthetic 360°"):
 * the view transform is exposed as a RECT in the zoom view's OSD-style
 * convention — image width normalized to 1.0, y in width units — via
 * getRect/setRect + an onViewChange callback, so the app serializes it with
 * the same x1..y2 URL convention as the zoom view. Rects live on a cylinder:
 * TEXTURE_WRAP_S = REPEAT on both textures, the horizontal offset wraps
 * modulo 1, and a URL rect's x may leave [0, 1] — normalizeRect on parse.
 */

export interface TerrainMeta {
	width: number;
	height: number;
	/** azimuth of column-0 CENTER, degrees */
	az_start: number;
	/** azimuth of last-column center, degrees (fallback for az_step_deg) */
	az_end: number;
	az_step_deg?: number;
	elev_max_deg: number;
	elev_min_deg: number;
	/** viewpoint */
	lat: number;
	lon: number;
	depth_scale_m: number;
	/** the render's marched range — "what this can see" (coverage circle) */
	max_distance_m?: number;
}

export interface TerrainPick {
	lat: number;
	lon: number;
	distance_m: number;
	azimuth_deg: number;
	col: number;
	row: number;
}

export interface FogParams {
	/** meteorological visibility in km (Koschmieder 2% contrast threshold) */
	visibilityKm?: number;
	/** '#rrggbb' */
	skyColor?: string;
}

const R_EARTH_M = 6371000;

/** Forward geodesic on the sphere — mirrors frontend/src/lib/geo.ts and
 * enrich/terrain/renderer.py so all three agree on the click-back. */
export function destinationPoint(
	lat: number,
	lng: number,
	bearingDeg: number,
	distanceM: number
): { lat: number; lon: number } {
	const d = distanceM / R_EARTH_M;
	const br = (bearingDeg * Math.PI) / 180;
	const la1 = (lat * Math.PI) / 180;
	const lo1 = (lng * Math.PI) / 180;
	const la2 = Math.asin(Math.sin(la1) * Math.cos(d) + Math.cos(la1) * Math.sin(d) * Math.cos(br));
	const lo2 =
		lo1 +
		Math.atan2(Math.sin(br) * Math.sin(d) * Math.cos(la1), Math.cos(d) - Math.sin(la1) * Math.sin(la2));
	return { lat: (la2 * 180) / Math.PI, lon: ((((lo2 * 180) / Math.PI + 540) % 360) - 180) };
}

/** Column-center azimuth in [0, 360). Uses az_step_deg when present, else
 * derives it from the az_start→az_end span (centers, no wrap by design:
 * a full sweep is az_start≈0.025 → az_end≈359.975). */
export function azimuthForColumn(meta: TerrainMeta, col: number): number {
	const step =
		meta.az_step_deg ?? (meta.width > 1 ? (meta.az_end - meta.az_start) / (meta.width - 1) : 0);
	return (((meta.az_start + col * step) % 360) + 360) % 360;
}

/** The click-back as a pure function: (col, row) into the raw uint16 depth
 * buffer → geo coordinates. Returns null for sky pixels. */
export function pickFromDepth(
	meta: TerrainMeta,
	depth: Uint16Array,
	col: number,
	row: number
): TerrainPick | null {
	if (col < 0 || row < 0 || col >= meta.width || row >= meta.height) return null;
	const q = depth[row * meta.width + col];
	if (q === 0) return null; // sky
	const distance_m = q * meta.depth_scale_m;
	const azimuth_deg = azimuthForColumn(meta, col);
	const p = destinationPoint(meta.lat, meta.lon, azimuth_deg, distance_m);
	return { lat: p.lat, lon: p.lon, distance_m, azimuth_deg, col, row };
}

export function hexToRgb(hex: string): [number, number, number] {
	const h = hex.replace('#', '');
	return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as [number, number, number];
}

// ---- viewport rect (pure) ----

/** Viewport bounds in the zoom view's convention: image width normalized to
 * 1.0, y measured in width units (OSD viewport coordinates). x may leave
 * [0, 1] for seam-straddling views. */
export interface ViewRect {
	x1: number;
	y1: number;
	x2: number;
	y2: number;
}

/** Internal view transform in texture UV space. */
export interface ViewState {
	offX: number;
	offY: number;
	scale: number;
}

export function wrap01(x: number): number {
	return ((x % 1) + 1) % 1;
}

export function textureAspect(meta: TerrainMeta): number {
	return meta.height / meta.width;
}

export function rectFromView(meta: TerrainMeta, v: ViewState): ViewRect {
	const a = textureAspect(meta);
	const w = 1 / v.scale;
	return { x1: v.offX, y1: v.offY * a, x2: v.offX + w, y2: (v.offY + w) * a };
}

/** Inverse of rectFromView. Scale derives from the rect WIDTH alone (the
 * texture aspect is fixed, mirroring how the zoom view treats its bounds);
 * x wraps onto the cylinder, y passes through un-clamped like the pan does. */
export function viewFromRect(meta: TerrainMeta, r: ViewRect): ViewState {
	const a = textureAspect(meta);
	const scale = Math.min(40, Math.max(1, 1 / Math.max(1e-9, r.x2 - r.x1)));
	return { offX: wrap01(r.x1), offY: r.y1 / a, scale };
}

/** URL rects may arrive with x outside [0, 1] (seam wrap); shift the pair so
 * x1 lands in [0, 1) while preserving the width. */
export function normalizeRect(r: ViewRect): ViewRect {
	const shift = Math.floor(r.x1);
	return shift === 0 ? r : { ...r, x1: r.x1 - shift, x2: r.x2 - shift };
}

/** Azimuth at a horizontal texture coordinate u ∈ [0, 1): column centers sit
 * at (col + 0.5) / width, so this is azimuthForColumn at a fractional col. */
export function azimuthAtU(meta: TerrainMeta, u: number): number {
	return azimuthForColumn(meta, u * meta.width - 0.5);
}

/** Total angular sweep the full texture width covers (360 for a full pano). */
export function angularSpanDeg(meta: TerrainMeta): number {
	const step =
		meta.az_step_deg ?? (meta.width > 1 ? (meta.az_end - meta.az_start) / (meta.width - 1) : 0);
	return step * meta.width;
}

/** The map's view wedge, purely DERIVED from the rect (pane → map, one-way):
 * center-x → azimuth, width → wedge FOV. */
export function wedgeFromRect(
	meta: TerrainMeta,
	r: ViewRect
): { azimuthDeg: number; fovDeg: number } {
	return {
		azimuthDeg: azimuthAtU(meta, wrap01((r.x1 + r.x2) / 2)),
		fovDeg: Math.min(1, r.x2 - r.x1) * angularSpanDeg(meta)
	};
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
	if (vUV.y < 0.0 || vUV.y > 1.0) { // x wraps via TEXTURE_WRAP_S = REPEAT
		frag = vec4(0.08, 0.09, 0.11, 1.0); return; }
	float d = texture(uDepth, vUV).r;
	vec3 c = texture(uColor, vUV).rgb;
	if (d <= 0.0) { // sky: subtle vertical gradient
		frag = vec4(mix(uSky * 1.08, uSky * 0.92, vUV.y), 1.0); return; }
	float fog = 1.0 - exp(-d * uDensity);
	frag = vec4(mix(c, uSky, fog), 1.0);
}`;

export interface LoadOptions {
	/** either URLs… */
	previewUrl?: string;
	depthUrl?: string;
	/** …or preloaded data */
	image?: HTMLImageElement | ImageBitmap;
	depth?: Uint16Array;
	meta: TerrainMeta;
}

export class DepthPanoViewer {
	private canvas: HTMLCanvasElement;
	private gl: WebGL2RenderingContext;
	private prog: WebGLProgram;
	private onPick?: (pick: TerrainPick | null) => void;
	private onViewChange?: (rect: ViewRect) => void;
	private pendingRect: ViewRect | null = null;
	private meta: TerrainMeta | null = null;
	private depthU16: Uint16Array | null = null;
	// view transform in texture UV space
	private scale = 1;
	private offX = 0;
	private offY = 0;
	private visibilityKm = 80;
	private skyColor = '#a7cdf0';
	// pointer state (mouse + touch + pinch via Pointer Events)
	private pointers = new Map<number, { x: number; y: number }>();
	private pinchDist = 0;
	private moved = 0;
	private resizeObs: ResizeObserver | null = null;
	private disposed = false;

	constructor(
		canvas: HTMLCanvasElement,
		opts: {
			onPick?: (p: TerrainPick | null) => void;
			/** fires on USER-driven view changes (and reset/load), never from
			 * setRect — so URL-sync consumers can't feedback-loop */
			onViewChange?: (rect: ViewRect) => void;
		} = {}
	) {
		this.canvas = canvas;
		this.onPick = opts.onPick;
		this.onViewChange = opts.onViewChange;
		const gl = canvas.getContext('webgl2');
		if (!gl) throw new Error('WebGL2 is required for the terrain viewer');
		this.gl = gl;
		this.prog = this.link();
		const buf = gl.createBuffer();
		gl.bindBuffer(gl.ARRAY_BUFFER, buf);
		gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
		const loc = gl.getAttribLocation(this.prog, 'aPos');
		gl.enableVertexAttribArray(loc);
		gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
		canvas.style.touchAction = 'none'; // we own pan/pinch
		canvas.addEventListener('wheel', this.onWheel, { passive: false });
		canvas.addEventListener('pointerdown', this.onDown);
		canvas.addEventListener('pointermove', this.onMove);
		canvas.addEventListener('pointerup', this.onUp);
		canvas.addEventListener('pointercancel', this.onCancel);
		this.resizeObs = new ResizeObserver(() => this.resize());
		this.resizeObs.observe(canvas);
	}

	private link(): WebGLProgram {
		const gl = this.gl;
		const compile = (type: number, src: string) => {
			const s = gl.createShader(type)!;
			gl.shaderSource(s, src);
			gl.compileShader(s);
			if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
				throw new Error(gl.getShaderInfoLog(s) ?? 'shader error');
			return s;
		};
		const p = gl.createProgram()!;
		gl.attachShader(p, compile(gl.VERTEX_SHADER, VS));
		gl.attachShader(p, compile(gl.FRAGMENT_SHADER, FS));
		gl.linkProgram(p);
		if (!gl.getProgramParameter(p, gl.LINK_STATUS))
			throw new Error(gl.getProgramInfoLog(p) ?? 'link error');
		gl.useProgram(p);
		return p;
	}

	async load(opts: LoadOptions): Promise<void> {
		const meta = opts.meta;
		const [image, depthBuf] = await Promise.all([
			opts.image ??
				new Promise<HTMLImageElement>((res, rej) => {
					const i = new Image();
					i.crossOrigin = 'anonymous';
					i.onload = () => res(i);
					i.onerror = () => rej(new Error(`preview load failed: ${opts.previewUrl}`));
					i.src = opts.previewUrl!;
				}),
			opts.depth ??
				fetch(opts.depthUrl!).then(async (r) => {
					if (!r.ok) throw new Error(`depth load failed: HTTP ${r.status}`);
					return new Uint16Array(await r.arrayBuffer());
				})
		]);
		if (this.disposed) return;
		const depthU16 = depthBuf instanceof Uint16Array ? depthBuf : new Uint16Array(depthBuf);
		if (depthU16.length !== meta.width * meta.height)
			throw new Error(
				`depth buffer size ${depthU16.length} != ${meta.width}x${meta.height} from meta`
			);
		this.meta = meta;
		this.depthU16 = depthU16;
		const depthF32 = new Float32Array(depthU16.length);
		for (let i = 0; i < depthU16.length; i++) depthF32[i] = depthU16[i] * meta.depth_scale_m;

		const gl = this.gl;
		const tex = (unit: number) => {
			gl.activeTexture(gl.TEXTURE0 + unit);
			gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT); // cylinder seam
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
		};
		tex(0);
		gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
		gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
		tex(1);
		gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, meta.width, meta.height, 0, gl.RED, gl.FLOAT, depthF32);
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
		gl.uniform1i(gl.getUniformLocation(this.prog, 'uColor'), 0);
		gl.uniform1i(gl.getUniformLocation(this.prog, 'uDepth'), 1);
		if (this.pendingRect) {
			const v = viewFromRect(meta, this.pendingRect);
			this.pendingRect = null;
			this.scale = v.scale;
			this.offX = v.offX;
			this.offY = v.offY;
		} else {
			this.scale = 1;
			this.offX = 0;
			this.offY = 0;
		}
		this.resize();
		this.emitView();
	}

	/** Current viewport rect (zoom view convention), null before load. */
	getRect(): ViewRect | null {
		return this.meta
			? rectFromView(this.meta, { offX: this.offX, offY: this.offY, scale: this.scale })
			: null;
	}

	/** Restore a viewport rect (e.g. from URL params — run normalizeRect on
	 * parse first). Before load() it is stashed and applied on load, so deep
	 * links restore without a flash of the reset view. Does NOT emit. */
	setRect(rect: ViewRect): void {
		if (!this.meta) {
			this.pendingRect = rect;
			return;
		}
		const v = viewFromRect(this.meta, rect);
		this.scale = v.scale;
		this.offX = v.offX;
		this.offY = v.offY;
		this.draw();
	}

	private emitView(): void {
		if (this.meta && this.onViewChange)
			this.onViewChange(
				rectFromView(this.meta, { offX: this.offX, offY: this.offY, scale: this.scale })
			);
	}

	setFog({ visibilityKm, skyColor }: FogParams): void {
		if (visibilityKm !== undefined) this.visibilityKm = visibilityKm;
		if (skyColor !== undefined) this.skyColor = skyColor;
		this.draw();
	}

	resetView(): void {
		this.scale = 1;
		this.offX = 0;
		this.offY = 0;
		this.draw();
		this.emitView();
	}

	resize(): void {
		const { canvas, meta } = this;
		if (!meta || canvas.clientWidth === 0) return;
		const dpr = globalThis.devicePixelRatio ?? 1;
		const cssH = canvas.clientWidth * (meta.height / meta.width);
		canvas.style.height = `${cssH}px`;
		canvas.width = Math.round(canvas.clientWidth * dpr);
		canvas.height = Math.round(cssH * dpr);
		this.draw();
	}

	draw(): void {
		const { gl, prog, meta } = this;
		if (!meta) return;
		gl.viewport(0, 0, this.canvas.width, this.canvas.height);
		gl.uniform3f(gl.getUniformLocation(prog, 'uView'), this.offX, this.offY, this.scale);
		// Koschmieder: extinction for 2% contrast threshold at visibility V
		gl.uniform1f(gl.getUniformLocation(prog, 'uDensity'), 3.912 / (this.visibilityKm * 1000));
		const [r, g, b] = hexToRgb(this.skyColor);
		gl.uniform3f(gl.getUniformLocation(prog, 'uSky'), r, g, b);
		gl.drawArrays(gl.TRIANGLES, 0, 3);
	}

	/** Test/instrumentation hook: RGBA at a CSS-pixel position relative to the
	 * canvas. Redraws then reads synchronously in the same task, so it works
	 * without preserveDrawingBuffer (canvas readback is blank after the frame
	 * otherwise — the e2e suites sample fog behavior through this). */
	readPixel(cssX: number, cssY: number): [number, number, number, number] {
		this.draw();
		const gl = this.gl;
		const r = this.canvas.getBoundingClientRect();
		const x = Math.min(this.canvas.width - 1,
			Math.max(0, Math.round((cssX / r.width) * this.canvas.width)));
		const yTop = Math.min(this.canvas.height - 1,
			Math.max(0, Math.round((cssY / r.height) * this.canvas.height)));
		const out = new Uint8Array(4);
		gl.readPixels(x, this.canvas.height - 1 - yTop, 1, 1,
			gl.RGBA, gl.UNSIGNED_BYTE, out);
		return [out[0], out[1], out[2], out[3]];
	}

	destroy(): void {
		this.disposed = true;
		this.resizeObs?.disconnect();
		const c = this.canvas;
		c.removeEventListener('wheel', this.onWheel);
		c.removeEventListener('pointerdown', this.onDown);
		c.removeEventListener('pointermove', this.onMove);
		c.removeEventListener('pointerup', this.onUp);
		c.removeEventListener('pointercancel', this.onCancel);
		this.gl.getExtension('WEBGL_lose_context')?.loseContext();
	}

	// ---- navigation ----

	private uvAt(clientX: number, clientY: number): [number, number] {
		const r = this.canvas.getBoundingClientRect();
		return [
			(clientX - r.left) / r.width / this.scale + this.offX,
			(clientY - r.top) / r.height / this.scale + this.offY
		];
	}

	private zoomAt(clientX: number, clientY: number, factor: number): void {
		const [ux, uy] = this.uvAt(clientX, clientY);
		this.scale = Math.min(40, Math.max(1, this.scale * factor));
		const r = this.canvas.getBoundingClientRect();
		this.offX = wrap01(ux - (clientX - r.left) / r.width / this.scale);
		this.offY = uy - (clientY - r.top) / r.height / this.scale;
		this.draw();
		this.emitView();
	}

	private onWheel = (e: WheelEvent): void => {
		e.preventDefault();
		this.zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.2 : 1 / 1.2);
	};

	private onDown = (e: PointerEvent): void => {
		this.canvas.setPointerCapture(e.pointerId);
		this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
		if (this.pointers.size === 1) this.moved = 0;
		if (this.pointers.size === 2) this.pinchDist = this.pointerDist();
	};

	private onMove = (e: PointerEvent): void => {
		const prev = this.pointers.get(e.pointerId);
		if (!prev) return;
		this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
		if (this.pointers.size === 2) {
			const d = this.pointerDist();
			if (this.pinchDist > 0) {
				const [a, b] = [...this.pointers.values()];
				this.zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, d / this.pinchDist);
			}
			this.pinchDist = d;
			this.moved += 10;
			return;
		}
		const r = this.canvas.getBoundingClientRect();
		this.offX = wrap01(this.offX - (e.clientX - prev.x) / r.width / this.scale);
		this.offY -= (e.clientY - prev.y) / r.height / this.scale;
		this.moved += Math.abs(e.clientX - prev.x) + Math.abs(e.clientY - prev.y);
		this.draw();
		this.emitView();
	};

	private onUp = (e: PointerEvent): void => {
		this.pointers.delete(e.pointerId);
		this.pinchDist = 0;
		if (this.moved > 4 || !this.meta || !this.depthU16 || !this.onPick) return;
		const [uRaw, v] = this.uvAt(e.clientX, e.clientY);
		if (v < 0 || v > 1) return;
		const u = wrap01(uRaw); // seam: the viewport lives on a cylinder
		const col = Math.min(this.meta.width - 1, Math.floor(u * this.meta.width));
		const row = Math.min(this.meta.height - 1, Math.floor(v * this.meta.height));
		this.onPick(pickFromDepth(this.meta, this.depthU16, col, row));
	};

	private onCancel = (e: PointerEvent): void => {
		this.pointers.delete(e.pointerId);
		this.pinchDist = 0;
	};

	private pointerDist(): number {
		const [a, b] = [...this.pointers.values()];
		return Math.hypot(a.x - b.x, a.y - b.y);
	}
}

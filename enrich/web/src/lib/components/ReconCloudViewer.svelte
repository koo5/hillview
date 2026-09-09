<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { apiBase } from '$lib/config';

	// Orbitable point cloud + camera frusta for one reconstruction.
	//
	// The cloud arrives as packed [float32 xyz][uint8 rgb] rather than the PLY on disk:
	// reconstruct.py writes ASCII, so the sparse cloud is ~65 MB and a dense one runs to
	// hundreds — 15 bytes/point is what makes this openable in a browser at all.
	//
	// Frusta are the part the old viz_app viewer lacked, and they are what makes a bad solve
	// legible: a collapsed run shows its cameras piled in a corner, and an impostor sits
	// somewhere the real ones do not.
	let {
		runId,
		dense = false,
		maxPoints = 900000,
		showCameras = true,
		showGround = true,
		showMap = true,
		showPhotos = false
	}: {
		runId: string;
		dense?: boolean;
		maxPoints?: number;
		showCameras?: boolean;
		showGround?: boolean;
		showMap?: boolean;
		showPhotos?: boolean;
	} = $props();

	let el: HTMLDivElement;
	let status = $state('loading…');
	let pointSize = $state(1.0);
	let nPoints = $state(0);

	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let three: any = null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let renderer: any = null,
		scene: any = null,
		camera: any = null,
		controls: any = null,
		cloud: any = null;
	let raf = 0;
	let disposed = false;
	// held at top level: onDestroy cannot be registered from inside the async onMount
	// callback (Svelte 5 only allows lifecycle registration during initialisation)
	let ro: ResizeObserver | null = null;
	let coreScale = $state(100);
	let groundZ = 0;
	let extentM = $state(0);
	let nBuildings = $state(0);
	let mapNote = $state('');
	let camHeight = $state(0);
	// Orbit is for judging a model from outside; fly is for being IN it -- Descent-style
	// six degrees of freedom, no gravity, no up: pitch and yaw are about the camera's own
	// axes, roll is on Q/E, and there is momentum. Pointer lock so the mouse is a look
	// axis rather than a cursor.
	let mode = $state<'orbit' | 'fly'>('orbit');
	let flySpeed = $state(1); // multiplier on a scene-sized base speed
	let locked = $state(false);
	const keys = new Set<string>();
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let vel: any = null; // THREE.Vector3, camera-local velocity
	let lastT = 0;
	let spacing = 0;
	let minWorldSize = 0;
	let pointPx = $state(0);
	let edl = $state(true);
	let camScale = $state(1);
	let photoOpacity = $state(1);
	let edlStrength = $state(1.0);
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let edlPass: any = null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let camGroups: any[] = [];
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let photoMats: any[] = [];
	let nPhotosLoaded = $state(0);
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let camsGroup: any = null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let mapGroup: any = null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let sceneOffset: any = null;
	let sceneSize = 1;
	let mounted = $state(false);

	// --- layer attach/detach, so a toggle never disturbs the camera -----------------
	async function syncCameras() {
		if (!scene || !three) return;
		if (camsGroup) {
			scene.remove(camsGroup);
			disposeTree(camsGroup);
			camsGroup = null;
		}
		camGroups = [];
		for (const m of photoMats) {
			m.map?.dispose?.();
			m.dispose?.();
		}
		photoMats = [];
		nPhotosLoaded = 0;
		if (!showCameras) return;
		const g = await loadCameras(three, sceneSize);
		if (!g || disposed || !scene) return;
		g.position.copy(sceneOffset);
		camsGroup = g;
		scene.add(g);
	}

	function syncMap() {
		if (!scene || !three) return;
		if (!showMap) {
			if (mapGroup) {
				scene.remove(mapGroup);
				disposeTree(mapGroup);
				mapGroup = null;
			}
			return;
		}
		if (mapGroup) return;
		// Overpass can be slow or rate-limited; the cloud must already be on screen and
		// orbitable when it is, so its failure is a note, not a dead viewer.
		loadMap(three, groundZ - sceneOffset.z)
			.then((m) => {
				if (disposed || !m || !scene || !showMap) return;
				m.position.copy(sceneOffset);
				mapGroup = m;
				scene.add(m);
			})
			.catch((e) => {
				mapNote = `map unavailable: ${e instanceof Error ? e.message : String(e)}`;
			});
	}

	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	function disposeTree(root: any) {
		root.traverse?.((o: { geometry?: { dispose?: () => void }; material?: unknown }) => {
			o.geometry?.dispose?.();
			const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
			for (const m of mats as { map?: { dispose?: () => void }; dispose?: () => void }[]) {
				m.map?.dispose?.();
				m.dispose?.();
			}
		});
	}

	// a filled white disc, used as the point sprite's alpha mask
	function discSprite(THREE: typeof import('three')) {
		const n = 64;
		const c = document.createElement('canvas');
		c.width = c.height = n;
		const g = c.getContext('2d')!;
		g.fillStyle = '#fff';
		g.beginPath();
		g.arc(n / 2, n / 2, n / 2 - 1, 0, Math.PI * 2);
		g.fill();
		const t = new THREE.CanvasTexture(c);
		t.minFilter = THREE.LinearFilter;
		return t;
	}

	// World-units point size. 1.6x the measured spacing is what closes the gaps between
	// samples, but on a dense subject cloud that spacing is a few millimetres, which lands
	// UNDER one pixel at any sane viewing distance — the GPU then clamps every sprite to
	// 1 px and the slider appears dead. So the base size is the larger of "1.6x spacing"
	// and "whatever covers 2.5 px at the distance the scene is framed from".
	function pointWorldSize() {
		const bySpacing = spacing > 0 ? spacing * 1.6 : coreScale / 900;
		return Math.max(bySpacing, minWorldSize) * pointSize;
	}

	// px on screen = worldSize * projFactor / distance, with
	// projFactor = drawingBufferHeight / (2 tan(fov/2))
	function projFactor() {
		if (!renderer || !camera) return 0;
		const h = renderer.getDrawingBufferSize(new three.Vector2()).y;
		return h / (2 * Math.tan(((camera.fov / 2) * Math.PI) / 180));
	}

	function setPointSize() {
		const world = pointWorldSize();
		cloud.material.size = world;
		const dist = camera ? camera.position.distanceTo(controls?.target ?? cloud.position) : 0;
		pointPx = dist > 0 ? Math.round((world * projFactor()) / dist * 10) / 10 : 0;
	}

	// Median nearest-neighbour distance, via a uniform grid whose cell is chosen so the
	// average occupancy is a handful of points. Sampled: 4000 probes settle a median.
	function medianSpacing(pos: Float32Array, n: number): number {
		if (n < 100) return 0;
		let minX = Infinity, minY = Infinity, minZ = Infinity;
		let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
		const step = Math.max(1, Math.floor(n / 20000));
		for (let i = 0; i < n; i += step) {
			const x = pos[i * 3], y = pos[i * 3 + 1], z = pos[i * 3 + 2];
			if (x < minX) minX = x;
			if (x > maxX) maxX = x;
			if (y < minY) minY = y;
			if (y > maxY) maxY = y;
			if (z < minZ) minZ = z;
			if (z > maxZ) maxZ = z;
		}
		const vol = Math.max(1e-9, (maxX - minX) * (maxY - minY) * (maxZ - minZ));
		const cell = Math.max(1e-6, Math.cbrt((vol * 8) / n));
		const grid = new Map<string, number[]>();
		for (let i = 0; i < n; i++) {
			const k =
				Math.floor(pos[i * 3] / cell) + ',' +
				Math.floor(pos[i * 3 + 1] / cell) + ',' +
				Math.floor(pos[i * 3 + 2] / cell);
			const b = grid.get(k);
			if (b) { if (b.length < 24) b.push(i); } else grid.set(k, [i]);
		}
		const d: number[] = [];
		const probes = Math.min(4000, n);
		const pstep = Math.max(1, Math.floor(n / probes));
		for (let i = 0; i < n && d.length < probes; i += pstep) {
			const x = pos[i * 3], y = pos[i * 3 + 1], z = pos[i * 3 + 2];
			const cx = Math.floor(x / cell), cy = Math.floor(y / cell), cz = Math.floor(z / cell);
			let best = Infinity;
			for (let a = -1; a <= 1; a++)
				for (let b2 = -1; b2 <= 1; b2++)
					for (let c = -1; c <= 1; c++) {
						const bucket = grid.get(`${cx + a},${cy + b2},${cz + c}`);
						if (!bucket) continue;
						for (const j of bucket) {
							if (j === i) continue;
							const dx = pos[j * 3] - x, dy = pos[j * 3 + 1] - y, dz = pos[j * 3 + 2] - z;
							const dd = dx * dx + dy * dy + dz * dz;
							if (dd < best) best = dd;
						}
					}
			if (Number.isFinite(best) && best > 0) d.push(Math.sqrt(best));
		}
		if (d.length < 50) return 0;
		d.sort((p, q) => p - q);
		return d[Math.floor(d.length / 2)];
	}

	async function loadCloud(THREE: typeof import('three')) {
		const url =
			`${apiBase}/recon/runs/${runId}/cloud.bin?max_points=${maxPoints}` +
			(dense ? '&dense=true' : '');
		const res = await fetch(url);
		// A 404 or an error page decodes into ~100 "points" of arbitrary float garbage,
		// whose p90 radius can reach 1e38 — which then sizes a GridHelper with billions of
		// divisions and takes the whole browser tab down. Refuse the bytes instead.
		if (!res.ok) throw new Error(`cloud.bin ${res.status}`);
		const buf = await res.arrayBuffer();
		const stride = 15; // 3*float32 + 3*uint8
		const n = Math.floor(buf.byteLength / stride);
		const dv = new DataView(buf);
		const pos = new Float32Array(n * 3);
		const col = new Float32Array(n * 3);
		let k = 0;
		for (let i = 0; i < n; i++) {
			const o = i * stride;
			const x = dv.getFloat32(o, true);
			const y = dv.getFloat32(o + 4, true);
			const z = dv.getFloat32(o + 8, true);
			// a single NaN or 1e38 poisons the bounding box and therefore the framing
			if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) continue;
			if (Math.abs(x) > 1e6 || Math.abs(y) > 1e6 || Math.abs(z) > 1e6) continue;
			pos[k * 3] = x;
			pos[k * 3 + 1] = y;
			pos[k * 3 + 2] = z;
			col[k * 3] = dv.getUint8(o + 12) / 255;
			col[k * 3 + 1] = dv.getUint8(o + 13) / 255;
			col[k * 3 + 2] = dv.getUint8(o + 14) / 255;
			k++;
		}
		nPoints = k;
		if (!k) throw new Error('cloud is empty');
		const g = new THREE.BufferGeometry();
		g.setAttribute('position', new THREE.BufferAttribute(pos.subarray(0, k * 3), 3));
		g.setAttribute('color', new THREE.BufferAttribute(col.subarray(0, k * 3), 3));
		g.computeBoundingBox();
		return g;
	}

	// positions only, so the floor under the rig can be found before the grid is drawn
	async function loadCameraPositions(): Promise<number[][]> {
		try {
			const r = await fetch(`${apiBase}/recon/runs/${runId}/cameras`);
			if (!r.ok) return [];
			const d = await r.json();
			return (d.frames ?? []).map((f: { pos?: number[] }) => f.pos).filter(Boolean);
		} catch {
			return [];
		}
	}

	// One Group per camera, built at UNIT scale and placed by the ENU pose, so the size
	// slider becomes a scale on each group rather than a rebuild — and a photo texture
	// never has to be fetched twice.
	async function loadCameras(THREE: typeof import('three'), size: number) {
		const r = await fetch(
			`${apiBase}/recon/runs/${runId}/cameras` + (showPhotos ? '?images=true' : '')
		);
		if (!r.ok) return null;
		const d = await r.json();
		const group = new THREE.Group();
		const loader = new THREE.TextureLoader();
		loader.setCrossOrigin('anonymous');
		let loaded = 0;
		for (const f of d.frames) {
			// `pose` is the RAW solve pose; `pos`/`rot` are the same camera already carried
			// into metres east/north/up. The cloud is served in ENU, so using `pose` here
			// drew every frustum in a different coordinate system from the points it
			// belongs to — cameras floating beside their own scene. A frame without the
			// ENU pair is skipped rather than drawn in the wrong frame.
			const rot = f.rot;
			const t = f.pos;
			if (!rot || !t) continue;
			const m = new THREE.Matrix4();
			m.set(
				rot[0][0], rot[0][1], rot[0][2], t[0],
				rot[1][0], rot[1][1], rot[1][2], t[1],
				rot[2][0], rot[2][1], rot[2][2], t[2],
				0, 0, 0, 1
			);
			const cam = new THREE.Group();
			cam.applyMatrix4(m);

			// The frustum's true shape: the half-angles are atan(w/2f) and atan(h/2f) in
			// the pixels the SOLVER loaded, so its image plane at unit depth is exactly
			// (img_w/f) x (img_h/f). Falls back to a square when the size is unknown.
			const fp = f.focal_px || 400;
			const hw = f.img_w ? f.img_w / (2 * fp) : 0.7;
			const hh = f.img_h ? f.img_h / (2 * fp) : 0.7;
			const g = new THREE.BufferGeometry();
			const v = new Float32Array([
				0, 0, 0, -hw, -hh, 1, 0, 0, 0, hw, -hh, 1,
				0, 0, 0, hw, hh, 1, 0, 0, 0, -hw, hh, 1,
				-hw, -hh, 1, hw, -hh, 1, hw, -hh, 1, hw, hh, 1,
				hw, hh, 1, -hw, hh, 1, -hw, hh, 1, -hw, -hh, 1
			]);
			g.setAttribute('position', new THREE.BufferAttribute(v, 3));
			cam.add(
				new THREE.LineSegments(
					g,
					new THREE.LineBasicMaterial({ color: f.injected ? 0xe0a23a : 0x3987e5 })
				)
			);

			if (showPhotos && f.image_url) {
				const mat = new THREE.MeshBasicMaterial({
					color: 0xffffff,
					side: THREE.DoubleSide,
					transparent: true,
					opacity: photoOpacity
				});
				const mesh = new THREE.Mesh(new THREE.PlaneGeometry(hw * 2, hh * 2), mat);
				// camera space here is x right, y DOWN, z forward, so the plane's own +y
				// carries the image's BOTTOM: flipY off puts the texture the right way up
				mesh.position.set(0, 0, 1);
				cam.add(mesh);
				photoMats.push(mat);
				loader.load(
					f.image_url,
					(tex) => {
						tex.flipY = false;
						tex.colorSpace = THREE.SRGBColorSpace;
						mat.map = tex;
						mat.needsUpdate = true;
						nPhotosLoaded = ++loaded;
					},
					undefined,
					() => {}
				);
			}
			// a bare frustum is a marker, so it stays small; a frustum carrying its
			// photograph is meant to be looked at, so it starts three times bigger
			cam.userData.unit = size * (showPhotos ? 0.06 : 0.02);
			cam.scale.setScalar(cam.userData.unit * camScale);
			camGroups.push(cam);
			group.add(cam);
		}
		return group;
	}


	// The map layer: OSM footprints extruded to their tagged height, in the same ENU
	// metres as the cloud. MASt3R gives its confidence to the near field and almost none
	// to the buildings behind it, so without this the far half of every spot is missing
	// and there is nothing to judge the near half against.
	async function loadMap(THREE: typeof import('three'), groundLevel: number) {
		const r = await fetch(`${apiBase}/recon/runs/${runId}/map`);
		if (!r.ok) return null;
		const d = await r.json();
		const group = new THREE.Group();
		let nb = 0;
		// One merged wireframe per height source: a guessed height must not look surveyed.
		const edges: Record<string, number[]> = { height: [], levels: [], default: [] };
		const faces: number[] = [];
		for (const b of d.buildings ?? []) {
			const ring: [number, number][] = b.ring;
			if (ring.length < 3) continue;
			nb++;
			const top = groundLevel + (b.height_m ?? 7);
			const bucket = edges[b.height_source] ?? edges.default;
			for (let i = 0; i + 1 < ring.length; i++) {
				const [x0, y0] = ring[i];
				const [x1, y1] = ring[i + 1];
				// base, cap and one vertical per vertex — enough to read as a solid
				bucket.push(x0, y0, groundLevel, x1, y1, groundLevel);
				bucket.push(x0, y0, top, x1, y1, top);
				bucket.push(x0, y0, groundLevel, x0, y0, top);
				// two triangles for the translucent wall quad
				faces.push(x0, y0, groundLevel, x1, y1, groundLevel, x1, y1, top);
				faces.push(x0, y0, groundLevel, x1, y1, top, x0, y0, top);
			}
		}
		const colours: Record<string, number> = {
			height: 0xff9a2e,
			levels: 0xd08a44,
			default: 0x7a6a55
		};
		for (const [k, arr] of Object.entries(edges)) {
			if (!arr.length) continue;
			const g = new THREE.BufferGeometry();
			g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(arr), 3));
			group.add(
				new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: colours[k] }))
			);
		}
		if (faces.length) {
			const g = new THREE.BufferGeometry();
			g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(faces), 3));
			g.computeVertexNormals();
			group.add(
				new THREE.Mesh(
					g,
					new THREE.MeshBasicMaterial({
						color: 0x6b4a1f,
						transparent: true,
						opacity: 0.22,
						side: THREE.DoubleSide,
						depthWrite: false
					})
				)
			);
		}
		const lines = (items: { line: [number, number][] }[], colour: number, z: number) => {
			const arr: number[] = [];
			for (const it of items ?? []) {
				for (let i = 0; i + 1 < it.line.length; i++) {
					arr.push(it.line[i][0], it.line[i][1], z, it.line[i + 1][0], it.line[i + 1][1], z);
				}
			}
			if (!arr.length) return;
			const g = new THREE.BufferGeometry();
			g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(arr), 3));
			group.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: colour })));
		};
		lines(d.walls, 0x4fa8d8, groundLevel + 1.0);
		lines(d.roads, 0x53627a, groundLevel + 0.05);
		nBuildings = nb;
		return group;
	}

	// ---------------------------------------------------------------- eye-dome lighting
	// The trick that makes a point cloud look solid without meshing it (Potree/CloudCompare
	// use the same one). Render to an offscreen target with a depth texture, then shade
	// each pixel by how much NEARER it is than its neighbours: silhouettes and creases go
	// dark, flat surfaces stay flat. Points already occlude each other via the depth
	// buffer; what they lack is shading, and this supplies it from depth alone — no
	// normals, no lights, no mesh.
	function makeEdl(THREE: typeof import('three'), w: number, h: number) {
		const target = new THREE.WebGLRenderTarget(w, h, {
			minFilter: THREE.NearestFilter,
			magFilter: THREE.NearestFilter,
			depthTexture: new THREE.DepthTexture(w, h)
		});
		const quadScene = new THREE.Scene();
		const quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
		const material = new THREE.ShaderMaterial({
			uniforms: {
				tColor: { value: target.texture },
				tDepth: { value: target.depthTexture },
				uTexel: { value: new THREE.Vector2(1 / w, 1 / h) },
				uStrength: { value: 1.0 },
				uRadius: { value: 1.4 },
				uNear: { value: 0.1 },
				uFar: { value: 1000 }
			},
			vertexShader: `
				varying vec2 vUv;
				void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
			`,
			fragmentShader: `
				precision highp float;
				varying vec2 vUv;
				uniform sampler2D tColor;
				uniform sampler2D tDepth;
				uniform vec2 uTexel;
				uniform float uStrength, uRadius, uNear, uFar;
				// linear eye depth, so the response does not collapse near the far plane
				float eyeZ(vec2 uv) {
					float d = texture2D(tDepth, uv).x;
					if (d >= 1.0) return -1.0;
					float ndc = d * 2.0 - 1.0;
					return (2.0 * uNear * uFar) / (uFar + uNear - ndc * (uFar - uNear));
				}
				void main() {
					vec4 c = texture2D(tColor, vUv);
					float z = eyeZ(vUv);
					if (z < 0.0) { gl_FragColor = c; return; }
					float lz = log2(z);
					float sum = 0.0;
					const int N = 8;
					vec2 dirs[8];
					dirs[0] = vec2( 1.0, 0.0); dirs[1] = vec2(-1.0, 0.0);
					dirs[2] = vec2( 0.0, 1.0); dirs[3] = vec2( 0.0,-1.0);
					dirs[4] = vec2( 0.7, 0.7); dirs[5] = vec2(-0.7, 0.7);
					dirs[6] = vec2( 0.7,-0.7); dirs[7] = vec2(-0.7,-0.7);
					for (int i = 0; i < N; i++) {
						vec2 uv = vUv + dirs[i] * uTexel * uRadius;
						float nz = eyeZ(uv);
						// background counts as "much further", which is what draws silhouettes
						sum += nz < 0.0 ? 1.0 : max(0.0, lz - log2(nz));
					}
					float shade = exp(-sum * 40.0 * uStrength / float(N));
					gl_FragColor = vec4(c.rgb * shade, c.a);
				}
			`
		});
		const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
		quad.frustumCulled = false;
		quadScene.add(quad);
		return { target, quadScene, quadCam, material };
	}

	// One frame of flight. Thrust along the camera's local axes with inertia (Descent
	// coasts), look from pointer-lock deltas, roll on Q/E, L to level the wings.
	function flyStep(THREE: typeof import('three'), dt: number) {
		if (!camera || !vel) return;
		const base = (coreScale || 10) * 0.35 * flySpeed; // units per second at full thrust
		const acc = base * 4;
		const thrust = new THREE.Vector3(
			(keys.has('KeyD') || keys.has('ArrowRight') ? 1 : 0) -
				(keys.has('KeyA') || keys.has('ArrowLeft') ? 1 : 0),
			(keys.has('KeyR') || keys.has('Space') ? 1 : 0) -
				(keys.has('KeyF') || keys.has('ShiftLeft') || keys.has('ShiftRight') ? 1 : 0),
			(keys.has('KeyS') || keys.has('ArrowDown') ? 1 : 0) -
				(keys.has('KeyW') || keys.has('ArrowUp') ? 1 : 0)
		);
		vel.addScaledVector(thrust, acc * dt);
		vel.multiplyScalar(Math.pow(0.02, dt)); // damping: ~98% gone in a second
		if (vel.length() > base) vel.setLength(base);
		const step = vel.clone().multiplyScalar(dt).applyQuaternion(camera.quaternion);
		camera.position.add(step);
		const rollRate = 1.6; // rad/s
		if (keys.has('KeyQ')) camera.rotateZ(rollRate * dt);
		if (keys.has('KeyE')) camera.rotateZ(-rollRate * dt);
		if (keys.has('KeyL')) levelWings(THREE);
	}

	// Roll back to horizontal without changing where the camera points: rebuild the
	// orientation from the current forward vector and world up (Z, this is ENU).
	function levelWings(THREE: typeof import('three')) {
		const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
		if (Math.abs(fwd.z) > 0.999) return;
		const target = camera.position.clone().add(fwd);
		camera.up.set(0, 0, 1);
		camera.lookAt(target);
	}

	function onLook(e: MouseEvent) {
		if (mode !== 'fly' || !locked || !camera) return;
		const sens = 0.0022;
		camera.rotateY(-e.movementX * sens); // yaw about the camera's own up
		camera.rotateX(-e.movementY * sens); // pitch about its own right
	}

	function onKeyDown(e: KeyboardEvent) {
		if (mode !== 'fly') return;
		if (e.code === 'Escape') return; // browser releases the lock itself
		keys.add(e.code);
		if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.code))
			e.preventDefault();
	}
	function onKeyUp(e: KeyboardEvent) {
		keys.delete(e.code);
	}
	function onWheel(e: WheelEvent) {
		if (mode !== 'fly') return;
		e.preventDefault();
		flySpeed = Math.min(20, Math.max(0.05, flySpeed * (e.deltaY < 0 ? 1.25 : 0.8)));
	}
	function onLockChange() {
		locked = document.pointerLockElement === renderer?.domElement;
		if (!locked) keys.clear();
	}

	function setMode(m: 'orbit' | 'fly') {
		if (m === mode || !camera || !controls) return;
		mode = m;
		if (m === 'fly') {
			controls.enabled = false;
			vel?.set(0, 0, 0);
			lastT = 0;
		} else {
			if (document.pointerLockElement) document.exitPointerLock();
			keys.clear();
			// hand orbit a target ahead of wherever flight ended, and level the view so the
			// orbit does not inherit a roll it cannot undo
			levelWings(three);
			const fwd = new three.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
			controls.target.copy(camera.position).addScaledVector(fwd, (coreScale || 10) * 0.6);
			controls.enabled = true;
			controls.update();
		}
	}

	function onStageClick() {
		if (mode === 'fly' && renderer && !locked) renderer.domElement.requestPointerLock?.();
	}

	onMount(async () => {
		try {
			const THREE = await import('three');
			const { OrbitControls } = await import('three/examples/jsm/controls/OrbitControls.js');
			three = THREE;
			if (disposed) return;

			scene = new THREE.Scene();
			scene.background = new THREE.Color(0x0d0d0d);

			const g = await loadCloud(THREE);
			if (disposed) return;
			// Centre and scale must be ROBUST, not extremal: a dense cloud carries stray points
			// out to hundreds of metres (this walk claims depth to 415 m while the bulk sits
			// within tens), so a bbox centre and a bounding-sphere radius are both set by
			// outliers and leave the actual structure a speck in the middle of the view.
			// Median centre + p90 radius, from a sample — 20 k points settle these fine.
			const posArr = g.getAttribute('position').array as Float32Array;
			const nAll = posArr.length / 3;
			const stepS = Math.max(1, Math.floor(nAll / 20000));
			const xs: number[] = [], ys: number[] = [], zs: number[] = [];
			for (let i = 0; i < nAll; i += stepS) {
				xs.push(posArr[i * 3]);
				ys.push(posArr[i * 3 + 1]);
				zs.push(posArr[i * 3 + 2]);
			}
			const med = (a: number[]) => {
				a.sort((p, q) => p - q);
				return a[Math.floor(a.length / 2)];
			};
			const centre = new THREE.Vector3(med(xs), med(ys), med(zs));
			const d: number[] = [];
			for (let i = 0; i < nAll; i += stepS) {
				const dx = posArr[i * 3] - centre.x;
				const dy = posArr[i * 3 + 1] - centre.y;
				const dz = posArr[i * 3 + 2] - centre.z;
				d.push(Math.sqrt(dx * dx + dy * dy + dz * dz));
			}
			d.sort((p, q) => p - q);
			const coreRadius = d[Math.floor(d.length * 0.9)] || 1;
			const size = coreRadius * 2;
			g.translate(-centre.x, -centre.y, -centre.z);

			// Real-world frame: the API serves metres east / north / up (GPS-aligned), so tell
			// three.js that Z is up. Without this the scene renders on its side and nothing
			// about it is judgeable — the single biggest reason the old view was unreadable.
			THREE.Object3D.DEFAULT_UP.set(0, 0, 1);

			// Ground height. The low tail of z over the WHOLE cloud is wrong wherever the
			// scene has relief: at Prosek the 5th percentile is the valley floor 13 m below
			// the clifftop the camera stood on, so the grid — and the map drawn on it —
			// floated. Estimate the floor UNDER THE CAMERAS instead: points within 3 m in
			// plan of some camera and 0.3–4 m below it, low quartile. Fall back to the
			// global tail when the cloud has nothing beneath the cameras.
			const camPos = await loadCameraPositions();
			const zsSorted = [...zs].sort((p, q) => p - q);
			groundZ = zsSorted[Math.floor(zsSorted.length * 0.05)] - centre.z;
			if (camPos.length) {
				const floor: number[] = [];
				for (let i = 0; i < nAll; i += Math.max(1, Math.floor(nAll / 60000))) {
					const x = posArr[i * 3], y = posArr[i * 3 + 1], z = posArr[i * 3 + 2];
					for (const c of camPos) {
						const dx = x - (c[0] - centre.x), dy = y - (c[1] - centre.y);
						const dz = z - (c[2] - centre.z);
						if (dx * dx + dy * dy < 9 && dz < -0.3 && dz > -4) {
							floor.push(z);
							break;
						}
					}
				}
				if (floor.length > 200) {
					floor.sort((p, q) => p - q);
					groundZ = floor[Math.floor(floor.length * 0.25)];
					camHeight = Math.round((camPos[0][2] - centre.z - groundZ) * 100) / 100;
				}
			}
			extentM = Math.round(coreRadius * 2);

			// Point size that makes the cloud read as a SURFACE rather than a spray: the
			// gaps have to close, so size the sprite to the actual spacing between points
			// instead of to the scene. Median nearest-neighbour distance over a sample,
			// found with a grid hash (a full kd-tree is not worth it for a slider default).
			spacing = medianSpacing(posArr, nAll);
			if (spacing > 0) pointSize = 1.0;
			coreScale = size;
			cloud = new THREE.Points(
				g,
				new THREE.PointsMaterial({
					size: pointWorldSize(),
					vertexColors: true,
					sizeAttenuation: true,
					// round sprites, cut with alphaTest rather than blending, so they still
					// write depth and occlude each other: square points read as a mosaic of
					// tiles, round ones read as a surface
					map: discSprite(THREE),
					alphaTest: 0.5,
					transparent: false
				})
			);
			scene.add(cloud);

			if (showGround) {
				// 5 m squares, a heavier line every 25 m: a grid is only useful if you can
				// count it, and counting needs a unit.
				// capped: the grid costs a vertex per division, so an outlier-driven radius
				// must not be allowed to ask for millions of them
				const span = Math.min(4000, Math.max(20, Math.ceil((coreRadius * 2.4) / 25) * 25));
				const grid = new THREE.GridHelper(span, span / 5, 0x3a5a86, 0x24303f);
				grid.rotation.x = Math.PI / 2; // GridHelper is XZ; we want XY with Z up
				grid.position.set(0, 0, groundZ);
				scene.add(grid);
				const coarse = new THREE.GridHelper(span, span / 25, 0x4d7ab5, 0x4d7ab5);
				coarse.rotation.x = Math.PI / 2;
				coarse.position.set(0, 0, groundZ + 0.01);
				scene.add(coarse);
				// north marker: +Y is north in ENU
				const nlen = span / 2;
				const ng = new THREE.BufferGeometry().setAttribute(
					'position',
					new THREE.BufferAttribute(
						new Float32Array([
							0, 0, groundZ, 0, nlen, groundZ,
							-nlen * 0.04, nlen * 0.92, groundZ, 0, nlen, groundZ,
							nlen * 0.04, nlen * 0.92, groundZ, 0, nlen, groundZ
						]),
						3
					)
				);
				scene.add(new THREE.LineSegments(ng, new THREE.LineBasicMaterial({ color: 0x8fb8ef })));
			}

			// Layers are attached and detached in place, never by remounting the viewer:
			// a rebuild would throw away the orbit camera, and losing your viewpoint every
			// time you tick a checkbox makes the toggles useless for comparing.
			sceneOffset = centre.clone().negate();
			sceneSize = size;
			if (showCameras) await syncCameras();
			if (showMap) syncMap();

			const w = el.clientWidth || 800;
			const h = el.clientHeight || 480;
			const fov = 55;
			// Far plane must clear the map, not just the cloud: a subject-scale dense cloud
			// is metres across while the OSM layer reaches 300 m, and a far plane fitted to
			// the cloud clips the whole map out of existence.
			camera = new THREE.PerspectiveCamera(fov, w / h, size / 5000, Math.max(size * 20, 1500));
			// Frame the whole cloud rather than guessing a distance: a walk cloud is long and
			// thin, so a fraction-of-diagonal guess leaves it small and clipped. Fit the
			// bounding sphere to the vertical FOV, backed off slightly, viewed obliquely so
			// the structure reads as 3-D on first paint.
			const dist = (coreRadius / Math.sin((fov / 2) * (Math.PI / 180))) * 1.15;
			// 2.5 px at the framing distance, so the slider has room in both directions
			const dbh = (el.clientHeight || 480) * Math.min(devicePixelRatio, 2);
			minWorldSize = (2.5 * dist * 2 * Math.tan((fov / 2) * (Math.PI / 180))) / dbh;
			camera.up.set(0, 0, 1);
			// looking north-east and downwards ~35 degrees: an aerial-oblique reads as a
			// place, where a level view reads as a smear
			camera.position.set(-dist * 0.55, -dist * 0.55, dist * 0.62);
			camera.lookAt(0, 0, groundZ);
			renderer = new THREE.WebGLRenderer({ antialias: true });
			renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
			renderer.setSize(w, h);
			el.appendChild(renderer.domElement);

			controls = new OrbitControls(camera, renderer.domElement);
			controls.enableDamping = true;
			controls.target.set(0, 0, groundZ);
			controls.update();

			edlPass = makeEdl(THREE, w, h);
			vel = new THREE.Vector3();
			const tick = () => {
				raf = requestAnimationFrame(tick);
				const now = performance.now();
				const dt = Math.min(0.1, (now - (lastT || now)) / 1000);
				lastT = now;
				if (mode === 'fly') flyStep(THREE, dt);
				else controls.update();
				if (edl && edlPass) {
					edlPass.material.uniforms.uStrength.value = edlStrength;
					edlPass.material.uniforms.uNear.value = camera.near;
					edlPass.material.uniforms.uFar.value = camera.far;
					renderer.setRenderTarget(edlPass.target);
					renderer.clear();
					renderer.render(scene, camera);
					renderer.setRenderTarget(null);
					renderer.render(edlPass.quadScene, edlPass.quadCam);
				} else {
					renderer.setRenderTarget(null);
					renderer.render(scene, camera);
				}
			};
			tick();
			setPointSize();
			mounted = true;
			status = '';

			renderer.domElement.addEventListener('click', onStageClick);
			renderer.domElement.addEventListener('mousemove', onLook);
			renderer.domElement.addEventListener('wheel', onWheel, { passive: false });
			document.addEventListener('pointerlockchange', onLockChange);
			window.addEventListener('keydown', onKeyDown);
			window.addEventListener('keyup', onKeyUp);

			ro = new ResizeObserver(() => {
				if (!renderer) return;
				const cw = el.clientWidth || 800;
				const ch = el.clientHeight || 480;
				camera.aspect = cw / ch;
				camera.updateProjectionMatrix();
				renderer.setSize(cw, ch);
				if (edlPass) {
					const dpr = renderer.getPixelRatio();
					edlPass.target.setSize(cw * dpr, ch * dpr);
					edlPass.material.uniforms.uTexel.value.set(1 / (cw * dpr), 1 / (ch * dpr));
				}
			});
			ro.observe(el);
		} catch (e) {
			status = `viewer failed: ${e instanceof Error ? e.message : String(e)}`;
		}
	});

	$effect(() => {
		// same trap as below: `cloud` is null on the first run, so pointSize must be read
		// unconditionally or the effect never subscribes to it
		void pointSize;
		if (cloud && three) setPointSize();
	});

	$effect(() => {
		void showPhotos;
		void showCameras;
		if (mounted) syncCameras();
	});

	$effect(() => {
		void showMap;
		if (mounted) syncMap();
	});

	// NB: read the reactive value BEFORE the loop. Both of these lists are empty on the
	// effect's first run (the cameras load asynchronously), so a read that only happens
	// inside the loop body is never tracked and the slider silently does nothing.
	$effect(() => {
		const k = camScale;
		for (const c of camGroups) c.scale.setScalar((c.userData.unit || 1) * k);
	});

	$effect(() => {
		const o = photoOpacity;
		for (const m of photoMats) m.opacity = o;
	});

	onDestroy(() => {
		disposed = true;
		document.removeEventListener('pointerlockchange', onLockChange);
		window.removeEventListener('keydown', onKeyDown);
		window.removeEventListener('keyup', onKeyUp);
		if (document.pointerLockElement) document.exitPointerLock?.();
		ro?.disconnect();
		cancelAnimationFrame(raf);
		controls?.dispose?.();
		cloud?.geometry?.dispose?.();
		cloud?.material?.dispose?.();
		for (const m of photoMats) {
			m.map?.dispose?.();
			m.dispose?.();
		}
		photoMats = [];
		camGroups = [];
		edlPass?.target?.dispose?.();
		edlPass?.material?.dispose?.();
		renderer?.dispose?.();
		renderer?.domElement?.remove();
	});
</script>

<div class="wrap">
	<div class="stage" class:flying={mode === 'fly'} bind:this={el} data-testid="recon-cloud" data-mode={mode}></div>
	<div class="hud">
		{#if status}
			<span class="muted">{status}</span>
		{:else}
			<span class="muted">{nPoints.toLocaleString()} points{dense ? ' (dense)' : ''}</span>
			<span class="muted">~{extentM} m across · grid 5 m · ↑ north · Z up</span>
			<label title="point diameter; the number is what it works out to on screen right now">
				points
				<input type="range" min="0.3" max="6" step="0.1" bind:value={pointSize} />
				{#if pointPx}<span class="muted small">{pointPx} px</span>{/if}
			</label>
			<label title="frustum length; with photos on, this is how big the photographs hang">
				cameras
				<input type="range" min="0.2" max="8" step="0.1" bind:value={camScale} />
			</label>
			{#if showPhotos}
				<label title="photo opacity">
					photo
					<input type="range" min="0.1" max="1" step="0.05" bind:value={photoOpacity} />
					<span class="muted small">{nPhotosLoaded} loaded</span>
				</label>
			{/if}
			<label title="eye-dome lighting: shades the cloud by depth discontinuity, so it reads as a surface instead of a spray">
				<input type="checkbox" bind:checked={edl} /> solid
			</label>
			{#if edl}
				<input
					type="range"
					min="0.2"
					max="3"
					step="0.1"
					bind:value={edlStrength}
					title="shading strength"
				/>
			{/if}
			{#if camHeight}
				<span class="muted" title="camera above the floor beneath it — a phone is held at 1.4-1.7 m, so this is also a scale check">
					camera {camHeight} m above ground
				</span>
			{/if}
			{#if nBuildings}
				<span class="muted">{nBuildings} OSM buildings</span>
			{/if}
			{#if mapNote}
				<span class="muted small">{mapNote}</span>
			{/if}
			<span class="seg">
				<button class:on={mode === 'orbit'} onclick={() => setMode('orbit')}
					data-testid="recon-mode-orbit">orbit</button
				>
				<button class:on={mode === 'fly'} onclick={() => setMode('fly')}
					title="Descent-style: click the view to grab the mouse, WASD + R/F to move, Q/E roll, L to level, scroll for speed, Esc to release"
					data-testid="recon-mode-fly">fly</button
				>
			</span>
			{#if mode === 'fly'}
				<span class="muted small" data-testid="recon-fly-hint">
					{locked
						? `WASD move · R/F up/down · Q/E roll · L level · scroll speed ×${flySpeed.toFixed(2)} · Esc to release`
						: 'click the view to take the controls'}
				</span>
			{:else}
				<span class="muted small"
					>drag to orbit · scroll to zoom · blue = cameras · orange = map</span
				>
			{/if}
		{/if}
	</div>
</div>

<style>
	.wrap {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.stage.flying {
		cursor: crosshair;
	}
	.stage {
		width: 100%;
		height: 460px;
		border-radius: 6px;
		overflow: hidden;
		background: #0d0d0d;
	}
	.hud {
		display: flex;
		align-items: center;
		gap: 14px;
		font-size: 12px;
		flex-wrap: wrap;
	}
	.hud label {
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}
	.small {
		font-size: 11px;
	}
</style>

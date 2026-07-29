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
		showCameras = true
	}: { runId: string; dense?: boolean; maxPoints?: number; showCameras?: boolean } = $props();

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

	async function loadCloud(THREE: typeof import('three')) {
		const url =
			`${apiBase}/recon/runs/${runId}/cloud.bin?max_points=${maxPoints}` +
			(dense ? '&dense=true' : '');
		const buf = await (await fetch(url)).arrayBuffer();
		const stride = 15; // 3*float32 + 3*uint8
		const n = Math.floor(buf.byteLength / stride);
		nPoints = n;
		const dv = new DataView(buf);
		const pos = new Float32Array(n * 3);
		const col = new Float32Array(n * 3);
		for (let i = 0; i < n; i++) {
			const o = i * stride;
			pos[i * 3] = dv.getFloat32(o, true);
			pos[i * 3 + 1] = dv.getFloat32(o + 4, true);
			pos[i * 3 + 2] = dv.getFloat32(o + 8, true);
			col[i * 3] = dv.getUint8(o + 12) / 255;
			col[i * 3 + 1] = dv.getUint8(o + 13) / 255;
			col[i * 3 + 2] = dv.getUint8(o + 14) / 255;
		}
		const g = new THREE.BufferGeometry();
		g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
		g.setAttribute('color', new THREE.BufferAttribute(col, 3));
		g.computeBoundingBox();
		return g;
	}

	async function loadCameras(THREE: typeof import('three'), size: number) {
		const r = await fetch(`${apiBase}/recon/runs/${runId}/cameras`);
		if (!r.ok) return null;
		const d = await r.json();
		const group = new THREE.Group();
		const s = size * 0.02;
		for (const f of d.frames) {
			const m = new THREE.Matrix4();
			// pose is row-major cam2world; three wants column-major
			const p = f.pose;
			m.set(
				p[0][0], p[0][1], p[0][2], p[0][3],
				p[1][0], p[1][1], p[1][2], p[1][3],
				p[2][0], p[2][1], p[2][2], p[2][3],
				0, 0, 0, 1
			);
			// a small pyramid along +z (camera looks down +z in this convention)
			const g = new THREE.BufferGeometry();
			const w = s * 0.7;
			const v = new Float32Array([
				0, 0, 0, -w, -w, s, 0, 0, 0, w, -w, s, 0, 0, 0, w, w, s, 0, 0, 0, -w, w, s,
				-w, -w, s, w, -w, s, w, -w, s, w, w, s, w, w, s, -w, w, s, -w, w, s, -w, -w, s
			]);
			g.setAttribute('position', new THREE.BufferAttribute(v, 3));
			const line = new THREE.LineSegments(
				g,
				new THREE.LineBasicMaterial({ color: f.injected ? 0xe0a23a : 0x3987e5 })
			);
			line.applyMatrix4(m);
			group.add(line);
		}
		return group;
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

			coreScale = size;
			cloud = new THREE.Points(
				g,
				new THREE.PointsMaterial({
					size: (size / 900) * pointSize,
					vertexColors: true,
					sizeAttenuation: true
				})
			);
			scene.add(cloud);

			if (showCameras) {
				const cams = await loadCameras(THREE, size);
				if (cams) {
					cams.position.set(-centre.x, -centre.y, -centre.z);
					scene.add(cams);
				}
			}

			const w = el.clientWidth || 800;
			const h = el.clientHeight || 480;
			const fov = 55;
			camera = new THREE.PerspectiveCamera(fov, w / h, size / 5000, size * 20);
			// Frame the whole cloud rather than guessing a distance: a walk cloud is long and
			// thin, so a fraction-of-diagonal guess leaves it small and clipped. Fit the
			// bounding sphere to the vertical FOV, backed off slightly, viewed obliquely so
			// the structure reads as 3-D on first paint.
			const dist = (coreRadius / Math.sin((fov / 2) * (Math.PI / 180))) * 1.1;
			camera.position.set(dist * 0.45, -dist * 0.55, dist * 0.7);
			camera.lookAt(0, 0, 0);
			renderer = new THREE.WebGLRenderer({ antialias: true });
			renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
			renderer.setSize(w, h);
			el.appendChild(renderer.domElement);

			controls = new OrbitControls(camera, renderer.domElement);
			controls.enableDamping = true;
			controls.target.set(0, 0, 0);
			controls.update();

			const tick = () => {
				raf = requestAnimationFrame(tick);
				controls.update();
				renderer.render(scene, camera);
			};
			tick();
			status = '';

			ro = new ResizeObserver(() => {
				if (!renderer) return;
				const cw = el.clientWidth || 800;
				const ch = el.clientHeight || 480;
				camera.aspect = cw / ch;
				camera.updateProjectionMatrix();
				renderer.setSize(cw, ch);
			});
			ro.observe(el);
		} catch (e) {
			status = `viewer failed: ${e instanceof Error ? e.message : String(e)}`;
		}
	});

	$effect(() => {
		if (cloud && three) cloud.material.size = (coreScale / 900) * pointSize;
	});

	onDestroy(() => {
		disposed = true;
		ro?.disconnect();
		cancelAnimationFrame(raf);
		controls?.dispose?.();
		cloud?.geometry?.dispose?.();
		cloud?.material?.dispose?.();
		renderer?.dispose?.();
		renderer?.domElement?.remove();
	});
</script>

<div class="wrap">
	<div class="stage" bind:this={el} data-testid="recon-cloud"></div>
	<div class="hud">
		{#if status}
			<span class="muted">{status}</span>
		{:else}
			<span class="muted">{nPoints.toLocaleString()} points{dense ? ' (dense)' : ''}</span>
			<label>
				size
				<input type="range" min="0.2" max="4" step="0.1" bind:value={pointSize} />
			</label>
			<span class="muted small">drag to orbit · scroll to zoom · blue = cameras</span>
		{/if}
	</div>
</div>

<style>
	.wrap {
		display: flex;
		flex-direction: column;
		gap: 6px;
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

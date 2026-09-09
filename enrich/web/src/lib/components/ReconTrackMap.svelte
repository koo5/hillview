<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { html } from '$lib/html';
	import 'leaflet/dist/leaflet.css';

	// GPS track vs the Umeyama-aligned recovered camera track for one reconstruction.
	// Thin connectors join each GPS fix to its recovered camera, so the residual is a
	// visible length rather than a number — a collapsed solve (walk_sparse) shows as a
	// clump with long connectors fanning out.
	type Frame = {
		idx: number;
		gps: [number, number] | null;
		recovered_gps: [number, number] | null;
		captured_at?: string | null;
	};
	let {
		frames = [],
		residuals = {},
		selected = null,
		onselect
	}: {
		frames?: Frame[];
		// idx -> per-frame reprojection error (px), for the tooltip
		residuals?: Record<number, { residual_m?: number | null; reproj_px?: number | null }>;
		selected?: number | null;
		onselect?: (idx: number) => void;
	} = $props();

	let el: HTMLDivElement;
	let wrap: HTMLDivElement;
	let full = $state(false);
	// only the FIRST render frames the track; later ones (a selection change, a hover)
	// must leave the user's pan and zoom alone
	let fitOnRender = true;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let map: any = null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let L: any = null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let layer: any = null;

	// Per-frame handles, so hovering can highlight ONE link without redrawing the layer:
	// a re-render on every mouse move would re-fit the bounds and fight the user's pan.
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let links: Record<number, any> = {};
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let recDots: Record<number, any> = {};
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let gpsDots: Record<number, any> = {};
	let hovered = $state<number | null>(null);

	const LINK = { color: '#8b93a1', weight: 1, opacity: 0.5 };
	const LINK_HI = { color: '#e0a23a', weight: 3, opacity: 1 };

	function paintHighlight() {
		for (const [k, ln] of Object.entries(links)) {
			const on = Number(k) === hovered || Number(k) === selected;
			ln.setStyle(on ? LINK_HI : LINK);
			if (on) ln.bringToFront();
		}
		for (const [k, m] of Object.entries(recDots)) {
			const i = Number(k);
			const sel = i === selected;
			const hov = i === hovered;
			m.setStyle({ color: sel ? '#e0a23a' : hov ? '#ffd479' : '#3987e5' });
			m.setRadius(sel ? 8 : hov ? 7 : 5);
		}
		for (const [k, m] of Object.entries(gpsDots)) {
			const on = Number(k) === hovered || Number(k) === selected;
			m.setStyle({ color: on ? '#e0a23a' : '#8b93a1' });
			m.setRadius(on ? 5 : 3);
		}
	}

	function render() {
		if (!map || !L) return;
		if (layer) layer.remove();
		layer = L.layerGroup().addTo(map);
		links = {};
		recDots = {};
		gpsDots = {};
		const pts: [number, number][] = [];
		const gpsLine: [number, number][] = [];
		const recLine: [number, number][] = [];

		for (const f of frames) {
			if (f.gps) gpsLine.push([f.gps[0], f.gps[1]]);
			if (f.recovered_gps) recLine.push([f.recovered_gps[0], f.recovered_gps[1]]);
			if (f.gps && f.recovered_gps) {
				links[f.idx] = L.polyline([f.gps, f.recovered_gps], LINK).addTo(layer);
			}
		}
		if (gpsLine.length > 1)
			L.polyline(gpsLine, { color: '#8b93a1', weight: 2, opacity: 0.7 }).addTo(layer);
		if (recLine.length > 1)
			L.polyline(recLine, { color: '#3987e5', weight: 2, opacity: 0.9 }).addTo(layer);

		for (const f of frames) {
			if (f.gps) {
				gpsDots[f.idx] = L.circleMarker(f.gps, {
					radius: 3,
					color: '#8b93a1',
					weight: 1,
					fillOpacity: 0.7
				}).addTo(layer);
				pts.push(f.gps);
			}
			if (f.recovered_gps) {
				const r = residuals[f.idx] ?? {};
				const m = L.circleMarker(f.recovered_gps, {
					radius: 5,
					color: '#3987e5',
					weight: 2,
					fillOpacity: 0.85
				})
					.bindTooltip(
						html`frame ${f.idx}` +
							(r.residual_m != null ? html`<br>GPS residual ${r.residual_m} m` : '') +
							(r.reproj_px != null ? html`<br>reprojection ${r.reproj_px} px` : '')
					)
					.addTo(layer);
				m.on('click', () => onselect?.(f.idx));
				m.on('mouseover', () => {
					hovered = f.idx;
					paintHighlight();
				});
				m.on('mouseout', () => {
					hovered = null;
					paintHighlight();
				});
				recDots[f.idx] = m;
				pts.push(f.recovered_gps);
			}
		}
		paintHighlight();
		if (pts.length && fitOnRender) map.fitBounds(pts, { padding: [30, 30], maxZoom: 18 });
		fitOnRender = false;
	}

	onMount(async () => {
		L = (await import('leaflet')).default;
		map = L.map(el, { zoomControl: true });
		L.tileLayer('https://tiles4.ueueeu.eu/tile/{z}/{x}/{y}.png', {
			maxZoom: 23,
			maxNativeZoom: 20,
			attribution: '© OpenStreetMap contributors'
		}).addTo(map);
		render();
	});
	onDestroy(() => map?.remove());

	$effect(() => {
		// re-render on a frame change; a selection change only repaints, so the map does
		// not jump when a frame is picked from the table
		frames;
		render();
	});

	$effect(() => {
		selected;
		paintHighlight();
	});

	$effect(() => {
		// leaflet measures its container once; after a size change it needs telling
		if (full !== undefined && map) setTimeout(() => map.invalidateSize(), 60);
	});

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && full) full = false;
	}
</script>

<svelte:window on:keydown={onKey} />

<div class="wrap" class:full bind:this={wrap}>
	<div class="map" bind:this={el}></div>
	<button
		class="expand"
		onclick={() => (full = !full)}
		title={full ? 'exit fullscreen (Esc)' : 'fullscreen'}
		data-testid="recon-track-expand">{full ? '\u2715' : '\u26f6'}</button
	>
	{#if hovered != null}
		<div class="hoverbox">
			frame {hovered}{#if residuals[hovered]?.residual_m != null}
				· GPS residual {residuals[hovered].residual_m} m{/if}{#if residuals[hovered]?.reproj_px != null}
				· reprojection {residuals[hovered].reproj_px} px{/if}
		</div>
	{/if}
</div>

<style>
	.wrap {
		position: relative;
	}
	.map {
		width: 100%;
		height: 360px;
		border-radius: 6px;
		overflow: hidden;
	}
	.wrap.full {
		position: fixed;
		inset: 0;
		z-index: 4000;
		background: #0d0d0d;
		padding: 0;
	}
	.wrap.full .map {
		height: 100vh;
		border-radius: 0;
	}
	.expand {
		position: absolute;
		top: 8px;
		right: 8px;
		z-index: 1000;
		width: 30px;
		height: 30px;
		font-size: 15px;
		line-height: 1;
		cursor: pointer;
		border-radius: 4px;
	}
	.hoverbox {
		position: absolute;
		left: 8px;
		bottom: 8px;
		z-index: 1000;
		padding: 3px 8px;
		border-radius: 4px;
		font-size: 12px;
		background: rgba(20, 22, 28, 0.85);
		color: #e8e8e8;
		pointer-events: none;
	}
</style>

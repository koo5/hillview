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
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let map: any = null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let L: any = null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let layer: any = null;

	function render() {
		if (!map || !L) return;
		if (layer) layer.remove();
		layer = L.layerGroup().addTo(map);
		const pts: [number, number][] = [];
		const gpsLine: [number, number][] = [];
		const recLine: [number, number][] = [];

		for (const f of frames) {
			if (f.gps) gpsLine.push([f.gps[0], f.gps[1]]);
			if (f.recovered_gps) recLine.push([f.recovered_gps[0], f.recovered_gps[1]]);
			if (f.gps && f.recovered_gps) {
				L.polyline([f.gps, f.recovered_gps], {
					color: '#8b93a1',
					weight: 1,
					opacity: 0.5
				}).addTo(layer);
			}
		}
		if (gpsLine.length > 1)
			L.polyline(gpsLine, { color: '#8b93a1', weight: 2, opacity: 0.7 }).addTo(layer);
		if (recLine.length > 1)
			L.polyline(recLine, { color: '#3987e5', weight: 2, opacity: 0.9 }).addTo(layer);

		for (const f of frames) {
			if (f.gps) {
				L.circleMarker(f.gps, {
					radius: 3,
					color: '#8b93a1',
					weight: 1,
					fillOpacity: 0.7
				}).addTo(layer);
				pts.push(f.gps);
			}
			if (f.recovered_gps) {
				const sel = f.idx === selected;
				const r = residuals[f.idx] ?? {};
				const m = L.circleMarker(f.recovered_gps, {
					radius: sel ? 8 : 5,
					color: sel ? '#e0a23a' : '#3987e5',
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
				pts.push(f.recovered_gps);
			}
		}
		if (pts.length) map.fitBounds(pts, { padding: [30, 30], maxZoom: 18 });
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
		// re-render on frame/selection change (reads them so the effect tracks)
		frames;
		selected;
		render();
	});
</script>

<div class="map" bind:this={el}></div>

<style>
	.map {
		width: 100%;
		height: 360px;
		border-radius: 6px;
		overflow: hidden;
	}
</style>

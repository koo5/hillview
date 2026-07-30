<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import type { Candidate, CandidatePhoto, Wedge } from '$lib/types';
	import 'leaflet/dist/leaflet.css';

	let {
		photo,
		candidates,
		target = null,
		wedge = null,
		annotationPie = null,
		selected = null,
		onselect,
		onmapclick,
		fit = true,
		onviewport
	}: {
		photo: CandidatePhoto;
		candidates: Candidate[];
		target?: { lat: number; lon: number; label?: string } | null;
		// sight-ray wedge (ray-mode matching), drawn as an amber sector
		wedge?: Wedge | null;
		// the single annotation's exact rect slice (violet, from the photo)
		annotationPie?: { bearing: number; half: number; radius_m: number } | null;
		selected?: string | null;
		onselect?: (candidate: string) => void;
		// background-click → (lat, lon); marker clicks don't fire this
		onmapclick?: (lat: number, lon: number) => void;
		// auto-fit the view to the candidates on render (off for map-area mode,
		// where the user's pan/zoom defines the query)
		fit?: boolean;
		// current viewport bounds, emitted on moveend (map-area candidate mode)
		onviewport?: (b: { minlon: number; minlat: number; maxlon: number; maxlat: number }) => void;
	} = $props();

	// destination point along a bearing (spherical earth) — for sector polygons
	function dest(lat: number, lon: number, brg: number, m: number): [number, number] {
		const R = 6371000;
		const d = m / R;
		const p1 = (lat * Math.PI) / 180;
		const b = (brg * Math.PI) / 180;
		const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
		const l2 =
			(lon * Math.PI) / 180 +
			Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
		return [(p2 * 180) / Math.PI, ((((l2 * 180) / Math.PI + 540) % 360) - 180)];
	}

	function sectorLatLngs(
		lat: number,
		lon: number,
		azimuth: number,
		half: number,
		nearM: number,
		farM: number
	): [number, number][] {
		const pts: [number, number][] = [];
		const steps = 24;
		for (let i = 0; i <= steps; i++) {
			pts.push(dest(lat, lon, azimuth - half + (2 * half * i) / steps, farM));
		}
		if (nearM > 1) {
			for (let i = steps; i >= 0; i--) {
				pts.push(dest(lat, lon, azimuth - half + (2 * half * i) / steps, nearM));
			}
		} else {
			pts.push([lat, lon]);
		}
		return pts;
	}

	let el: HTMLDivElement;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let map: any = null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let L: any = null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let layer: any = null;

	const COLORS: Record<string, string> = {
		proposed: '#8b93a1',
		approved: '#46c281',
		rejected: '#e0603a'
	};

	function render() {
		if (!map || !L) return;
		if (layer) layer.remove();
		layer = L.layerGroup().addTo(map);
		const pts: [number, number][] = [];

		if (photo.lat != null && photo.lon != null) {
			L.circleMarker([photo.lat, photo.lon], {
				radius: 7,
				color: '#6ca4ff',
				fillOpacity: 0.9
			})
				.bindTooltip('photo')
				.addTo(layer);
			pts.push([photo.lat, photo.lon]);
			if (photo.bearing != null) {
				// bearing ray, ~2km
				const rad = (photo.bearing * Math.PI) / 180;
				const dlat = (2 / 110.54) * Math.cos(rad);
				const dlon = ((2 / 111.32) * Math.sin(rad)) / Math.cos((photo.lat * Math.PI) / 180);
				L.polyline(
					[
						[photo.lat, photo.lon],
						[photo.lat + dlat, photo.lon + dlon]
					],
					{ color: '#6ca4ff', weight: 2, dashArray: '6 6' }
				).addTo(layer);
			}
		}

		if (target) {
			L.circleMarker([target.lat, target.lon], {
				radius: 9,
				color: '#e0a23a',
				weight: 3,
				fillOpacity: 0.5
			})
				.bindTooltip(target.label ?? 'target')
				.addTo(layer);
			pts.push([target.lat, target.lon]);
		}

		// the ORIGIN photo's own view pie (calibrated FOV when available) —
		// dashed outline, same blue as its marker
		if (photo.pie && photo.lat != null && photo.lon != null) {
			L.polygon(
				sectorLatLngs(photo.lat, photo.lon, photo.pie.bearing, photo.pie.half, 0, photo.pie.radius_m),
				{
					color: '#6ca4ff',
					weight: 1,
					dashArray: '4 4',
					fillColor: '#6ca4ff',
					fillOpacity: 0.05,
					interactive: false
				}
			).addTo(layer);
		}

		if (wedge) {
			L.polygon(sectorLatLngs(wedge.lat, wedge.lon, wedge.azimuth, wedge.half, wedge.near_m, wedge.far_m), {
				color: '#e0a23a',
				weight: 1,
				fillColor: '#e0a23a',
				fillOpacity: 0.1,
				interactive: false
			}).addTo(layer);
			// keep the wedge direction visible without zooming out to its far edge
			pts.push(dest(wedge.lat, wedge.lon, wedge.azimuth, Math.min(wedge.far_m, 3000)));
		}

		// the annotation's exact rect slice — the measurement, vs the wedge's
		// padded search region
		if (annotationPie && photo.lat != null && photo.lon != null) {
			L.polygon(
				sectorLatLngs(photo.lat, photo.lon, annotationPie.bearing, annotationPie.half, 0, annotationPie.radius_m),
				{
					color: '#b48cff',
					weight: 1.5,
					fillColor: '#b48cff',
					fillOpacity: 0.14,
					interactive: false
				}
			).addTo(layer);
			// sight-line rects (w ≈ 0) collapse the sector to a hairline —
			// the solid center ray keeps the assumed direction visible
			L.polyline(
				[
					[photo.lat, photo.lon],
					dest(photo.lat, photo.lon, annotationPie.bearing, annotationPie.radius_m)
				],
				{ color: '#b48cff', weight: 2, opacity: 0.75, interactive: false }
			).addTo(layer);
			pts.push(dest(photo.lat, photo.lon, annotationPie.bearing, Math.min(annotationPie.radius_m, 3000)));
		}

		// the selected candidate's own view pie — shows WHY it does/doesn't see;
		// colored like its status marker
		const selCand = selected ? candidates.find((c) => c.candidate === selected) : null;
		if (selCand?.pie && selCand.lat != null && selCand.lon != null && selCand.pie.bearing != null) {
			const pieColor = COLORS[selCand.status] ?? COLORS.proposed;
			L.polygon(
				sectorLatLngs(selCand.lat, selCand.lon, selCand.pie.bearing, selCand.pie.half, 0, selCand.pie.radius_m),
				{
					color: pieColor,
					weight: 1,
					fillColor: pieColor,
					fillOpacity: 0.09,
					interactive: false
				}
			).addTo(layer);
		}

		for (const c of candidates) {
			if (c.lat == null || c.lon == null) continue;
			const m = L.circleMarker([c.lat, c.lon], {
				radius: c.candidate === selected ? 10 : 7,
				color: COLORS[c.status] ?? COLORS.proposed,
				weight: c.candidate === selected ? 3 : 2,
				fillOpacity: 0.7,
				bubblingMouseEvents: false
			})
				.bindTooltip(
					`${c.displayName ?? c.candidate}<br>${c.km ?? '?'} km · Δ${c.bearing_offset ?? '?'}°`
				)
				.addTo(layer);
			m.on('click', () => onselect?.(c.candidate));
			pts.push([c.lat, c.lon]);
		}
		if (fit && pts.length) map.fitBounds(pts, { padding: [30, 30], maxZoom: 15 });
	}

	function emitViewport() {
		if (!map || !onviewport) return;
		const b = map.getBounds();
		onviewport({
			minlon: b.getWest(),
			minlat: b.getSouth(),
			maxlon: b.getEast(),
			maxlat: b.getNorth()
		});
	}

	onMount(async () => {
		L = (await import('leaflet')).default;
		map = L.map(el, { zoomControl: true });
		L.tileLayer('https://tiles4.ueueeu.eu/tile/{z}/{x}/{y}.png', {
			maxZoom: 23,
			maxNativeZoom: 20,
			attribution: '© OpenStreetMap contributors'
		}).addTo(map);
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		map.on('click', (e: any) => onmapclick?.(e.latlng.lat, e.latlng.lng));
		map.on('moveend', emitViewport);
		render();
		emitViewport(); // seed the page with the initial viewport
	});
	onDestroy(() => map?.remove());

	$effect(() => {
		void candidates;
		void selected;
		void target;
		void wedge;
		void annotationPie;
		render();
	});
</script>

<div bind:this={el} style="height:420px; border-radius:10px; border:1px solid var(--border)"></div>

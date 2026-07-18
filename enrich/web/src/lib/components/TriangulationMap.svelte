<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import 'leaflet/dist/leaflet.css';

	export interface TriRay {
		annotation_id: string;
		photo_id: string;
		lat: number;
		lon: number;
		azimuth: number;
		calibrated: boolean;
		forward_m?: number;
	}
	export interface TriFix {
		lat: number;
		lon: number;
		residual_m: number;
	}

	let {
		rays = [],
		fix = null,
		selected = null,
		onselect
	}: {
		rays: TriRay[];
		fix?: TriFix | null;
		selected?: string | null;
		onselect?: (annotation_id: string) => void;
	} = $props();

	// destination point along a bearing (spherical earth)
	function dest(lat: number, lon: number, brg: number, m: number): [number, number] {
		const R = 6371000;
		const d = m / R;
		const p1 = (lat * Math.PI) / 180;
		const b = (brg * Math.PI) / 180;
		const p2 = Math.asin(
			Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b)
		);
		const l2 =
			(lon * Math.PI) / 180 +
			Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
		return [(p2 * 180) / Math.PI, ((((l2 * 180) / Math.PI + 540) % 360) - 180)];
	}

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

		for (const r of rays) {
			if (r.lat == null || r.lon == null) continue;
			const sel = r.annotation_id === selected;
			const color = sel ? '#e0a23a' : r.calibrated ? '#46c281' : '#8b93a1';
			// ray: from the pano to the fix (if any) or a default distance
			const reach = fix
				? Math.max(500, (r.forward_m ?? 3000) * 1.05)
				: 8000;
			const end = dest(r.lat, r.lon, r.azimuth, reach);
			L.polyline([[r.lat, r.lon], end], {
				color,
				weight: sel ? 3 : 2,
				opacity: 0.8,
				dashArray: r.calibrated ? undefined : '6 6'
			}).addTo(layer);
			const m = L.circleMarker([r.lat, r.lon], {
				radius: sel ? 8 : 6,
				color,
				weight: 2,
				fillOpacity: 0.85
			})
				.bindTooltip(
					`${r.photo_id.slice(0, 8)}<br>az ${r.azimuth}°${r.calibrated ? ' (calibrated)' : ' (compass)'}`
				)
				.addTo(layer);
			m.on('click', () => onselect?.(r.annotation_id));
			pts.push([r.lat, r.lon]);
		}

		if (fix) {
			L.circleMarker([fix.lat, fix.lon], {
				radius: 10,
				color: '#b48cff',
				weight: 3,
				fillColor: '#b48cff',
				fillOpacity: 0.6
			})
				.bindTooltip(`triangulated POI<br>±${fix.residual_m} m residual`, { permanent: false })
				.addTo(layer);
			pts.push([fix.lat, fix.lon]);
		}

		if (pts.length) map.fitBounds(pts, { padding: [40, 40], maxZoom: 16 });
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
		void rays;
		void fix;
		void selected;
		render();
	});
</script>

<div bind:this={el} style="height:480px; border-radius:10px; border:1px solid var(--border)"></div>

<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import TriangulationMap, {
		type TriRay,
		type TriFix
	} from '$lib/components/TriangulationMap.svelte';

	interface PoiRow {
		poi_id: string;
		label: string | null;
		n_annotations: number;
	}
	interface PoiAnnotation {
		annotation_id: string;
		ray: (TriRay & { body?: string | null; photo_title?: string | null }) | null;
	}
	interface PoiDetail {
		poi_id: string;
		label: string | null;
		annotations: PoiAnnotation[];
		n_rays: number;
		triangulation: (TriFix & { rays: TriRay[] }) | null;
	}

	let pois = $state<PoiRow[]>([]);
	let detail = $state<PoiDetail | null>(null);
	let sel = $state<string | null>(null);
	let selRay = $state<string | null>(null);
	let err = $state<string | null>(null);

	async function loadList() {
		try {
			pois = (await api.get<{ pois: PoiRow[] }>('/pois')).pois;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
	}
	async function loadDetail(id: string) {
		sel = id;
		selRay = null;
		try {
			detail = await api.get<PoiDetail>(`/pois/${id}`);
			err = null;
		} catch (e) {
			detail = null;
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
	}
	function pick(id: string) {
		goto(`?poi=${id}`, { noScroll: true, keepFocus: true });
	}

	const rays = $derived((detail?.annotations ?? []).map((a) => a.ray).filter(Boolean) as TriRay[]);

	onMount(loadList);
	$effect(() => {
		const id = page.url.searchParams.get('poi');
		if (id && id !== sel) loadDetail(id);
	});
</script>

<h1>Triangulate</h1>
<p class="muted">
	A <b>POI</b> is the shared subject that several annotations depict. Relate the annotations to
	one POI (on each annotation's detail page), then their sight-rays are intersected here to
	estimate where it stands. <span style="color:#46c281">green</span> = calibrated ray ·
	<span style="color:#8b93a1">grey dashed</span> = compass-only (less certain) ·
	<span style="color:#b48cff">violet</span> = the triangulated point.
</p>

{#if err}<div class="card" style="border-color:var(--bad)">{err}</div>{/if}

<div class="row" style="align-items:flex-start; gap:18px">
	<div style="flex:0 0 300px">
		<table>
			<tbody>
				{#each pois as p (p.poi_id)}
					<tr
						style="cursor:pointer; {sel === p.poi_id ? 'background:var(--panel2)' : ''}"
						onclick={() => pick(p.poi_id)}
					>
						<td style="font-size:13px">{p.label ?? '(unnamed POI)'}</td>
						<td class="mono muted" style="font-size:11px; text-align:right">
							{p.n_annotations} ann
						</td>
					</tr>
				{/each}
				{#if !pois.length}
					<tr><td class="muted" style="font-size:12px">No POIs yet — create one from an annotation's detail page.</td></tr>
				{/if}
			</tbody>
		</table>
	</div>

	<div style="flex:1; min-width:480px">
		{#if detail}
			<div class="row" style="margin-bottom:6px; align-items:baseline">
				<b>{detail.label ?? '(unnamed POI)'}</b>
				<span class="muted" style="font-size:12px">
					{detail.n_rays} usable ray{detail.n_rays === 1 ? '' : 's'}
					{#if detail.triangulation}
						· fix <span class="mono">{detail.triangulation.lat.toFixed(5)}, {detail.triangulation.lon.toFixed(5)}</span>
						· residual ±{detail.triangulation.residual_m} m
						· <a href="https://hillview.cz/?lat={detail.triangulation.lat}&lon={detail.triangulation.lon}&zoom=18" target="_blank" rel="noreferrer">map ↗</a>
					{:else if detail.n_rays < 2}
						· need ≥2 rays to triangulate (relate another annotation)
					{/if}
				</span>
			</div>

			<TriangulationMap
				{rays}
				fix={detail.triangulation}
				selected={selRay}
				onselect={(id) => (selRay = id)}
			/>

			<table style="margin-top:10px">
				<thead><tr><th>annotation</th><th>pano</th><th>azimuth</th><th>fwd</th></tr></thead>
				<tbody>
					{#each detail.annotations as a (a.annotation_id)}
						<tr
							style={selRay === a.annotation_id ? 'background:var(--panel2)' : ''}
							onmouseenter={() => (selRay = a.annotation_id)}
						>
							<td>
								<a href="/annotations/{a.annotation_id}" class="mono" style="font-size:11px">{a.annotation_id.slice(0, 8)}</a>
								{#if a.ray?.body}<span class="muted" style="font-size:11px"> · {a.ray.body}</span>{/if}
							</td>
							<td>
								{#if a.ray}
									<a href="/photos/{a.ray.photo_id}" class="mono muted" style="font-size:11px">{a.ray.photo_id.slice(0, 8)}</a>
								{/if}
							</td>
							<td class="mono" style="font-size:12px">
								{#if a.ray}
									{a.ray.azimuth}° <span class="muted">{a.ray.calibrated ? 'cal' : 'compass'}</span>
								{:else}
									<span class="muted">no ray</span>
								{/if}
							</td>
							<td class="mono muted" style="font-size:11px">
								{a.ray && 'forward_m' in a.ray ? `${a.ray.forward_m} m` : ''}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
			{#if rays.some((r) => !r.calibrated)}
				<p class="muted" style="font-size:11px; margin-top:6px">
					⚠ some rays use compass + assumed FOV (no calibration) — calibrate those panos for a
					tighter fix.
				</p>
			{/if}
		{:else}
			<p class="muted">← pick a POI</p>
		{/if}
	</div>
</div>

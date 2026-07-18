<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import PhotoThumb from '$lib/components/PhotoThumb.svelte';

	interface PhotoRow {
		id: string;
		title: string | null;
		place_name: string | null;
		width: number | null;
		height: number | null;
		compass_angle: number | null;
		sizes: Record<string, { url?: string }> | null;
		uploaded_at: string | null;
		n_annotations: number;
		is_pano: boolean;
		calibrated: boolean;
	}
	interface PhotoList {
		total: number;
		page_size: number;
		photos: PhotoRow[];
	}

	let q = $state('');
	let pano = $state(false);
	let annotated = $state(false);
	let calibrated = $state(false);
	let pg = $state(1);
	let data = $state<PhotoList | null>(null);
	let err = $state<string | null>(null);

	async function load() {
		const p = new URLSearchParams({ page: String(pg) });
		if (q.trim()) p.set('q', q.trim());
		if (pano) p.set('pano', 'true');
		if (annotated) p.set('annotated', 'true');
		if (calibrated) p.set('calibrated', 'true');
		try {
			data = await api.get<PhotoList>(`/photos?${p}`);
			err = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
	}
	function refilter() {
		pg = 1;
		load();
	}
	const pages = $derived(data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1);

	onMount(load);
</script>

<h1>Photos</h1>
<p class="muted">
	The mirrored photo set, most-annotated first. Click through to a photo's record page —
	annotations, facts, protos, matches in one place.
</p>

{#if err}<div class="card" style="border-color:var(--bad)">{err}</div>{/if}

<div class="row" style="margin-bottom:10px">
	<input
		style="min-width:240px"
		placeholder="search title / place / id…"
		bind:value={q}
		onkeydown={(e) => e.key === 'Enter' && refilter()}
	/>
	<button onclick={refilter}>search</button>
	<label class="muted" style="font-size:12px">
		<input type="checkbox" bind:checked={pano} onchange={refilter} /> panos
	</label>
	<label class="muted" style="font-size:12px">
		<input type="checkbox" bind:checked={annotated} onchange={refilter} /> annotated
	</label>
	<label class="muted" style="font-size:12px">
		<input type="checkbox" bind:checked={calibrated} onchange={refilter} /> calibrated 🧭
	</label>
	<div style="flex:1"></div>
	<span class="muted" style="font-size:12px">{data?.total ?? '…'} photos</span>
</div>

<table>
	<thead><tr><th>photo</th><th>title / place</th><th>size</th><th>anns</th><th>uploaded</th></tr></thead>
	<tbody>
		{#each data?.photos ?? [] as p (p.id)}
			<tr>
				<td style="width:100px">
					<a href="/photos/{p.id}"><PhotoThumb sizes={p.sizes} size={90} /></a>
				</td>
				<td style="max-width:340px">
					<a href="/photos/{p.id}" style="font-size:13px">{p.title ?? p.id.slice(0, 8)}</a>
					<div class="muted" style="font-size:11px">
						<span class="mono">{p.id.slice(0, 8)}</span>
						{#if p.place_name}· {p.place_name}{/if}
						{#if p.compass_angle != null}· {Math.round(p.compass_angle)}°{/if}
					</div>
				</td>
				<td style="font-size:12px; white-space:nowrap">
					<span class="mono">{p.width}×{p.height}</span>
					{#if p.is_pano}<span class="pill" style="font-size:10px">pano</span>{/if}
					{#if p.calibrated}🧭{/if}
				</td>
				<td class="mono">{p.n_annotations || ''}</td>
				<td class="mono muted" style="font-size:11px">{p.uploaded_at ? String(p.uploaded_at).slice(0, 10) : ''}</td>
			</tr>
		{/each}
	</tbody>
</table>

<div class="row" style="margin-top:12px">
	<button disabled={pg <= 1} onclick={() => (pg--, load())}>‹ prev</button>
	<span class="muted">page {pg} of {pages}</span>
	<button disabled={pg >= pages} onclick={() => (pg++, load())}>next ›</button>
</div>

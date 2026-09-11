<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import Help from '$lib/components/Help.svelte';
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
		// latest terrain render state (done = depth artifact available) — null: none
		terrain: 'done' | 'queued' | 'rendering' | 'error' | null;
		// terrain overlay fit: approved (graduated / marked for export) | saved | null
		overlay: 'approved' | 'saved' | null;
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
	let terrain = $state(false);
	let overlay = $state(false);
	let pg = $state(1);
	let data = $state<PhotoList | null>(null);
	let err = $state<string | null>(null);

	// filter clicks in quick succession race their fetches (the unfiltered count
	// over the whole mirror is the slow one) — only the latest request may land
	let seq = 0;
	async function load() {
		const my = ++seq;
		const p = new URLSearchParams({ page: String(pg) });
		if (q.trim()) p.set('q', q.trim());
		if (pano) p.set('pano', 'true');
		if (annotated) p.set('annotated', 'true');
		if (calibrated) p.set('calibrated', 'true');
		if (terrain) p.set('terrain', 'true');
		if (overlay) p.set('overlay', 'true');
		try {
			const d = await api.get<PhotoList>(`/photos?${p}`);
			if (my !== seq) return;
			data = d;
			err = null;
		} catch (e) {
			if (my !== seq) return;
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

<div class="row" style="gap:8px">
	<h1>Photos</h1>
	<Help>
		<h4>what this page does</h4>
		<p>
			Browse the read-only mirror of Hillview's photo table (synced by append/reconcile —
			see the Dashboard). Everything else in the workbench hangs off a photo's record
			page: annotations, facts, calibration, matching, transfer.
		</p>
		<h4>filters</h4>
		<dl>
			<dt>search</dt>
			<dd>title / place / id substring</dd>
			<dt>panos</dt>
			<dd>aspect ratio ≥ 2 only</dd>
			<dt>annotated</dt>
			<dd>has at least one current annotation</dd>
			<dt>calibrated 🧭</dt>
			<dd>carries accepted calibration facts (see the Calibration bench)</dd>
			<dt>terrain ⛰</dt>
			<dd>has a finished terrain render with a depth artifact (Terrain bench)</dd>
			<dt>overlay</dt>
			<dd>has a saved terrain-overlay fit; <i>approved</i> = graduated / marked for export</dd>
		</dl>
		<h4>columns</h4>
		<dl>
			<dt>photo</dt>
			<dd>thumbnail — click through to the record page</dd>
			<dt>title / place</dt>
			<dd>title, geocoded place name, short id</dd>
			<dt>size</dt>
			<dd>
				pixel dimensions; <i>pano</i> pill when aspect ≥ 2; 🧭 calibrated; ⛰ terrain render
				(muted while queued / rendering, red on error); <i>overlay</i> pill for a saved fit
				(green when approved) — both link to their bench
			</dd>
			<dt>anns</dt>
			<dd>current annotation count (default sort, most first)</dd>
			<dt>uploaded</dt>
			<dd>upload date in Hillview</dd>
		</dl>
	</Help>
</div>
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
	<label class="muted" style="font-size:12px">
		<input type="checkbox" bind:checked={terrain} onchange={refilter} /> terrain ⛰
	</label>
	<label class="muted" style="font-size:12px">
		<input type="checkbox" bind:checked={overlay} onchange={refilter} /> overlay
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
					{#if p.terrain}
						<a
							href="/terrain?photo={p.id}"
							data-testid="photo-terrain"
							title="terrain render: {p.terrain}"
							style={p.terrain === 'done' ? '' : p.terrain === 'error' ? 'color:var(--bad)' : 'opacity:0.45'}
							>⛰</a
						>
					{/if}
					{#if p.overlay}
						<a
							href="/terrain/overlay?photo={p.id}"
							data-testid="photo-overlay"
							class="pill {p.overlay === 'approved' ? 'ok' : ''}"
							style="font-size:10px"
							title={p.overlay === 'approved' ? 'overlay fit approved (graduates)' : 'overlay fit saved, not approved'}
							>overlay</a
						>
					{/if}
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

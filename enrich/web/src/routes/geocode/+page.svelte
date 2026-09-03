<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import { localStorageSharedStore } from '$lib/svelte-shared-store';
	import type { AnnotationList, AnnotationRow, CandidatesResponse } from '$lib/types';
	import CandidateMap from '$lib/components/CandidateMap.svelte';
	import CandidateTable from '$lib/components/CandidateTable.svelte';
	import Help from '$lib/components/Help.svelte';
	import PhotoThumb from '$lib/components/PhotoThumb.svelte';

	const q = localStorageSharedStore('enrich_geo_q', '');

	let list = $state<AnnotationList | null>(null);
	let sel = $state<AnnotationRow | null>(null);
	let cands = $state<CandidatesResponse | null>(null);
	let selCand = $state<string | null>(null);
	let err = $state<string | null>(null);
	let running = $state(false);
	let offset = $state(0);
	const LIMIT = 30;

	async function load() {
		try {
			const p = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
			if ($q) p.set('q', $q);
			list = await api.get<AnnotationList>(`/annotations?${p}`);
			err = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
	}

	async function select(a: AnnotationRow) {
		sel = a;
		selCand = null;
		cands = null;
		cands = await api.get<CandidatesResponse>(`/annotations/${a.id}/candidates`);
	}

	// after a ✓/✗/↺ in the table (it posts /facts/curate itself)
	async function reloadCands() {
		if (sel) cands = await api.get<CandidatesResponse>(`/annotations/${sel.id}/candidates`);
	}

	// the runner's live state (GET /geocode/status): polled while a job runs,
	// whoever started it — this button, the calibration bench, or a sync
	interface GeoRun {
		id: string;
		status: string;
		note: string | null;
		started_at: string;
		finished_at: string | null;
		error: string | null;
		stats: {
			annotations?: number; done?: number; candidates?: number; wiki_hits?: number; errors?: number;
			current?: { annotation_id: string; label: string | null; wiki: boolean; coords: boolean } | null;
			recent?: { annotation_id: string; label: string | null; hits: number; wiki: boolean; wiki_tried: boolean; pin: boolean }[];
			error_detail?: { annotation_id: string; label: string | null; error: string }[];
		} | null;
	}
	let geo = $state<{ running: boolean; run: GeoRun | null } | null>(null);
	let geoTimer: ReturnType<typeof setTimeout> | null = null;
	async function pollGeo() {
		try {
			const g = await api.get<{ running: boolean; run: GeoRun | null }>('/geocode/status');
			const wasRunning = geo?.running;
			geo = g;
			// fast while a job runs; slow otherwise, so a run started elsewhere
			// (sync, calibration bench, curl) still shows up here
			if (geoTimer) clearTimeout(geoTimer);
			geoTimer = setTimeout(pollGeo, g.running ? 2000 : 10000);
			if (!g.running && wasRunning) {
				// a run just finished under us — refresh what we are looking at
				if (sel) await reloadCands();
				await load();
			}
		} catch {
			/* status is advisory */
		}
	}
	onMount(pollGeo);
	onDestroy(() => geoTimer && clearTimeout(geoTimer));

	async function runGeocode() {
		running = true;
		try {
			await api.post('/geocode/run', { scope: 'all-current' });
			await pollGeo();
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			running = false;
		}
	}

	function label(a: AnnotationRow): string {
		const lt = a.facts.find((f) => f.predicate === 'labelText');
		return lt?.value ?? a.body ?? '(unnamed)';
	}
	function nCands(a: AnnotationRow): number {
		return a.facts.filter((f) => f.predicate === 'anchorCandidate').length;
	}
	function approvedCand(a: AnnotationRow): boolean {
		return a.facts.some((f) => f.predicate === 'anchorCandidate' && f.status === 'approved');
	}

	onMount(load);
	$effect(() => {
		void $q;
		void offset;
		load();
	});
</script>

<div class="row" style="gap:8px">
	<h1>Geocode</h1>
	<Help>
		<h4>what this page does</h4>
		<p>
			Resolves each annotation's label to a place on Earth. The geocoder worker queries
			Nominatim (and Wikipedia coordinates when the body carries a wiki link) per label
			and mints <span class="mono">anchorCandidate</span> facts; here you pick the right
			one. An <b>approved</b> candidate becomes the annotation's <b>anchor</b> — its
			assumed real-world location.
		</p>
		<h4>candidate table</h4>
		<dl>
			<dt>candidate</dt>
			<dd>display name + source URI (OSM object, Wikipedia page, or a geo: pin)</dd>
			<dt>km</dt>
			<dd>distance from the photo</dd>
			<dt>Δ°</dt>
			<dd>bearing to the candidate minus the photo's compass — in-view candidates have small Δ</dd>
			<dt>type</dt>
			<dd>OSM object type (node/way/relation kind)</dd>
			<dt>✓ / ✗</dt>
			<dd>approve (= make it the anchor — one per annotation, a previously approved one is demoted to rejected, noted "superseded") / reject the candidate fact</dd>
		</dl>
		<h4>map</h4>
		<p>
			Blue dot = the photo's position, dashed ray = its stored compass bearing, markers =
			candidates (click to select). A plausible anchor sits near the ray at a sane
			distance.
		</p>
		<h4>actions</h4>
		<dl>
			<dt>⟳ run geocode</dt>
			<dd>enqueue the geocoder over all current labels (cached; re-runs pick up renames)</dd>
		</dl>
		<h4>downstream</h4>
		<p>
			Anchors feed calibration (azimuth reference points), the matching bench's view-pie
			gate, and triangulation. A rename (on the annotation page) redirects future
			geocoding to the new label.
		</p>
	</Help>
</div>
<p class="muted">
	Nominatim/Wikipedia candidates per label, plus locations borrowed from <b>namesake</b>
	annotations (same label or id= key on another photo). Approve the right one — it becomes the anchor.
	Blue dot = photo, dashed ray = its bearing.
</p>

{#if err}<div class="card" style="border-color:var(--bad)">{err}</div>{/if}

{#if geo?.run}
	{@const r = geo.run}
	{@const st = r.stats ?? {}}
	<div class="card" style="font-size:12px; margin-bottom:10px" data-testid="geocode-runner">
		<div class="row" style="gap:10px; align-items:baseline">
			<b>geocode runner</b>
			<span class="pill {geo.running ? 'running' : r.status === 'succeeded' ? 'ok' : 'bad'}">{geo.running ? 'running' : r.status}</span>
			<span class="mono muted" style="font-size:11px">{r.id.slice(0, 8)}</span>
			{#if r.note}<span class="muted">{r.note}</span>{/if}
			<div style="flex:1"></div>
			<span class="mono">{st.done ?? 0}/{st.annotations ?? '?'}</span>
			<span class="muted">· {st.candidates ?? 0} candidates · {st.wiki_hits ?? 0} wiki · {st.errors ?? 0} errors</span>
		</div>
		{#if geo.running && st.annotations}
			<div style="height:4px; background:var(--panel2); border-radius:2px; margin:6px 0">
				<div style="height:4px; width:{Math.round(100 * (st.done ?? 0) / st.annotations)}%; background:var(--accent); border-radius:2px"></div>
			</div>
		{/if}
		{#if geo.running && st.current}
			<div class="muted">now: <a href="/annotations/{st.current.annotation_id}">{st.current.label ?? '(no label)'}</a>{st.current.wiki ? ' · wiki' : ''}{st.current.coords ? ' · pin' : ''}</div>
		{/if}
		{#if st.recent?.length}
			<div class="muted" style="margin-top:4px">
				recent:
				{#each st.recent as o (o.annotation_id)}
					<a href="/annotations/{o.annotation_id}" title={`${o.hits} nominatim hit(s)${o.wiki_tried ? (o.wiki ? ', wiki coords found' : ', wiki page has no coords') : ''}${o.pin ? ', body coords → pin' : ''}`}
						>{o.label ?? '(wiki)'}</a
					><span class="mono" style="font-size:10px"> {o.hits}{o.wiki ? 'w' : ''}{o.pin ? 'p' : ''}</span>{' '}
				{/each}
			</div>
		{/if}
		{#if st.error_detail?.length}
			<div style="color:var(--bad); margin-top:4px">
				{#each st.error_detail as e (e.annotation_id)}<div>{e.label}: {e.error}</div>{/each}
			</div>
		{/if}
		{#if r.error}<div style="color:var(--bad)">{r.error}</div>{/if}
	</div>
{/if}

<div class="row" style="align-items:flex-start; gap:18px">
	<div style="flex:0 0 380px">
		<div class="row" style="margin-bottom:8px">
			<input
				placeholder="search…"
				value={$q}
				onchange={(e) => ($q = (e.target as HTMLInputElement).value)}
				style="flex:1"
			/>
			<button onclick={runGeocode} disabled={running || !!geo?.running} title="geocode all current labels (Nominatim per label, biased to a ~200 km box around the photo; wikipedia coords; pins from body coords)">
				{running || geo?.running ? '⟳ running…' : '⟳ run geocode'}
			</button>
		</div>
		<table>
			<tbody>
				{#each list?.items ?? [] as a (a.id)}
					<tr
						style="cursor:pointer; {sel?.id === a.id ? 'background:var(--panel2)' : ''}"
						onclick={() => select(a)}
					>
						<td style="width:60px"><PhotoThumb sizes={a.sizes} size={54} /></td>
						<td>
							{label(a)}
							{#if approvedCand(a)}<span class="pill ok" style="margin-left:5px">⚓</span>{/if}
						</td>
						<td class="muted" style="text-align:right">{nCands(a) || ''}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		<div class="row" style="margin-top:8px">
			<button disabled={offset === 0} onclick={() => (offset = Math.max(0, offset - LIMIT))}>‹</button>
			<span class="muted" style="font-size:12px"
				>{offset + 1}–{Math.min(offset + LIMIT, list?.total ?? 0)} / {list?.total ?? 0}</span
			>
			<button disabled={!list || offset + LIMIT >= list.total} onclick={() => (offset += LIMIT)}>›</button>
		</div>
	</div>

	<div style="flex:1; min-width:420px">
		{#if sel && cands}
			<div class="row" style="margin-bottom:6px">
				<b>{label(sel)}</b>
				<span class="mono muted" style="font-size:11px">{sel.id.slice(0, 8)}</span>
				<a href="/annotations/{sel.id}">detail</a>
				<a href={sel.web_url} target="_blank" rel="noreferrer">hillview ↗</a>
			</div>
			<CandidateMap
				photo={cands.photo}
				candidates={cands.candidates}
				selected={selCand}
				onselect={(c) => (selCand = c)}
			/>
			<div style="margin-top:10px">
				<CandidateTable
					candidates={cands.candidates}
					selected={selCand}
					onselect={(c) => (selCand = c)}
					onchange={reloadCands}
				/>
			</div>
		{:else}
			<p class="muted">← pick an annotation</p>
		{/if}
	</div>
</div>

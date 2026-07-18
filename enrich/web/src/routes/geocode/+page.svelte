<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import { localStorageSharedStore } from '$lib/svelte-shared-store';
	import type { AnnotationList, AnnotationRow, CandidatesResponse } from '$lib/types';
	import CandidateMap from '$lib/components/CandidateMap.svelte';
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

	async function curate(fact: string, decision: 'approved' | 'rejected' | 'proposed') {
		await api.post('/facts/curate', { fact, decision });
		if (sel) cands = await api.get<CandidatesResponse>(`/annotations/${sel.id}/candidates`);
	}

	async function runGeocode() {
		running = true;
		try {
			await api.post('/geocode/run', { scope: 'all-current' });
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

<h1>Geocode</h1>
<p class="muted">
	Nominatim/Wikipedia candidates per label. Approve the right one — it becomes the anchor.
	Blue dot = photo, dashed ray = its bearing.
</p>

{#if err}<div class="card" style="border-color:var(--bad)">{err}</div>{/if}

<div class="row" style="align-items:flex-start; gap:18px">
	<div style="flex:0 0 380px">
		<div class="row" style="margin-bottom:8px">
			<input
				placeholder="search…"
				value={$q}
				onchange={(e) => ($q = (e.target as HTMLInputElement).value)}
				style="flex:1"
			/>
			<button onclick={runGeocode} disabled={running} title="geocode all current labels">
				{running ? '…' : '⟳ run geocode'}
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
			<table style="margin-top:10px">
				<thead><tr><th></th><th>candidate</th><th>km</th><th>Δ°</th><th>type</th><th></th></tr></thead>
				<tbody>
					{#each cands.candidates as c (c.candidate)}
						<tr
							style="cursor:pointer; {selCand === c.candidate ? 'background:var(--panel2)' : ''}"
							onclick={() => (selCand = c.candidate)}
						>
							<td>
								<span
									class="pill {c.status === 'approved' ? 'ok' : c.status === 'rejected' ? 'bad' : ''}"
									>{c.status[0]}</span
								>
							</td>
							<td style="max-width:340px">
								<a href={c.candidate} target="_blank" rel="noreferrer" style="font-size:12px">
									{c.displayName ?? c.candidate.replace('https://', '')}
								</a>
							</td>
							<td class="mono">{c.km ?? ''}</td>
							<td
								class="mono"
								style={Math.abs(c.bearing_offset ?? 0) > 60 ? 'color:var(--warn)' : ''}
							>
								{c.bearing_offset ?? ''}
							</td>
							<td class="muted" style="font-size:11px">{c.osmType ?? 'wiki'}</td>
							<td style="white-space:nowrap">
								{#if c.status !== 'approved'}
									<button title="approve = the anchor" onclick={(e) => { e.stopPropagation(); curate(c.fact, 'approved'); }}>✓</button>
								{/if}
								{#if c.status !== 'rejected'}
									<button title="reject" onclick={(e) => { e.stopPropagation(); curate(c.fact, 'rejected'); }}>✗</button>
								{/if}
								{#if c.status !== 'proposed'}
									<button title="reset" onclick={(e) => { e.stopPropagation(); curate(c.fact, 'proposed'); }}>↺</button>
								{/if}
							</td>
						</tr>
					{:else}
						<tr><td colspan="6" class="muted">no candidates — run geocode, or the label found nothing</td></tr>
					{/each}
				</tbody>
			</table>
		{:else}
			<p class="muted">← pick an annotation</p>
		{/if}
	</div>
</div>

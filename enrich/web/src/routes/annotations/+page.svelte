<script lang="ts">
	import { api, ApiError } from '$lib/api';
	import { localStorageSharedStore } from '$lib/svelte-shared-store';
	import type { AnnotationList } from '$lib/types';
	import FactChip from '$lib/components/FactChip.svelte';
	import Help from '$lib/components/Help.svelte';
	import PhotoThumb from '$lib/components/PhotoThumb.svelte';

	const filters = localStorageSharedStore('enrich_ann_filters', {
		pano: false,
		status: '',
		q: ''
	});

	let data = $state<AnnotationList | null>(null);
	let err = $state<string | null>(null);
	let loading = $state(false);
	let offset = $state(0);
	const LIMIT = 50;

	// bulk parse: every current annotation body → facts (local, content-
	// addressed, idempotent — re-running is free; curation survives). Sync
	// parses + geocodes the rows it changed by itself; this is the catch-up for
	// a parser version bump or an orphaned run.
	let parsing = $state(false);
	let parseMsg = $state<string | null>(null);
	async function parseAll() {
		parsing = true;
		parseMsg = null;
		try {
			const r = await api.post<{ run_id: string; stats: Record<string, number> }>('/parse/run', {
				scope: 'all-current',
				note: 'from annotations bench'
			});
			const st = r.stats;
			parseMsg = `parsed ${st.annotations} annotations → ${st.facts} facts (${st.with_coords} with coords, ${st.with_wiki} with wiki, ${st.unnamed} unnamed)`;
			await load();
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			parsing = false;
		}
	}

	async function load() {
		loading = true;
		try {
			const p = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
			if ($filters.pano) p.set('pano', 'true');
			if ($filters.status) p.set('status', $filters.status);
			if ($filters.q) p.set('q', $filters.q);
			data = await api.get<AnnotationList>(`/annotations?${p}`);
			err = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			loading = false;
		}
	}

	// reload when filters/offset change
	$effect(() => {
		void $filters.pano;
		void $filters.status;
		void $filters.q;
		void offset;
		load();
	});

	function segs(body: string | null): string[] {
		return (body ?? '').split('|').map((s) => s.trim());
	}
</script>

<div class="row" style="gap:8px">
	<h1>Annotations</h1>
	<Help>
		<h4>what this page does</h4>
		<p>
			The mirrored annotations with the facts the parser extracted from each body.
			<b>⟳ parse all</b> (top right) runs that parser in bulk. Sync already parses and
			geocodes the annotations it changed; the bulk buttons are for a parser upgrade
			(re-parse everything) or catch-up after an orphaned run.
			Bodies are pipe-separated (<span class="mono">name|wiki-url|…</span>); the parser
			worker turns them into RDF facts (labelText, wikipediaUrl, …), each stored as its
			own content-addressed graph with proposed/approved/rejected curation status.
		</p>
		<h4>filters</h4>
		<dl>
			<dt>panos only</dt>
			<dd>annotations on photos with aspect ≥ 2</dd>
			<dt>status</dt>
			<dd>show only annotations having a fact with that curation status</dd>
			<dt>search</dt>
			<dd>body substring</dd>
		</dl>
		<h4>columns</h4>
		<dl>
			<dt>photo</dt>
			<dd>the photo the annotation sits on</dd>
			<dt>body</dt>
			<dd>raw body text, segments split on |; links to the annotation detail page</dd>
			<dt>facts</dt>
			<dd>
				parsed fact chips — green border approved, red/struck rejected, plain proposed.
				Curation verbs live on the detail page
			</dd>
		</dl>
		<h4>downstream</h4>
		<p>
			The detail page is where everything happens: rename, wiki-attach, anchor curation
			(geocode), POI relations, matching verdicts. Approved facts eventually flow back
			into Hillview via Graduation.
		</p>
	</Help>
</div>
<p class="muted">
	Annotation bodies → parsed facts. Curate on the detail page or via the chips' verbs there.
</p>

<div class="card row">
	<label><input type="checkbox" bind:checked={$filters.pano} /> panos only</label>
	<select bind:value={$filters.status}>
		<option value="">any status</option>
		<option value="proposed">proposed</option>
		<option value="approved">approved</option>
		<option value="rejected">rejected</option>
	</select>
	<input
		placeholder="search body…"
		value={$filters.q}
		onchange={(e) => ($filters.q = (e.target as HTMLInputElement).value)}
	/>
	{#if loading}<span class="muted">loading…</span>{/if}
	<div style="flex:1"></div>
	<span class="muted">{data ? `${data.total} annotations` : ''}</span>
	<button
		data-testid="parse-all"
		onclick={parseAll}
		disabled={parsing}
		title="run the body parser over every current annotation (local, idempotent) — sync already parses + geocodes what it changed; use this after a parser upgrade or an orphaned run">
		{parsing ? 'parsing…' : '⟳ parse all'}
	</button>
</div>
{#if parseMsg}<p class="muted" style="font-size:12px; margin:4px 0">{parseMsg} — next: <a href="/geocode">⟳ run geocode</a> to mint anchor candidates from the new labels/coords</p>{/if}

{#if err}<div class="card" style="border-color:var(--bad)">{err}</div>{/if}

<table>
	<thead><tr><th>photo</th><th>body</th><th>facts</th><th></th></tr></thead>
	<tbody>
		{#each data?.items ?? [] as a (a.id)}
			<tr>
				<td>
					<a href="/photos/{a.photo_id}" title="photo page"><PhotoThumb sizes={a.sizes} size={90} /></a>
				</td>
				<td style="max-width:300px">
					<a href="/annotations/{a.id}" class="mono" style="font-size:12px">
						{#each segs(a.body) as s, i (i)}
							{#if i > 0}<span class="muted"> | </span>{/if}<span>{s}</span>
						{/each}
					</a>
					<div class="muted" style="font-size:11px; margin-top:3px">
						{a.place_name ?? ''}
						{a.compass_angle != null ? `· ${Math.round(a.compass_angle)}°` : ''}
					</div>
				</td>
				<td>
					{#each a.facts.filter((f) => f.predicate !== 'onPhoto') as f (f.fact)}
						<FactChip fact={f} />
					{/each}
				</td>
				<td style="white-space:nowrap">
					<a href={a.web_url} target="_blank" rel="noreferrer" title="open on hillview.cz">🌍</a>
				</td>
			</tr>
		{/each}
	</tbody>
</table>

<div class="row" style="margin-top:12px">
	<button disabled={offset === 0} onclick={() => (offset = Math.max(0, offset - LIMIT))}>‹ prev</button>
	<span class="muted">{offset + 1}–{Math.min(offset + LIMIT, data?.total ?? 0)} of {data?.total ?? 0}</span>
	<button
		disabled={!data || offset + LIMIT >= data.total}
		onclick={() => (offset = offset + LIMIT)}>next ›</button
	>
</div>

<script lang="ts">
	import { api, ApiError } from '$lib/api';
	import { localStorageSharedStore } from '$lib/svelte-shared-store';
	import Help from '$lib/components/Help.svelte';

	const EXAMPLES: Record<string, string> = {
		'facts of one annotation': `PREFIX hv: <https://rdf.hillview.cz/ns#>
SELECT ?f ?p ?o WHERE {
  GRAPH <https://rdf.hillview.cz/id/graph/meta> { ?f hv:about ?ann }
  GRAPH ?f { ?ann ?p ?o }
} LIMIT 50`,
		'label counts': `PREFIX hv: <https://rdf.hillview.cz/ns#>
SELECT ?label (COUNT(?ann) AS ?n) WHERE {
  GRAPH ?f { ?ann hv:labelText ?label }
} GROUP BY ?label ORDER BY DESC(?n) LIMIT 30`,
		'curation decisions': `PREFIX hv: <https://rdf.hillview.cz/ns#>
SELECT ?f ?status ?at WHERE {
  GRAPH <https://rdf.hillview.cz/id/graph/curation>
    { ?f hv:status ?status ; hv:decidedAt ?at }
} ORDER BY DESC(?at) LIMIT 50`,
		'runs & their fact counts': `PREFIX hv: <https://rdf.hillview.cz/ns#>
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?run (COUNT(?f) AS ?facts) WHERE {
  GRAPH <https://rdf.hillview.cz/id/graph/meta> { ?f prov:wasGeneratedBy ?run }
} GROUP BY ?run ORDER BY DESC(?facts)`
	};

	const saved = localStorageSharedStore('enrich_sparql_query', EXAMPLES['facts of one annotation']);
	let result = $state<{ head: { vars: string[] }; results: { bindings: Record<string, { value: string }>[] } } | null>(null);
	let err = $state<string | null>(null);
	let busy = $state(false);

	async function run() {
		busy = true;
		err = null;
		result = null;
		try {
			result = await api.post('/sparql', { query: $saved });
		} catch (e) {
			err = e instanceof ApiError ? e.message : String(e);
		} finally {
			busy = false;
		}
	}
</script>

<div class="row" style="gap:8px">
	<h1>SPARQL</h1>
	<Help>
		<h4>what this page does</h4>
		<p>
			Raw read access to the Oxigraph fact store — the same store all benches write to.
			The examples dropdown seeds runnable queries for the common shapes.
		</p>
		<h4>how the store is laid out</h4>
		<dl>
			<dt>fact graphs</dt>
			<dd>
				each fact is ONE triple in its own named graph
				<span class="mono">…/id/fact/&lt;hash&gt;</span>, content-addressed from
				(s,&nbsp;p,&nbsp;o) — asserting the same fact twice is a no-op, and curation can
				point at the fact without RDF-star
			</dd>
			<dt>curation graph</dt>
			<dd>
				<span class="mono">…/id/graph/curation</span> — per-fact
				<span class="mono">hv:status</span> (proposed / approved / rejected) +
				<span class="mono">hv:decidedAt</span>
			</dd>
			<dt>meta graph</dt>
			<dd>
				<span class="mono">…/id/graph/meta</span> — provenance:
				<span class="mono">prov:wasGeneratedBy</span> links each fact to its run,
				<span class="mono">hv:about</span> links it to its main entity
			</dd>
		</dl>
		<h4>vocabulary</h4>
		<p>
			Namespace <span class="mono">https://rdf.hillview.cz/ns#</span> (prefix
			<span class="mono">hv:</span>); entities live under
			<span class="mono">…/id/annotation/…</span>, <span class="mono">…/id/photo/…</span>,
			<span class="mono">…/id/poi/…</span>, <span class="mono">…/id/run/…</span>. The
			usual pattern is joining <span class="mono">GRAPH ?f {'{ … }'}</span> against the
			curation/meta graphs, as in the examples.
		</p>
	</Help>
</div>
<p class="muted">Raw query access to the fact store (Oxigraph). Full quads fun.</p>

<div class="card">
	<div class="row" style="margin-bottom:8px">
		<select onchange={(e) => ($saved = EXAMPLES[(e.target as HTMLSelectElement).value])}>
			{#each Object.keys(EXAMPLES) as k (k)}<option>{k}</option>{/each}
		</select>
		<button class="primary" onclick={run} disabled={busy}>{busy ? 'running…' : 'Run'}</button>
	</div>
	<textarea rows="9" bind:value={$saved}></textarea>
</div>

{#if err}<div class="card" style="border-color:var(--bad); white-space:pre-wrap" class:mono={true}>{err}</div>{/if}

{#if result}
	<p class="muted">{result.results.bindings.length} rows</p>
	<div style="overflow-x:auto">
		<table>
			<thead><tr>{#each result.head.vars as v (v)}<th>{v}</th>{/each}</tr></thead>
			<tbody>
				{#each result.results.bindings as b, i (i)}
					<tr>
						{#each result.head.vars as v (v)}
							<td class="mono" style="font-size:12px">{b[v]?.value ?? ''}</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<script lang="ts">
	import { api, ApiError } from '$lib/api';
	import { localStorageSharedStore } from '$lib/svelte-shared-store';

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

<h1>SPARQL</h1>
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

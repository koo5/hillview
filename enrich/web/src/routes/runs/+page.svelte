<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import type { RunRow } from '$lib/types';
	import Help from '$lib/components/Help.svelte';

	let runs = $state<RunRow[]>([]);
	let kind = $state('');

	async function load() {
		const p = kind ? `?kind=${kind}` : '';
		runs = await api.get<RunRow[]>(`/runs${p}`);
	}
	onMount(load);
	$effect(() => {
		void kind;
		load();
	});

	const fmt = (t: string | null) => (t ? new Date(t).toLocaleString() : '—');
	const dur = (r: RunRow) =>
		r.finished_at
			? `${((new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000).toFixed(1)}s`
			: '…';
</script>

<div class="row" style="gap:8px">
	<h1>Runs</h1>
	<Help>
		<h4>what this page does</h4>
		<p>
			The provenance ledger. Every operation that creates or curates facts — sync
			passes, parser runs, geocoding, calibrations, verdicts, transfers, graduation
			exports — is recorded as a run, and each fact links back to the run that generated
			it (prov:wasGeneratedBy in the meta graph). If you wonder "where did this fact
			come from", the answer is here.
		</p>
		<h4>columns</h4>
		<dl>
			<dt>kind</dt>
			<dd>
				operation type — the filter above lists the common ones; benches create their
				own kinds (calibration, verdict, transfer_accept, label_edit, …)
			</dd>
			<dt>status</dt>
			<dd>succeeded / failed / running</dd>
			<dt>took</dt>
			<dd>wall-clock duration</dd>
			<dt>stats</dt>
			<dd>the run's own summary JSON (counts, fit numbers, error text on failure)</dd>
			<dt>graph</dt>
			<dd>the run's named graph in the fact store, when it wrote one</dd>
		</dl>
	</Help>
</div>
<div class="card row">
	<select bind:value={kind}>
		<option value="">all kinds</option>
		<option value="annotation_parse">annotation_parse</option>
		<option value="sync_append">sync_append</option>
		<option value="sync_reconcile">sync_reconcile</option>
	</select>
</div>

<table>
	<thead><tr><th>kind</th><th>status</th><th>started</th><th>took</th><th>stats</th><th>graph</th></tr></thead>
	<tbody>
		{#each runs as r (r.id)}
			<tr>
				<td>{r.kind}</td>
				<td><span class="pill {r.status === 'succeeded' ? 'ok' : r.status === 'failed' ? 'bad' : 'running'}">{r.status}</span></td>
				<td class="muted">{fmt(r.started_at)}</td>
				<td class="muted">{dur(r)}</td>
				<td class="mono" style="font-size:11px; max-width:420px">{JSON.stringify(r.stats)}</td>
				<td class="mono muted" style="font-size:11px">{r.graph_iri ? r.graph_iri.split('/').pop() : ''}</td>
			</tr>
		{/each}
	</tbody>
</table>

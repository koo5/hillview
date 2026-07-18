<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import type { RunRow } from '$lib/types';

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

<h1>Runs</h1>
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

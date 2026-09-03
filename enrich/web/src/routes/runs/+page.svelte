<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import type { RunRow } from '$lib/types';
	import Help from '$lib/components/Help.svelte';

	let runs = $state<RunRow[]>([]);
	let kind = $state('');

	// while anything is running, keep the list live (geocode runs update their
	// stats per annotation: done/total, the label being looked up, recent hits)
	let timer: ReturnType<typeof setTimeout> | null = null;
	async function load() {
		const p = kind ? `?kind=${kind}` : '';
		runs = await api.get<RunRow[]>(`/runs${p}`);
		if (timer) clearTimeout(timer);
		if (runs.some((r) => r.status === 'running')) timer = setTimeout(load, 3000);
	}
	onMount(load);
	onDestroy(() => timer && clearTimeout(timer));

	// a running geocode run's stats carry live detail — say it in words; other
	// stats stay raw JSON (dropping the bulky live arrays once finished)
	function progress(r: RunRow): string | null {
		const st = r.stats as Record<string, unknown> | null;
		if (!st || !('done' in st) || !('annotations' in st)) return null;
		const cur = st.current as { label?: string | null; wiki?: boolean; coords?: boolean } | null | undefined;
		const head = `${st.done}/${st.annotations} · ${st.candidates ?? 0} candidates · ${st.wiki_hits ?? 0} wiki · ${st.errors ?? 0} errors`;
		return r.status === 'running' && cur
			? `${head} · now: ${cur.label ?? '(wiki page)'}${cur.wiki ? ' +wiki' : ''}${cur.coords ? ' +pin' : ''}`
			: head;
	}
	function statsText(r: RunRow): string {
		const st = r.stats as Record<string, unknown> | null;
		if (!st) return '';
		const { current, recent, error_detail, ...rest } = st;
		void current; void recent; void error_detail;
		return JSON.stringify(rest);
	}
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
				<td class="mono" style="font-size:11px; max-width:420px">
					{#if progress(r)}<div data-testid="run-progress" style={r.status === 'running' ? 'color:var(--accent)' : ''}>{progress(r)}</div>{/if}
					<span class="muted">{statsText(r)}</span>
				</td>
				<td class="mono muted" style="font-size:11px">{r.graph_iri ? r.graph_iri.split('/').pop() : ''}</td>
			</tr>
		{/each}
	</tbody>
</table>

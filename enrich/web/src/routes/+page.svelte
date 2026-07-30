<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import type { SyncStatus, Health } from '$lib/types';
	import Help from '$lib/components/Help.svelte';

	let health = $state<Health | null>(null);
	let status = $state<SyncStatus | null>(null);
	let err = $state<string | null>(null);
	let busy = $state<string | null>(null);
	let timer: ReturnType<typeof setInterval>;

	async function refresh() {
		try {
			[health, status] = await Promise.all([
				api.get<Health>('/health'),
				api.get<SyncStatus>('/sync/status')
			]);
			err = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
	}

	async function sync(mode: 'append' | 'reconcile') {
		busy = mode;
		try {
			await api.post('/sync/run', { mode });
			for (let i = 0; i < 120; i++) {
				await new Promise((r) => setTimeout(r, 1500));
				await refresh();
				if (status && !status.running) break;
			}
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			busy = null;
		}
	}

	onMount(() => {
		refresh();
		timer = setInterval(refresh, 5000);
	});
	onDestroy(() => clearInterval(timer));

	const fmt = (t: string | null) => (t ? new Date(t).toLocaleString() : '—');
</script>

<div class="row" style="gap:8px">
	<h1>Dashboard</h1>
	<Help>
		<h4>what this page does</h4>
		<p>
			Health of the workbench plumbing. The workbench never edits Hillview's tables: it
			keeps a read-only <b>mirror</b> of photos and annotations, enriches on top of the
			mirror, and pushes curation back only through Graduation packages.
		</p>
		<h4>sync modes</h4>
		<dl>
			<dt>append</dt>
			<dd>
				cheap incremental pull — fetches rows with <span class="mono">created_at</span>
				past the stored watermark
			</dd>
			<dt>reconcile</dt>
			<dd>
				full pass — row-hash comparison catches edits, deletions, and anything append
				missed. <b>Run this after importing a dump</b>: dump rows keep their old
				production timestamps, which sit behind the watermark, so append skips them
			</dd>
		</dl>
		<h4>sections</h4>
		<dl>
			<dt>Services</dt>
			<dd>API, workbench DB, Oxigraph, queue — red means a container is down</dd>
			<dt>Mirror</dt>
			<dd>row counts per mirrored table</dd>
			<dt>Sync state</dt>
			<dd>per-table watermark + when each mode last ran</dd>
			<dt>Recent sync runs</dt>
			<dd>the same runs as on the Runs page, filtered to sync</dd>
		</dl>
	</Help>
</div>
<p class="muted">Live mirror of the Hillview dev data + enrichment run history.</p>

{#if err}<div class="card" style="border-color:var(--bad)">{err}</div>{/if}

<h2>Services</h2>
<div class="card row">
	{#if health}
		{#each health.checks as c (c.dep)}
			<span class="pill {c.ok ? 'ok' : 'bad'}">{c.dep} · {c.ms}ms</span>
		{/each}
	{:else}
		<span class="muted">…</span>
	{/if}
</div>

<h2>Mirror</h2>
<div class="row">
	{#each Object.entries(status?.counts ?? {}) as [name, c] (name)}
		<div class="stat">
			<div class="n">{c.total.toLocaleString()}</div>
			<div class="l">{name.replace('_mirror', '')}{c.missing ? ` · ${c.missing} missing` : ''}</div>
		</div>
	{/each}
	<div style="flex:1"></div>
	<button class="primary" disabled={busy !== null || status?.running} onclick={() => sync('append')}>
		{busy === 'append' ? 'Appending…' : 'Sync append'}
	</button>
	<button disabled={busy !== null || status?.running} onclick={() => sync('reconcile')}>
		{busy === 'reconcile' ? 'Reconciling…' : 'Reconcile'}
	</button>
	{#if status?.running}<span class="pill running">running</span>{/if}
</div>

<h2>Sync state</h2>
<table>
	<thead>
		<tr><th>table</th><th>watermark</th><th>last append</th><th>last reconcile</th></tr>
	</thead>
	<tbody>
		{#each status?.state ?? [] as s (s.table_name)}
			<tr>
				<td>{s.table_name}</td>
				<td class="mono muted">{fmt(s.watermark)}</td>
				<td class="muted">{fmt(s.last_append_at)}</td>
				<td class="muted">{fmt(s.last_reconcile_at)}</td>
			</tr>
		{/each}
	</tbody>
</table>

<h2>Recent sync runs</h2>
<table>
	<thead><tr><th>kind</th><th>status</th><th>started</th><th>stats</th></tr></thead>
	<tbody>
		{#each status?.last_runs ?? [] as r (r.id)}
			<tr>
				<td>{r.kind}</td>
				<td>
					<span class="pill {r.status === 'succeeded' ? 'ok' : r.status === 'failed' ? 'bad' : 'running'}">
						{r.status}
					</span>
				</td>
				<td class="muted">{fmt(r.started_at)}</td>
				<td class="mono muted" style="font-size:11px">{JSON.stringify(r.stats)}</td>
			</tr>
		{/each}
	</tbody>
</table>

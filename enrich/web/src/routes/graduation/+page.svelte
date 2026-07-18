<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import PhotoThumb from '$lib/components/PhotoThumb.svelte';

	interface Change {
		what: string;
		from: string | null;
		to: string | null;
	}
	interface SuggestionFact {
		fact: string;
		predicate: string;
		value: string;
		decided_at?: string;
	}
	interface Suggestion {
		annotation_id: string;
		photo_id: string;
		sizes: Record<string, { url?: string }> | null;
		current_body: string | null;
		suggested_body: string;
		changes: Change[];
		facts: SuggestionFact[];
		decided_at: string | null;
		anchor: { uri: string; lat: number; lon: number } | null;
	}
	interface TargetChange {
		annotation_id: string;
		photo_id: string;
		sizes: Record<string, { url?: string }> | null;
		current_rect: string | null;
		proposed_rect: string;
	}
	interface Suggestions {
		suggestions: Suggestion[];
		landed: Suggestion[];
		creates: Suggestion[];
		target_changes: TargetChange[];
	}

	let data = $state<Suggestions | null>(null);
	let err = $state<string | null>(null);

	// "curated 3h ago" — the sort key made legible
	function ago(iso: string | null): string {
		if (!iso) return '';
		const then = new Date(iso).getTime();
		if (Number.isNaN(then)) return '';
		const s = Math.max(0, (Date.now() - then) / 1000);
		if (s < 90) return 'just now';
		if (s < 5400) return `${Math.round(s / 60)}m ago`;
		if (s < 172800) return `${Math.round(s / 3600)}h ago`;
		return `${Math.round(s / 86400)}d ago`;
	}

	interface Package {
		package: string;
		format_version: number;
		created_at: string;
		run_id: string;
		counts: { ops: number; facts: number };
		ops: unknown[];
		provenance_trig: string;
	}
	let exporting = $state(false);
	let exportMsg = $state<string | null>(null);

	async function exportPackage() {
		if (!data || (!data.suggestions.length && !data.creates.length && !data.target_changes.length))
			return;
		exporting = true;
		exportMsg = null;
		try {
			// empty body = all pending; the /graduation review IS the selection
			const pkg = await api.post<Package>('/graduation/export', {});
			const json = JSON.stringify(pkg, null, 2);
			const stamp = pkg.created_at.slice(0, 19).replace(/[:T]/g, '-');
			const blob = new Blob([json], { type: 'application/json' });
			const a = document.createElement('a');
			a.href = URL.createObjectURL(blob);
			a.download = `${pkg.package}-${stamp}.json`;
			a.click();
			URL.revokeObjectURL(a.href);
			exportMsg = `⬇ ${pkg.counts.ops} ops · ${pkg.counts.facts} provenance facts · run ${pkg.run_id.slice(0, 8)} — drop this file into Hillview's admin to apply`;
		} catch (e) {
			exportMsg = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			exporting = false;
		}
	}

	onMount(async () => {
		try {
			data = await api.get<Suggestions>('/graduation/suggestions');
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
	});
</script>

<h1>Graduation</h1>
<p class="muted">
	What approved curation would push back into Hillview: for every annotation with an
	<b>approved</b> labelText or anchorCandidate fact, the suggested body is the facts
	serialized into the annotation's <span class="mono">name | context | … | lat, lon</span>
	format (unrecognized segments preserved verbatim; round-trips through the parser).
	This page is a derived preview — nothing is written to Hillview from here. <b>Export
	package</b> bundles the pending set into a JSON ops manifest (each op carries a body
	precondition, so a concurrent edit is skipped, never clobbered) + a TriG provenance
	appendix; drop that file into Hillview's admin to review and apply. Landing is observed
	via the mirror sync — applied items simply move to “already reflected” on the next sync.
</p>

{#if err}<div class="card" style="border-color:var(--bad)">{err}</div>{/if}

{#if data}
	<div class="row" style="align-items:center; gap:12px">
		<h2 style="margin:0">
			Pending — {data.suggestions.length + data.creates.length + data.target_changes.length}
		</h2>
		{#if data.suggestions.length || data.creates.length || data.target_changes.length}
			<button class="primary" disabled={exporting} onclick={exportPackage}>
				{exporting
					? 'building…'
					: `⬇ export package (${data.suggestions.length + data.creates.length + data.target_changes.length})`}
			</button>
		{/if}
	</div>
	{#if exportMsg}
		<div class="muted" style="font-size:12px; margin:6px 0">{exportMsg}</div>
	{/if}
	{#if data.suggestions.length}
		<table>
			<thead>
				<tr><th>pano</th><th>annotation</th><th>curated</th><th>body</th><th>driving facts</th></tr>
			</thead>
			<tbody>
				{#each data.suggestions as s (s.annotation_id)}
					<tr>
						<td style="width:76px">
							<a href="/photos/{s.photo_id}"><PhotoThumb sizes={s.sizes} size={70} /></a>
						</td>
						<td style="white-space:nowrap">
							<a href="/annotations/{s.annotation_id}" class="mono" style="font-size:12px">
								{s.annotation_id.slice(0, 8)}
							</a>
							<div>
								<a href="/matching?annotation={s.annotation_id}" class="muted" style="font-size:10px">
									match ↗
								</a>
							</div>
						</td>
						<td class="muted" style="white-space:nowrap; font-size:11px"
							title={s.decided_at ?? ''}>{ago(s.decided_at)}</td>
						<td>
							<div class="mono muted" style="font-size:12px; text-decoration:line-through">
								{s.current_body || '(empty)'}
							</div>
							<div class="mono" style="font-size:12px; color:var(--ok)">
								{s.suggested_body}
							</div>
							<div style="margin-top:2px">
								{#each s.changes as c (c.what)}
									<span class="pill" style="font-size:10px" title="{c.from ?? '∅'} → {c.to}">
										{c.what}
									</span>
								{/each}
							</div>
						</td>
						<td style="font-size:11px">
							{#each s.facts as f (f.fact)}
								<div class="mono" style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:340px"
									title={f.fact}>
									<span class="pill ok" style="font-size:9px">✓</span>
									{f.predicate} = {f.value}
								</div>
							{/each}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{:else if !data.creates.length && !data.target_changes.length}
		<p class="muted">nothing pending — approve labels/anchors on annotation pages to propose changes</p>
	{/if}

	{#if data.creates.length}
		<h2 style="margin-top:18px">New annotations to create — {data.creates.length}</h2>
		<p class="muted" style="font-size:12px">
			workbench-drawn annotations (origin=workbench) that don't exist in Hillview yet — the
			package CREATES them there (idempotent by their id), then the mirror sync retires the
			local copy
		</p>
		<table>
			<thead><tr><th>pano</th><th>annotation</th><th>body</th><th>driving facts</th></tr></thead>
			<tbody>
				{#each data.creates as s (s.annotation_id)}
					<tr>
						<td style="width:76px">
							<a href="/photos/{s.photo_id}"><PhotoThumb sizes={s.sizes} size={70} /></a>
						</td>
						<td style="white-space:nowrap">
							<a href="/annotations/{s.annotation_id}" class="mono" style="font-size:12px">{s.annotation_id.slice(0, 8)}</a>
						</td>
						<td>
							<div class="mono" style="font-size:12px; color:var(--ok)">{s.suggested_body}</div>
							<span class="pill" style="font-size:10px">create</span>
						</td>
						<td style="font-size:11px">
							{#each s.facts as f (f.fact)}
								<div class="mono" style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:340px" title={f.fact}>
									<span class="pill ok" style="font-size:9px">✓</span> {f.predicate} = {f.value}
								</div>
							{/each}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}

	{#if data.target_changes.length}
		<h2 style="margin-top:18px">Reshapes to graduate — {data.target_changes.length}</h2>
		<p class="muted" style="font-size:12px">
			mirrored annotations reshaped in the workbench (a proposed geometry) — the package
			applies the new rectangle to Hillview (keeping the body), then the mirror confirms it
		</p>
		<table>
			<thead><tr><th>pano</th><th>annotation</th><th>rect x,y,w,h</th></tr></thead>
			<tbody>
				{#each data.target_changes as t (t.annotation_id)}
					<tr>
						<td style="width:76px">
							<a href="/photos/{t.photo_id}"><PhotoThumb sizes={t.sizes} size={70} /></a>
						</td>
						<td style="white-space:nowrap">
							<a href="/annotations/{t.annotation_id}" class="mono" style="font-size:12px">{t.annotation_id.slice(0, 8)}</a>
						</td>
						<td class="mono" style="font-size:11px">
							<div class="muted" style="text-decoration:line-through">{t.current_rect ?? '—'}</div>
							<div style="color:var(--ok)">{t.proposed_rect}</div>
							<span class="pill" style="font-size:10px">reshape</span>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}

	{#if data.landed.length}
		<h2 style="margin-top:18px">Already reflected — {data.landed.length}</h2>
		<p class="muted" style="font-size:12px">
			approved facts whose serialization already matches the mirrored body (either the
			body carried the information all along, or a previous package landed and the
			mirror sync confirmed it)
		</p>
		<table>
			<tbody>
				{#each data.landed as s (s.annotation_id)}
					<tr>
						<td style="width:56px">
							<a href="/photos/{s.photo_id}"><PhotoThumb sizes={s.sizes} size={46} /></a>
						</td>
						<td><a href="/annotations/{s.annotation_id}" class="mono" style="font-size:11px">{s.annotation_id.slice(0, 8)}</a></td>
						<td class="mono muted" style="font-size:11px">{s.current_body}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
{:else if !err}
	<p class="muted">loading…</p>
{/if}

<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import Help from '$lib/components/Help.svelte';
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
	interface OverlayFitSummary {
		projection: string;
		centre_bearing: number;
		fov_deg: number;
		horizon_pct: number;
		v_scale: number;
		roll_deg: number;
		warp: number[];
		visibility_km?: number | null;
	}
	interface OverlayItem {
		photo_id: string;
		photo_title: string | null;
		sizes: Record<string, { url?: string }> | null;
		fit: OverlayFitSummary;
		decided_at: string | null;
		fact: string;
		has_current: boolean;
	}
	interface Suggestions {
		suggestions: Suggestion[];
		landed: Suggestion[];
		creates: Suggestion[];
		target_changes: TargetChange[];
		overlays: OverlayItem[];
		overlays_landed: OverlayItem[];
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
		counts: { ops: number; facts: number; blobs?: number; blob_bytes?: number };
		ops: unknown[];
		provenance_trig: string;
		/** overlays the review page offered but that could not be baked */
		skipped?: { photo_id: string; photo_title: string | null; error: string }[];
	}
	let exporting = $state(false);
	let exportMsg = $state<string | null>(null);
	let exportSkipped = $state<{ photo_id: string; photo_title: string | null; error: string }[]>(
		[]
	);

	/** everything the export would carry — annotations plus overlays */
	const pendingCount = $derived(
		data
			? data.suggestions.length +
					data.creates.length +
					data.target_changes.length +
					data.overlays.length
			: 0
	);

	async function exportPackage() {
		if (!data || !pendingCount) return;
		exporting = true;
		exportMsg = null;
		exportSkipped = [];
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
			const blobNote = pkg.counts.blobs
				? ` · ${pkg.counts.blobs} depth buffer(s), ${Math.round((pkg.counts.blob_bytes ?? 0) / 1024)} KB`
				: '';
			exportMsg = `⬇ ${pkg.counts.ops} ops · ${pkg.counts.facts} provenance facts${blobNote} · run ${pkg.run_id.slice(0, 8)} — drop this file into Hillview's admin to apply`;
			// a short package must say so — the operator picked from a list
			// that promised more than the file contains
			exportSkipped = pkg.skipped ?? [];
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

<div class="row" style="gap:8px">
	<h1>Graduation</h1>
	<Help>
		<h4>what this page does</h4>
		<p>
			The one-way valve from workbench back to Hillview. Curation here never writes to
			the production database directly; this page derives what <i>would</i> change,
			bundles it into a reviewable package, and Hillview's admin applies it. Landing is
			then observed through the normal mirror sync — nothing is trusted blindly.
		</p>
		<h4>the three pending sections</h4>
		<dl>
			<dt>body rewrites</dt>
			<dd>
				annotations with an approved labelText / anchorCandidate fact: the facts are
				serialized back into the <span class="mono">name | context | … | lat, lon</span>
				body format. <b>driving facts</b> shows which approvals produced the change;
				the struck-through line is the current body being replaced (segments the parser
				doesn't recognize are preserved verbatim)
			</dd>
			<dt>new annotations</dt>
			<dd>
				workbench-native annotations (drawn in-bench or accepted transfers) to be
				created in Hillview, with their rect and body
			</dd>
			<dt>rect changes</dt>
			<dd>reshaped rectangles for existing annotations (struck-through = current rect)</dd>
			<dt>terrain overlays</dt>
			<dd>
				photos whose terrain overlay fit was approved on the overlay bench. The op carries
				a <b>baked</b> overlay — horizon elevation angle per azimuth + visible peak labels
				+ the DEM licence notice — so Hillview draws it with no depth buffer and no
				terrain worker. Landing compares the <b>fit alone</b>, so re-rendering the photo
				or nudging the horizon in Hillview never re-offers a settled overlay
			</dd>
		</dl>
		<h4>export package</h4>
		<p>
			Bundles the whole pending set into a JSON ops manifest + TriG provenance appendix.
			Each op carries a precondition on the current body/rect, so anything edited
			concurrently in Hillview is skipped, never clobbered. Drop the file into
			Hillview's admin; after the next sync, applied items disappear from pending
			("already reflected").
		</p>
	</Help>
</div>
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
		<h2 style="margin:0">Pending — {pendingCount}</h2>
		{#if pendingCount}
			<button class="primary" disabled={exporting} onclick={exportPackage}>
				{exporting ? 'building…' : `⬇ export package (${pendingCount})`}
			</button>
		{/if}
	</div>
	{#if exportMsg}
		<div class="muted" style="font-size:12px; margin:6px 0">{exportMsg}</div>
	{/if}
	{#if exportSkipped.length}
		<div class="card" style="border-color:var(--bad); font-size:12px; margin:6px 0">
			<b>{exportSkipped.length} overlay(s) left OUT of the package</b> — the export could not
			resolve them, so what you downloaded is short of the list above:
			<ul style="margin:4px 0 0 0; padding-left:18px">
				{#each exportSkipped as s (s.photo_id)}
					<li>
						<a href="/terrain/overlay?photo={s.photo_id}" class="mono">{s.photo_id.slice(0, 8)}</a>
						{#if s.photo_title}<span class="muted"> {s.photo_title}</span>{/if} — {s.error}
					</li>
				{/each}
			</ul>
		</div>
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

	{#if data.overlays.length}
		<h2 style="margin-top:18px">Terrain overlays to graduate — {data.overlays.length}</h2>
		<p class="muted" style="font-size:12px">
			photos with an <b>approved</b> terrain overlay fit (the “graduate” toggle on the
			overlay bench). The package carries a <i>baked</i> overlay — the fitted horizon
			resolved to an elevation angle per azimuth, plus the peak labels that were visible —
			so Hillview draws it without a depth buffer. Exporting re-reads the render, which
			takes a moment per photo.
		</p>
		<table>
			<thead>
				<tr><th>pano</th><th>photo</th><th>curated</th><th>fit</th><th>state</th></tr>
			</thead>
			<tbody>
				{#each data.overlays as o (o.photo_id)}
					<tr>
						<td style="width:76px">
							<a href="/photos/{o.photo_id}"><PhotoThumb sizes={o.sizes} size={70} /></a>
						</td>
						<td style="white-space:nowrap">
							<a href="/terrain/overlay?photo={o.photo_id}" class="mono" style="font-size:12px">
								{o.photo_id.slice(0, 8)}
							</a>
							{#if o.photo_title}
								<div class="muted" style="font-size:10px; max-width:180px; overflow:hidden; text-overflow:ellipsis">
									{o.photo_title}
								</div>
							{/if}
						</td>
						<td class="muted" style="white-space:nowrap; font-size:11px" title={o.decided_at ?? ''}>
							{ago(o.decided_at)}
						</td>
						<td class="mono" style="font-size:11px">
							{o.fit.projection} · {o.fit.fov_deg}° fov · bearing {o.fit.centre_bearing}° ·
							horizon {o.fit.horizon_pct}%
							{#if o.fit.visibility_km}· fog {o.fit.visibility_km} km{/if}
						</td>
						<td>
							<span class="pill" style="font-size:10px">
								{o.has_current ? 'update' : 'new'}
							</span>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}

	{#if data.overlays_landed.length}
		<h2 style="margin-top:18px">Terrain overlays already reflected — {data.overlays_landed.length}</h2>
		<p class="muted" style="font-size:12px">
			the approved fit matches the one Hillview holds (compared by fit alone — a
			re-render or a local horizon nudge there does not un-land an overlay)
		</p>
		<table>
			<tbody>
				{#each data.overlays_landed as o (o.photo_id)}
					<tr>
						<td style="width:56px">
							<a href="/photos/{o.photo_id}"><PhotoThumb sizes={o.sizes} size={46} /></a>
						</td>
						<td>
							<a href="/terrain/overlay?photo={o.photo_id}" class="mono" style="font-size:11px">
								{o.photo_id.slice(0, 8)}
							</a>
						</td>
						<td class="mono muted" style="font-size:11px">
							{o.fit.projection} · {o.fit.fov_deg}° · horizon {o.fit.horizon_pct}%
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

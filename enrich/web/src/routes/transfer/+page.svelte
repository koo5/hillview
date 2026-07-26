<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { apiBase } from '$lib/config';
	import Help from '$lib/components/Help.svelte';
	import OsdViewer, { type OsdRect, type OsdMark } from '$lib/components/OsdViewer.svelte';

	interface Rect {
		x: number;
		y: number;
		w: number;
		h: number;
	}
	interface XferResult {
		result_id: string;
		stage: string;
		window: number[] | null;
		status: string;
		raw: number | null;
		inliers: number | null;
		h_inliers: number;
		bbox: Rect | null;
		method: string | null;
		has_overlay: boolean;
		error: string | null;
	}
	interface Transfer {
		id: string;
		status: string;
		accepted_annotation_id: string | null;
		note: string | null;
		proposed_rect: Rect | null;
		proposed_stage: string | null;
		queued: number;
		results: XferResult[];
	}
	interface AnnEntry {
		id: string;
		body: string | null;
		rect: Rect | null;
		origin: string;
		azimuth: number | null;
		prediction: { x: number; slack_deg: number; dist_deg: number } | null;
		transfer?: Transfer;
	}
	interface PhotoMeta {
		id: string;
		title: string | null;
		width: number;
		height: number;
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		sizes: any;
	}
	interface Bench {
		target: PhotoMeta;
		donor_suggestions: { id: string; title: string | null; n: number }[];
		donors: { photo: PhotoMeta; calibration: { calibrated: boolean } | null; annotations: AnnEntry[] }[];
		datapoints: { az: number; x: number; h_inliers: number }[];
	}

	const CONF = 100;

	interface PhotoRow {
		id: string;
		title: string | null;
		place_name: string | null;
		width: number;
		height: number;
		n_annotations: number;
		calibrated: boolean;
	}

	let targetInput = $state('');
	let pickerOpen = $state(false);
	let pickerQ = $state('');
	let pickerRows = $state<PhotoRow[]>([]);
	let pickerTimer: ReturnType<typeof setTimeout> | null = null;
	let bench = $state<Bench | null>(null);
	let err = $state<string | null>(null);
	let sel = $state<string | null>(null); // selected annotation id
	let busy = $state(false);
	let autoRefine = $state(true);
	let nudged = $state<Record<string, Rect>>({}); // transfer id → user-adjusted rect
	let pollTimer: ReturnType<typeof setTimeout> | null = null;
	const refineRequested = new Set<string>();

	const target = $derived(page.url.searchParams.get('target'));

	function label(a: AnnEntry): string {
		const seg = (a.body ?? '').split('|')[0].trim();
		return seg && !seg.startsWith('http') ? seg : '(no label)';
	}
	const allAnns = $derived(bench?.donors.flatMap((d) => d.annotations) ?? []);
	const selEntry = $derived(allAnns.find((a) => a.id === sel) ?? null);
	const selDonor = $derived(
		bench?.donors.find((d) => d.annotations.some((a) => a.id === sel)) ?? null
	);
	const anyQueued = $derived(allAnns.some((a) => (a.transfer?.queued ?? 0) > 0));

	function bestOf(t: Transfer | undefined, stages: string[]): XferResult | null {
		if (!t) return null;
		const done = t.results.filter((r) => stages.includes(r.stage) && r.status === 'done' && r.bbox);
		return done.length ? done.reduce((a, b) => (b.h_inliers > a.h_inliers ? b : a)) : null;
	}
	function proposedRect(a: AnnEntry): Rect | null {
		const t = a.transfer;
		if (!t) return null;
		if (t.status === 'accepted' && t.proposed_rect) return t.proposed_rect;
		const ref = bestOf(t, ['refine']);
		if (ref && ref.h_inliers >= CONF) return ref.bbox;
		const coarse = bestOf(t, ['coarse', 'sweep']);
		return coarse && coarse.h_inliers >= CONF ? coarse.bbox : null;
	}
	function stateChip(a: AnnEntry): { text: string; cls: string } {
		const t = a.transfer;
		if (!t) return a.prediction ? { text: '—', cls: '' } : { text: 'no prior', cls: 'muted' };
		if (t.status === 'accepted') return { text: '✓ accepted', cls: 'ok' };
		if (t.status === 'rejected') return { text: '✗ rejected', cls: 'bad' };
		if (t.queued > 0) return { text: `⏳ ${t.queued} queued`, cls: 'warn' };
		const ref = bestOf(t, ['refine']);
		if (ref) return ref.h_inliers >= CONF
			? { text: `refined ${ref.h_inliers}`, cls: 'ok' }
			: { text: `refine weak ${ref.h_inliers}`, cls: 'warn' };
		const c = bestOf(t, ['coarse', 'sweep']);
		if (c) return c.h_inliers >= CONF
			? { text: `coarse ${c.h_inliers}`, cls: 'ok' }
			: { text: `weak ${c.h_inliers}`, cls: 'warn' };
		if (t.results.some((r) => r.status === 'error')) return { text: 'error', cls: 'bad' };
		return { text: '…', cls: 'muted' };
	}

	async function load() {
		if (!target) return;
		try {
			bench = await api.get<Bench>(`/transfer/bench?target=${target}`);
			err = null;
			maybeAutoRefine();
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
		schedulePoll();
	}
	function schedulePoll() {
		if (pollTimer) clearTimeout(pollTimer);
		if (anyQueued) pollTimer = setTimeout(load, 6000);
	}
	async function maybeAutoRefine() {
		if (!autoRefine || !bench) return;
		for (const a of allAnns) {
			const t = a.transfer;
			if (!t || t.status !== 'open' || t.queued > 0) continue;
			if (t.results.some((r) => r.stage === 'refine')) continue;
			const c = bestOf(t, ['coarse', 'sweep']);
			// big rects are already well-localized by the coarse pass
			if (!c || c.h_inliers < CONF || (c.bbox?.w ?? 0) >= 0.012) continue;
			if (refineRequested.has(t.id)) continue;
			refineRequested.add(t.id);
			try {
				await api.post('/transfer/refine', { transfer_id: t.id });
			} catch {
				/* surfaced on reload */
			}
		}
		schedulePoll();
	}

	async function runCoarseAll() {
		if (!bench) return;
		const ids = allAnns
			.filter((a) => a.prediction && (!a.transfer || (a.transfer.status === 'open' && !a.transfer.results.length)))
			.map((a) => a.id);
		if (!ids.length) return;
		busy = true;
		try {
			const res = await api.post<{ queued: unknown[]; skipped: { reason: string }[] }>(
				'/transfer/coarse',
				{ target, annotation_ids: ids }
			);
			if (res.skipped.length) err = `${res.skipped.length} skipped: ${res.skipped[0].reason}`;
			await load();
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			busy = false;
		}
	}
	async function runCoarseOne(a: AnnEntry) {
		busy = true;
		try {
			await api.post('/transfer/coarse', { target, annotation_ids: [a.id] });
			await load();
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			busy = false;
		}
	}
	async function runSweep(a: AnnEntry) {
		busy = true;
		try {
			await api.post('/transfer/sweep', { target, annotation_id: a.id });
			await load();
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			busy = false;
		}
	}
	async function runRefine(t: Transfer) {
		busy = true;
		try {
			await api.post('/transfer/refine', { transfer_id: t.id });
			await load();
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			busy = false;
		}
	}
	async function acceptSel() {
		const t = selEntry?.transfer;
		if (!t) return;
		busy = true;
		try {
			await api.post('/transfer/accept', {
				transfer_id: t.id,
				rect: nudged[t.id] ?? undefined,
				poi: true
			});
			await load();
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			busy = false;
		}
	}
	async function rejectSel() {
		const t = selEntry?.transfer;
		if (!t) return;
		await api.post('/transfer/reject', { transfer_id: t.id });
		await load();
	}
	async function reopenSel() {
		const t = selEntry?.transfer;
		if (!t) return;
		await api.post('/transfer/reopen', { transfer_id: t.id });
		await load();
	}

	// ---- review pane data ----
	const donorFull = $derived(selDonor?.photo.sizes?.full ?? null);
	const targetFull = $derived(bench?.target.sizes?.full ?? null);
	const donorRects = $derived<OsdRect[]>(
		selEntry?.rect
			? [{ id: 'donor', ...selEntry.rect, label: label(selEntry), kind: 'current' }]
			: []
	);
	const targetRect = $derived<Rect | null>(
		selEntry?.transfer
			? (nudged[selEntry.transfer.id] ?? proposedRect(selEntry))
			: null
	);
	const targetRects = $derived<OsdRect[]>(
		targetRect && selEntry
			? [{ id: 'proposal', ...targetRect, label: label(selEntry), kind: 'current' }]
			: []
	);
	const targetMarks = $derived<OsdMark[]>(
		selEntry?.prediction && !targetRect
			? [{ id: 'pred', x: selEntry.prediction.x, color: '#b48cff', label: 'predicted' }]
			: []
	);
	const bestResult = $derived(
		bestOf(selEntry?.transfer, ['refine']) ?? bestOf(selEntry?.transfer, ['coarse', 'sweep'])
	);
	function onNudge(id: string, targetObj: Record<string, unknown>) {
		const t = selEntry?.transfer;
		if (!t) return;
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		const g = (targetObj as any)?.selector?.geometry;
		if (g && typeof g.x === 'number') nudged = { ...nudged, [t.id]: { x: g.x, y: g.y, w: g.w, h: g.h } };
	}

	function go() {
		if (targetInput.trim()) goto(`?target=${targetInput.trim()}`, { noScroll: true });
	}
	async function searchPhotos() {
		try {
			pickerRows = (
				await api.get<{ photos: PhotoRow[] }>(
					`/photos?pano=true&q=${encodeURIComponent(pickerQ.trim())}`
				)
			).photos;
		} catch {
			pickerRows = [];
		}
	}
	function togglePicker() {
		pickerOpen = !pickerOpen;
		if (pickerOpen && !pickerRows.length) searchPhotos();
	}
	function pickTarget(id: string) {
		pickerOpen = false;
		goto(`?target=${id}`, { noScroll: true });
	}
	$effect(() => {
		void pickerQ;
		if (!pickerOpen) return;
		if (pickerTimer) clearTimeout(pickerTimer);
		pickerTimer = setTimeout(searchPhotos, 300);
	});

	onMount(() => {
		if (target) load();
	});
	$effect(() => {
		if (target) {
			targetInput = target;
			load();
		}
	});
	onDestroy(() => {
		if (pollTimer) clearTimeout(pollTimer);
	});
</script>

<div class="row" style="gap:8px">
	<h1>Transfer</h1>
	<Help>
		<h4>what this page does</h4>
		<p>
			Clones annotations from older <b>donor</b> panos onto a new <b>target</b> pano of
			the same spot, using MASt3R to find where each donor rectangle lands in the
			target. Pick the target (URL, search box, or browse ▾), donors within 200 m with
			annotations are suggested automatically.
		</p>
		<h4>the three stages</h4>
		<dl>
			<dt>sweep</dt>
			<dd>
				no prior yet: match one big annotation against ~14 overlapping windows across
				the whole target width. Wrong windows self-report via low inliers; the winner
				seeds the azimuth→x prior
			</dd>
			<dt>coarse</dt>
			<dd>
				for each annotation: predict its target-x from the prior, match a scale-matched
				~15° donor context against a windowed target crop, project the rect through the
				fitted homography
			</dd>
			<dt>refine</dt>
			<dd>
				tight second pass around the coarse hit (~10× the projected rect, matched
				scales) — runs automatically for small confident rects; the coarse homography
				alone carries ~0.1° model error, refine converges to ~0.02°
			</dd>
		</dl>
		<h4>the azimuth prior ("datapoints")</h4>
		<p>
			Every confident projection (≥ 100 homography inliers) from a <b>calibrated</b>
			donor becomes an (azimuth → target-x) datapoint; predictions use the nearest
			datapoint with slack growing by distance, so the prior is piecewise and absorbs
			stitching bends. Compass-only donors receive predictions but contribute nothing —
			their azimuth axis (±10°+ error) would corrupt the curve. Calibrate them first.
		</p>
		<h4>results table</h4>
		<dl>
			<dt>stage</dt>
			<dd>sweep / coarse / refine row for this annotation's transfer</dd>
			<dt>window</dt>
			<dd>the target crop the matcher searched (normalized x-range)</dd>
			<dt>raw / inliers / H-inl</dt>
			<dd>
				MASt3R correspondences / RANSAC-consistent pairs / pairs consistent with the
				final homography — H-inl ≥ 100 counts as confident
			</dd>
			<dt>bbox x</dt>
			<dd>where the projected rect landed; <b>overlay</b> shows the visual evidence</dd>
		</dl>
		<h4>review & accept</h4>
		<p>
			Top viewer = donor with the source rect; bottom = target with the editable
			proposal (violet mark = predicted x before coarse). Drag to nudge, then
			<b>accept</b>: creates a workbench-native clone of the donor body, an approved
			<span class="mono">derivedFrom</span> fact, and links both annotations to a shared
			POI (donor's reused, else minted). Flows into Hillview via the graduation
			create-annotation op. <b>reject</b> / <b>reopen</b> just flip the decision.
		</p>
	</Help>
</div>
<p class="muted">
	Clone annotations from donor panos onto a target pano of the same spot. Flow: <b>sweep</b> one
	big annotation once (seeds the azimuth→x prior) → <b>coarse</b> the rest (predicted window,
	scale-matched ~15° context) → auto-<b>refine</b> (tight second pass; the coarse homography
	carries ~0.1° model error) → review each proposal, nudge the rect if needed, <b>accept</b>
	(creates a workbench-native annotation + hv:derivedFrom + shared POI; graduates via the
	existing create-annotation op).
</p>

<div class="row" style="gap:8px; margin-bottom:10px">
	<input
		placeholder="target photo id…"
		bind:value={targetInput}
		onkeydown={(e) => e.key === 'Enter' && go()}
		style="width:340px"
	/>
	<button onclick={go}>open</button>
	<button onclick={togglePicker}>{pickerOpen ? '▴' : 'browse ▾'}</button>
	{#if bench}
		<span class="muted" style="font-size:12px">
			{bench.target.title ?? bench.target.id} · {bench.target.width}×{bench.target.height}
			· {bench.datapoints.length} datapoint{bench.datapoints.length === 1 ? '' : 's'}
			{#if bench.datapoints.length}
				(az {Math.min(...bench.datapoints.map((d) => d.az)).toFixed(0)}–{Math.max(
					...bench.datapoints.map((d) => d.az)
				).toFixed(0)}°)
			{/if}
		</span>
		<span style="flex:1"></span>
		<label class="muted" style="font-size:12px">
			<input type="checkbox" bind:checked={autoRefine} /> auto-refine
		</label>
		<button onclick={runCoarseAll} disabled={busy || !bench.datapoints.length}
			title="queue a coarse pass for every un-started annotation with a usable prior">
			▶ coarse all pending
		</button>
	{/if}
</div>

{#if pickerOpen}
	<div class="card" style="margin-bottom:10px; max-height:320px; overflow-y:auto">
		<input
			placeholder="search panos (title / place / id)…"
			bind:value={pickerQ}
			style="width:340px; margin-bottom:6px"
		/>
		<table>
			<thead><tr><th>pano</th><th>size</th><th>anns</th><th></th></tr></thead>
			<tbody>
				{#each pickerRows as p (p.id)}
					<tr style="cursor:pointer" onclick={() => pickTarget(p.id)}>
						<td style="font-size:12px">
							{p.title ?? p.id.slice(0, 8)}
							{#if p.place_name}<span class="muted" style="font-size:11px"> · {p.place_name}</span>{/if}
						</td>
						<td class="mono muted" style="font-size:11px">{p.width}×{p.height}</td>
						<td class="mono" style="font-size:11px">{p.n_annotations}</td>
						<td style="font-size:11px">{p.calibrated ? '🧭' : ''}</td>
					</tr>
				{/each}
				{#if !pickerRows.length}
					<tr><td class="muted" style="font-size:12px">no panos match</td></tr>
				{/if}
			</tbody>
		</table>
	</div>
{/if}

{#if err}<div class="card" style="border-color:var(--bad)">{err}</div>{/if}

{#if !target}
	<p class="muted">
		Enter the id of the pano to annotate (the big new one), e.g. from its
		<a href="/photos">photo page</a>.
	</p>
{:else if bench}
	<div class="row" style="align-items:flex-start; gap:16px">
		<div class="xfer-list">
			{#each bench.donors as d (d.photo.id)}
				<div class="donor-head">
					<a href="/photos/{d.photo.id}">{d.photo.title ?? d.photo.id.slice(0, 8)}</a>
					<span class="muted" style="font-size:11px">
						{d.annotations.length} ann ·
						{d.calibration?.calibrated ? 'calibrated' : '⚠ compass only'}
					</span>
				</div>
				<table>
					<tbody>
						{#each d.annotations as a (a.id)}
							{@const chip = stateChip(a)}
							<tr
								style="cursor:pointer; {sel === a.id ? 'background:var(--panel2)' : ''}"
								onclick={() => (sel = a.id)}
							>
								<td style="font-size:12px; max-width:190px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">
									{label(a)}
								</td>
								<td class="mono muted" style="font-size:11px">
									{a.azimuth != null ? a.azimuth.toFixed(1) + '°' : '—'}
								</td>
								<td style="font-size:11px" class={chip.cls}>{chip.text}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/each}
			{#if !bench.donors.length}
				<p class="muted" style="font-size:12px">no donor panos with annotations within 200 m</p>
			{/if}
		</div>

		<div style="flex:1; min-width:520px">
			{#if selEntry && selDonor}
				{@const t = selEntry.transfer}
				<div class="row" style="align-items:baseline; gap:10px; margin-bottom:4px">
					<b>{label(selEntry)}</b>
					<a class="mono muted" style="font-size:11px" href="/annotations/{selEntry.id}">
						{selEntry.id.slice(0, 8)}
					</a>
					{#if selEntry.azimuth != null}
						<span class="muted" style="font-size:12px">az {selEntry.azimuth}°</span>
					{/if}
					{#if selEntry.prediction}
						<span class="muted" style="font-size:12px">
							x̂ {selEntry.prediction.x.toFixed(3)} ±{selEntry.prediction.slack_deg.toFixed(1)}°
							(anchor {selEntry.prediction.dist_deg.toFixed(1)}° away)
						</span>
					{/if}
					<span style="flex:1"></span>
					{#if !t || (t.status === 'open' && !t.results.length)}
						<button onclick={() => runCoarseOne(selEntry)} disabled={busy || !selEntry.prediction}>
							▶ coarse
						</button>
						<button onclick={() => runSweep(selEntry)} disabled={busy}
							title="scan the whole target width — use once, on a big distinctive annotation">
							sweep
						</button>
					{:else if t.status === 'open'}
						<button onclick={() => runRefine(t)} disabled={busy || !bestOf(t, ['coarse', 'sweep'])}>
							🎯 refine
						</button>
						<button onclick={acceptSel} disabled={busy || !targetRect} class="ok">✓ accept</button>
						<button onclick={rejectSel} disabled={busy} class="bad">✗ reject</button>
					{:else}
						<button onclick={reopenSel} disabled={busy}>↺ reopen</button>
						{#if t.status === 'accepted' && t.accepted_annotation_id}
							<a href="/annotations/{t.accepted_annotation_id}" style="font-size:12px">clone ↗</a>
						{/if}
					{/if}
				</div>

				<div class="muted" style="font-size:11px; margin-bottom:4px">donor · {selDonor.photo.title}</div>
				{#if donorFull?.url}
					{#key selDonor.photo.id + selEntry.id}
						<OsdViewer
							pyramid={donorFull.pyramid ?? null}
							url={donorFull.url}
							width={selDonor.photo.width}
							height={selDonor.photo.height}
							rects={donorRects}
							focus={donorRects[0] ?? null}
							viewHeight={260}
						/>
					{/key}
				{/if}

				<div class="muted" style="font-size:11px; margin:8px 0 4px">
					target · {bench.target.title}
					{#if t && nudged[t.id]}
						· <span class="warn">nudged</span>
					{/if}
					{#if targetRect}
						· drag/resize the rect to adjust before accepting
					{/if}
				</div>
				{#if targetFull?.url}
					{#key bench.target.id + selEntry.id}
						<OsdViewer
							pyramid={targetFull.pyramid ?? null}
							url={targetFull.url}
							width={bench.target.width}
							height={bench.target.height}
							rects={targetRects}
							marks={targetMarks}
							focus={targetRects[0] ?? null}
							editable={t?.status === 'open' && !!targetRect}
							onedit={onNudge}
							viewHeight={260}
						/>
					{/key}
				{/if}

				{#if t?.results.length}
					<table style="margin-top:8px">
						<thead>
							<tr><th>stage</th><th>window</th><th>raw</th><th>inliers</th><th>H-inl</th><th>bbox x</th><th></th></tr>
						</thead>
						<tbody>
							{#each t.results as r (r.result_id)}
								<tr>
									<td style="font-size:12px">{r.stage}</td>
									<td class="mono muted" style="font-size:11px">
										{r.window ? `${r.window[0].toFixed(3)}+${r.window[2].toFixed(3)}` : '—'}
									</td>
									<td class="mono" style="font-size:12px">{r.raw ?? '…'}</td>
									<td class="mono" style="font-size:12px">{r.inliers ?? ''}</td>
									<td class="mono" style="font-size:12px">{r.h_inliers || ''}</td>
									<td class="mono" style="font-size:12px">
										{r.bbox ? r.bbox.x.toFixed(4) : r.error ? '⚠' : ''}
									</td>
									<td>
										{#if r.has_overlay}
											<a href="{apiBase}/matching/overlay/{r.result_id}" target="_blank" rel="noreferrer" style="font-size:11px">overlay ↗</a>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			{:else}
				<p class="muted">← pick an annotation</p>
			{/if}
		</div>
	</div>
{/if}

<style>
	.xfer-list {
		flex: 0 0 340px;
		max-height: calc(100vh - 210px);
		overflow-y: auto;
	}
	.donor-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		margin: 10px 0 4px;
	}
	.ok {
		color: var(--ok, #46c281);
	}
	.bad {
		color: var(--bad, #e0604f);
	}
	.warn {
		color: var(--warn, #e0a23a);
	}
</style>

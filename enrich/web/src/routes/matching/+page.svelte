<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { localStorageSharedStore } from '$lib/svelte-shared-store';
	import type { AnnotationList, AnnotationRow } from '$lib/types';
	import type { DziPyramid } from '$zoomview/tileSource';
	import CandidateMap from '$lib/components/CandidateMap.svelte';
	import OsdViewer, { type OsdRect } from '$lib/components/OsdViewer.svelte';
	import PhotoThumb from '$lib/components/PhotoThumb.svelte';

	interface ViewCandidate {
		photo_id: string;
		lat: number;
		lon: number;
		bearing: number;
		far_m: number | null;
		dist_m: number;
		off: number;
		ray_dist_m?: number;
		in_wedge?: boolean;
		hit_range?: [number, number] | null;
		pie?: { bearing: number; half: number; radius_m: number };
		title: string | null;
		width: number | null;
		height: number | null;
		sizes: Record<string, { url?: string }> | null;
		match: {
			id: string;
			status: string;
			raw_matches: number | null;
			inliers: number | null;
			ratio: number | null;
			overlay_path: string | null;
		} | null;
		verdict: string;
	}
	interface ViewResponse {
		mode: 'target' | 'ray' | 'bbox';
		target: { lat: number; lon: number; anchor: string; rule: string } | null;
		wedge:
			| {
					lat: number;
					lon: number;
					azimuth: number;
					half: number;
					near_m: number;
					far_m: number;
					calibrated: boolean;
					rect_x: number;
			  }
			| null;
		pano: {
			id: string;
			lat: number;
			lon: number;
			bearing: number | null;
			pie: { bearing: number; half: number; radius_m: number; calibrated: boolean } | null;
		};
		annotation_pie: { bearing: number; half: number; radius_m: number; calibrated: boolean } | null;
		total: number;
		candidates: ViewCandidate[];
	}

	const q = localStorageSharedStore('enrich_match_q', '');
	const knobs = localStorageSharedStore('enrich_match_knobs2', {
		slack: 2.0,
		half: 60,
		sameside: 90,
		limit: 40,
		// ray-mode knobs (used when the annotation has no anchor)
		near: 200,
		far: 15000,
		overlap: true,
		// bbox mode: candidates = whatever's in the map viewport (manual scan),
		// ignoring pie/ray/distance entirely
		bbox: false
	});

	// current map viewport, emitted by CandidateMap; used when bbox mode is on
	let mapBounds = $state<{ minlon: number; minlat: number; maxlon: number; maxlat: number } | null>(
		null
	);
	let bboxReloadTimer: ReturnType<typeof setTimeout> | null = null;

	let list = $state<AnnotationList | null>(null);
	let sel = $state<AnnotationRow | null>(null);
	let selDetail = $state<AnnotationRow | null>(null);
	let view = $state<ViewResponse | null>(null);
	let selCand = $state<string | null>(null);
	let inspect = $state<string | null>(null);
	let showMatchHelp = $state(false);
	let err = $state<string | null>(null);
	let loadingView = $state(false);
	let poller: ReturnType<typeof setInterval> | null = null;

	// side-by-side compare: pano region vs candidate photo (OsdViewer inputs)
	type Sizes = Record<string, { url?: string }> | null | undefined;
	const pyramidOf = (sizes: Sizes): DziPyramid | null => {
		const p = (sizes?.full as { pyramid?: DziPyramid } | undefined)?.pyramid;
		return p?.type === 'dzi' ? p : null;
	};
	const urlOf = (sizes: Sizes) => sizes?.full?.url ?? sizes?.['1024']?.url ?? '';
	const fallbackOf = (sizes: Sizes) => sizes?.['1024']?.url ?? sizes?.['640']?.url ?? null;

	const panoRect = $derived.by((): OsdRect | null => {
		const g = (selDetail?.target as { selector?: { geometry?: Record<string, number> } })
			?.selector?.geometry;
		if (!g || g.x == null) return null;
		const label = (selDetail?.body ?? '').split('|')[0].trim() || undefined;
		return { id: selDetail!.id, x: g.x, y: g.y ?? 0, w: g.w ?? 0.01, h: g.h ?? 0.1, label, kind: 'current' };
	});
	const inspectCand = $derived(
		(view?.candidates ?? []).find((c) => c.photo_id === inspect) ?? null
	);

	async function loadDetail(id: string) {
		try {
			selDetail = await api.get<AnnotationRow>(`/annotations/${id}`);
		} catch {
			selDetail = null;
		}
	}

	async function loadList() {
		const p = new URLSearchParams({ limit: '30' });
		if ($q) p.set('q', $q);
		list = await api.get<AnnotationList>(`/annotations?${p}`);
	}

	async function loadView() {
		if (!sel) return;
		loadingView = true;
		try {
			const k = $knobs;
			let p: URLSearchParams;
			if (k.bbox && mapBounds) {
				// map-area mode: candidates come from the current viewport, not the pie
				p = new URLSearchParams({
					mode: 'bbox',
					bbox: `${mapBounds.minlon},${mapBounds.minlat},${mapBounds.maxlon},${mapBounds.maxlat}`,
					limit: String(k.limit)
				});
			} else {
				p = new URLSearchParams({
					slack: String(k.slack),
					half: String(k.half),
					sameside: String(k.sameside),
					limit: String(k.limit),
					near_m: String(k.near),
					far_m: String(k.far),
					overlap: String(k.overlap)
				});
			}
			view = await api.get<ViewResponse>(`/annotations/${sel.id}/view_candidates?${p}`);
			err = null;
		} catch (e) {
			view = null;
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			loadingView = false;
		}
	}

	// map viewport changed: remember it; in bbox mode, re-query the visible area
	// (debounced so a pan/zoom gesture triggers one reload, not a storm)
	function onViewport(b: { minlon: number; minlat: number; maxlon: number; maxlat: number }) {
		mapBounds = b;
		if (!$knobs.bbox || !sel) return;
		if (bboxReloadTimer) clearTimeout(bboxReloadTimer);
		bboxReloadTimer = setTimeout(loadView, 450);
	}

	function select(a: AnnotationRow) {
		sel = a;
		selCand = null;
		inspect = null;
		selDetail = null;
		loadView();
		loadDetail(a.id);
	}
	// the annotation picker lives in a pop-up (☰), default closed — the page's
	// left column belongs to the candidate list
	let pickerOpen = $state(false);
	// selection is URL state (?annotation=…) so annotation pages can deep-link
	// here; the annotation need not be in the picker list — fetched directly
	function pick(a: AnnotationRow) {
		pickerOpen = false;
		goto(`?annotation=${a.id}`, { noScroll: true, keepFocus: true });
	}
	$effect(() => {
		const id = page.url.searchParams.get('annotation');
		if (id && id !== sel?.id) {
			api.get<AnnotationRow>(`/annotations/${id}`).then(select, () => {});
		}
	});

	async function verdict(photo_id: string, v: 'true' | 'false' | 'unset') {
		if (!sel) return;
		await api.post('/matching/verdict', { annotation_id: sel.id, photo_id, verdict: v });
		await loadView();
	}

	async function runMatch(photo_ids: string[]) {
		if (!sel || !photo_ids.length) return;
		await api.post('/matching/enqueue', { annotation_id: sel.id, photo_ids });
		await loadView();
	}

	// batch: every shown candidate that has no match job yet, in ray-dist order
	const unmatched = $derived((view?.candidates ?? []).filter((c) => !c.match));
	async function matchAll() {
		const n = unmatched.length;
		if (!n) return;
		const est = Math.round((n * 45) / 60);
		if (!confirm(`Enqueue ${n} MASt3R jobs? The worker is serial (~30–60 s/pair warm) — roughly ${est} min.`)) return;
		await runMatch(unmatched.map((c) => c.photo_id));
	}

	// poll while any match is queued; big batches don't need a 5s cadence
	// (view_candidates is a ~3s query — 30s is plenty for an hours-long run)
	let pollMs = 0;
	$effect(() => {
		const nQueued = view?.candidates.filter((c) => c.match?.status === 'queued').length ?? 0;
		const wanted = nQueued === 0 ? 0 : nQueued > 10 ? 30000 : 5000;
		if (wanted !== pollMs) {
			if (poller) {
				clearInterval(poller);
				poller = null;
			}
			if (wanted) poller = setInterval(loadView, wanted);
			pollMs = wanted;
		}
	});
	onDestroy(() => {
		if (poller) clearInterval(poller);
		if (bboxReloadTimer) clearTimeout(bboxReloadTimer);
	});

	function label(a: AnnotationRow): string {
		return (
			a.facts.find((f) => f.predicate === 'labelText' && f.status === 'approved')?.value ??
			a.facts.find((f) => f.predicate === 'labelText')?.value ??
			a.body ??
			'(unnamed)'
		);
	}
	const mapCandidates = $derived(
		(view?.candidates ?? []).map((c) => ({
			candidate: c.photo_id,
			fact: '',
			status: (c.verdict === 'approved'
				? 'approved'
				: c.verdict === 'rejected'
					? 'rejected'
					: 'proposed') as 'approved' | 'rejected' | 'proposed',
			lat: c.lat,
			lon: c.lon,
			displayName: `${c.photo_id.slice(0, 8)} · ${c.dist_m}m · Δ${c.off}°`,
			km: Math.round(c.dist_m / 10) / 100,
			bearing_offset: c.off,
			pie: c.pie
		}))
	);

	onMount(() => {
		loadList();
		if (!page.url.searchParams.get('annotation')) pickerOpen = true;
	});
	$effect(() => {
		void $q;
		loadList();
	});
</script>

<h1>Matching</h1>
<p class="muted">
	View-pie candidate gate (live knobs) → verdicts (the gold set) → MASt3R match jobs via the
	queue. Amber ring = target anchor; dots = candidate photos colored by verdict.
</p>

{#if err}<div class="card" style="border-color:var(--bad)">{err}</div>{/if}

<div class="row" style="margin-bottom:8px; position:relative">
	<button onclick={() => (pickerOpen = !pickerOpen)} title="pick an annotation">
		☰ annotations
	</button>
	{#if sel}
		<b>{label(sel)}</b>
		<span class="mono muted" style="font-size:11px">{sel.id.slice(0, 8)}</span>
		<a href="/annotations/{sel.id}">detail</a>
		<a href="/photos/{sel.photo_id}">pano</a>
		<a href="/geocode">geocode</a>
	{/if}
	{#if pickerOpen}
		<div
			class="card"
			style="position:absolute; top:calc(100% + 4px); left:0; z-index:1200; width:380px;
			max-height:65vh; overflow-y:auto; box-shadow:0 10px 30px rgba(0, 0, 0, 0.5)"
		>
			<input
				placeholder="search annotations…"
				value={$q}
				onchange={(e) => ($q = (e.target as HTMLInputElement).value)}
				style="width:100%; margin-bottom:8px"
			/>
			<table>
				<tbody>
					{#each list?.items ?? [] as a (a.id)}
						<tr
							style="cursor:pointer; {sel?.id === a.id ? 'background:var(--panel2)' : ''}"
							onclick={() => pick(a)}
						>
							<td style="width:56px"><PhotoThumb sizes={a.sizes} size={50} /></td>
							<td style="font-size:12px">{label(a)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

{#if sel}
	<div class="card row" style="gap:16px; font-size:12px; flex-wrap:wrap">
				<label title="ignore the view pie / ray — list every photo currently in the map viewport (manual visual scan by pan+zoom)">
					<input type="checkbox" bind:checked={$knobs.bbox} onchange={loadView} />
					<b>map area</b>
				</label>
				{#if !$knobs.bbox}
					<label>slack ×<input type="number" step="0.5" min="1" max="10" style="width:60px"
						bind:value={$knobs.slack} onchange={loadView} /></label>
					<label>±half °<input type="number" step="5" min="10" max="180" style="width:60px"
						bind:value={$knobs.half} onchange={loadView} /></label>
					{#if view?.mode !== 'ray'}
						<label>same-side °<input type="number" step="10" min="30" max="180" style="width:60px"
							bind:value={$knobs.sameside} onchange={loadView} /></label>
					{:else}
						<label>near m<input type="number" step="100" min="0" style="width:70px"
							bind:value={$knobs.near} onchange={loadView} /></label>
						<label>far m<input type="number" step="1000" min="500" style="width:80px"
							bind:value={$knobs.far} onchange={loadView} /></label>
						<label title="require the candidate's own view pie to see the ray (viewpie×viewpie); off = plain position-in-wedge">
							<input type="checkbox" bind:checked={$knobs.overlap} onchange={loadView} /> pie∩ray
						</label>
					{/if}
				{/if}
				<label>limit <input type="number" step="10" min="10" max="1000" style="width:60px"
					bind:value={$knobs.limit} onchange={loadView} /></label>
				{#if loadingView}<span class="muted">…</span>{/if}
				{#if unmatched.length}
					<button class="primary" style="font-size:12px" title="enqueue a MASt3R job for every shown candidate without one, best-ranked first"
						onclick={matchAll}>▶ match all {unmatched.length}</button>
				{/if}
				{#if view}
					<span class="muted">
						{view.total} candidates (showing {view.candidates.length}) ·
						{#if view.mode === 'bbox'}
							<b>map area</b> — every photo in the viewport (pan/zoom to change)
						{:else if view.mode === 'ray' && view.wedge}
							<b style="color:var(--warn)">ray</b> az {view.wedge.azimuth}° ±{view.wedge.half}°
							{view.wedge.calibrated ? '(calibrated)' : '(compass only!)'}
						{:else if view.target}
							target · anchor: {view.target.rule}
						{/if}
					</span>
				{/if}
			</div>

			{#if view}
				<!-- two independently-scrolling columns: candidate list left (order:1),
				     map + pairwise preview right (order:2 — source order kept so the
				     table block didn't have to move in the diff) -->
				<div class="row" style="align-items:stretch; gap:16px; height:calc(100vh - 235px); min-height:480px">
				<div style="flex:1; min-width:420px; order:2; overflow-y:auto">
				<CandidateMap
					photo={{ lat: view.pano.lat, lon: view.pano.lon, bearing: view.pano.bearing, pie: view.pano.pie }}
					candidates={mapCandidates}
					target={view.target ? { lat: view.target.lat, lon: view.target.lon, label: label(sel) } : null}
					wedge={view.wedge}
					annotationPie={view.annotation_pie}
					selected={selCand}
					onselect={(c) => (selCand = c)}
					fit={!$knobs.bbox}
					onviewport={onViewport}
				/>
				<p class="muted" style="font-size:11px; margin:3px 0 0">
					dashed blue = pano's view pie{view.pano.pie?.calibrated ? ' (calibrated FOV)' : ''} ·
					<span style="color:#b48cff">violet</span> = this annotation's exact rect slice (solid ray = its sight-line) ·
					hover a candidate for its pie{view.mode === 'ray' ? ' · amber = padded search wedge' : ''}
				</p>

				{#if selDetail && (pyramidOf(selDetail.sizes) || urlOf(selDetail.sizes)) && selDetail.width && selDetail.height}
					<div class="row" style="gap:10px; margin-top:10px; align-items:flex-start">
						<div style="flex:1; min-width:300px">
							<div class="muted" style="font-size:11px; margin-bottom:2px">
								annotation region — <a href="/photos/{selDetail.photo_id}">pano</a>
							</div>
							{#key selDetail.id}
								<OsdViewer
									pyramid={pyramidOf(selDetail.sizes)}
									url={urlOf(selDetail.sizes)}
									fallbackUrl={pyramidOf(selDetail.sizes) ? fallbackOf(selDetail.sizes) : null}
									width={pyramidOf(selDetail.sizes)?.width ?? selDetail.width}
									height={pyramidOf(selDetail.sizes)?.height ?? selDetail.height}
									rects={panoRect ? [panoRect] : []}
									focus={panoRect}
									viewHeight={230}
								/>
							{/key}
						</div>
						{#if inspectCand && inspectCand.width && inspectCand.height}
							<div style="flex:1; min-width:300px">
								<div class="muted" style="font-size:11px; margin-bottom:2px">
									candidate <a href="/photos/{inspectCand.photo_id}" class="mono">{inspectCand.photo_id.slice(0, 8)}</a>
									{inspectCand.title ?? ''}
								</div>
								{#key inspect}
									<OsdViewer
										pyramid={pyramidOf(inspectCand.sizes)}
										url={urlOf(inspectCand.sizes)}
										fallbackUrl={pyramidOf(inspectCand.sizes) ? fallbackOf(inspectCand.sizes) : null}
										width={pyramidOf(inspectCand.sizes)?.width ?? inspectCand.width}
										height={pyramidOf(inspectCand.sizes)?.height ?? inspectCand.height}
										viewHeight={230}
									/>
								{/key}
							</div>
						{:else}
							<div
								class="muted"
								style="flex:1; min-width:300px; display:flex; align-items:center; justify-content:center; height:230px; border:1px dashed var(--border); border-radius:8px; font-size:12px"
							>
								⊙ a candidate to compare side-by-side
							</div>
						{/if}
					</div>
				{/if}
				</div>

				<div class="candlist" style="flex:0 0 520px; order:1; overflow-y:auto">
				{#if showMatchHelp}
					<div class="card muted" style="position:sticky; top:0; z-index:30; font-size:12px; line-height:1.55; margin-bottom:8px">
						<p style="margin-top:0">
							<b>match</b>, e.g. <span class="mono">13/24 = 54%</span>: the worker feeds the
							annotation crop and the candidate photo (both resized to 512&nbsp;px) through
							<b>MASt3R</b>, which proposes point correspondences — the right number
							(<b>24 raw</b>) counts reciprocal nearest-neighbour descriptor pairs. RANSAC then
							fits a fundamental matrix — a single rigid two-camera geometry, 3&nbsp;px
							tolerance — and the left number (<b>13 inliers</b>) counts pairs consistent with
							it. The <b>%</b> is inliers/raw: geometric coherence, shown green from 50%.
						</p>
						<p>
							Read it as: raw = "how much looked similar", inliers = "how much of that agrees
							on one viewing geometry". Strong = high raw <i>and</i> high&nbsp;% (300/500). A
							high&nbsp;% on a tiny raw count is noise — below 8 raw pairs RANSAC can't run at
							all and inliers is 0. <b>overlay</b> opens the side-by-side image: green lines =
							inliers, red = rejected pairs (drawn only when sparse).
						</p>
						<p style="margin-bottom:0">
							Caution: repetitive or generic structures (chimneys, towers, façade grids) can
							produce geometrically coherent <i>false</i> matches — the numbers rank, but your
							✓/✗ verdicts are the gate that builds the gold set.
						</p>
					</div>
				{/if}
				<table>
					<thead>
						<tr>
							<th>photo</th>
							<th>{view.mode === 'ray' ? 'ray dist' : 'dist'}</th>
							<th>Δ°</th>
							<th>match
								<button title="what do these numbers mean?"
									style="font-size:11px; padding:0 7px; border-radius:50%"
									onclick={() => (showMatchHelp = !showMatchHelp)}>?</button>
							</th>
							<th>verdict</th>
						</tr>
					</thead>
					<tbody>
						{#each view.candidates as c (c.photo_id)}
							<tr style={selCand === c.photo_id ? 'background:var(--panel2)' : ''}
								onmouseenter={() => (selCand = c.photo_id)}>
								<td>
									<div class="row" style="gap:8px">
										<a href="/photos/{c.photo_id}" title="photo page"><PhotoThumb sizes={c.sizes} size={110} /></a>
										<div>
											<a href="/photos/{c.photo_id}" class="mono muted" style="font-size:10px">{c.photo_id.slice(0, 8)}</a>
											<button
												style="font-size:10px; padding:1px 7px; display:block; margin-top:3px; {inspect === c.photo_id ? 'border-color:var(--accent)' : ''}"
												title="side-by-side compare with the annotation region"
												onclick={() => (inspect = c.photo_id)}>⊙</button>
										</div>
									</div>
								</td>
								<td class="mono" title={c.hit_range ? `pie sees the ray at ${c.hit_range[0]}–${c.hit_range[1]} m` : undefined}>
									{c.ray_dist_m ?? c.dist_m}m
								</td>
								<td class="mono">{c.off}</td>
								<td style="font-size:12px">
									{#if c.match?.status === 'done'}
										<span class="mono" style={c.match.ratio != null && c.match.ratio >= 0.5 ? 'color:var(--ok)' : ''}>
											{c.match.inliers}/{c.match.raw_matches} = {Math.round((c.match.ratio ?? 0) * 100)}%
										</span>
										{#if c.match.overlay_path}
											· <a href="/api/matching/overlay/{c.match.id}" target="_blank" rel="noreferrer">overlay</a>
										{/if}
									{:else if c.match?.status === 'queued'}
										<span class="pill running">queued</span>
									{:else if c.match?.status === 'error'}
										<span class="pill bad" title={c.match.status}>error</span>
									{:else}
										<button onclick={() => runMatch([c.photo_id])}>match</button>
									{/if}
								</td>
								<td style="white-space:nowrap">
									{#if c.verdict === 'approved'}<span class="pill ok">true</span>
									{:else if c.verdict === 'rejected'}<span class="pill bad">false</span>{/if}
									{#if c.verdict !== 'approved'}
										<button title="true pair" onclick={() => verdict(c.photo_id, 'true')}>✓</button>
									{/if}
									{#if c.verdict !== 'rejected'}
										<button title="false pair" onclick={() => verdict(c.photo_id, 'false')}>✗</button>
									{/if}
									{#if c.verdict === 'approved' || c.verdict === 'rejected'}
										<button title="reset" onclick={() => verdict(c.photo_id, 'unset')}>↺</button>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
				</div>
				</div>
			{/if}
{:else}
	<p class="muted">☰ pick an annotation — anchored ones gate by a target ring; bare “?” rects run in ray mode</p>
{/if}

<style>
	/* keep the column headers readable while the candidate list scrolls */
	.candlist thead th {
		position: sticky;
		top: 0;
		background: var(--panel2);
		z-index: 10;
	}
</style>

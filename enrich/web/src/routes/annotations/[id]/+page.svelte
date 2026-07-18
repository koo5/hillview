<script lang="ts">
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import type { AnnotationRow, Candidate, CandidatesResponse } from '$lib/types';
	import type { DziPyramid } from '$zoomview/tileSource';
	import CandidateMap from '$lib/components/CandidateMap.svelte';
	import FactChip from '$lib/components/FactChip.svelte';
	import OsdViewer, { type OsdRect } from '$lib/components/OsdViewer.svelte';
	import PhotoThumb from '$lib/components/PhotoThumb.svelte';

	interface Suggestion {
		candidate: string;
		osm_type: string;
		osm_id: number;
		lat: number;
		lon: number;
		display_name: string;
		type: string;
		importance: number;
		km?: number;
		bearing_offset?: number;
		x_pred?: number;
		dx?: number;
		in_view?: boolean;
		type_match?: boolean;
		already?: string | null;
		score: number;
	}
	interface SuggestResponse {
		query: string;
		rect_x: number | null;
		calibrated: boolean;
		suggestions: Suggestion[];
	}

	let ann = $state<AnnotationRow | null>(null);
	let err = $state<string | null>(null);
	let reparsing = $state(false);
	let showHelp = $state(false);

	// group the flat fact list: facts about the annotation itself (parser output)
	// vs anchorCandidate facts (geocode) with their candidate-metadata nested under
	// them (those facts' subject is the candidate URI, not the annotation)
	const isAboutAnn = (f: { subject?: string }) =>
		f.subject == null || f.subject.endsWith(`/annotation/${ann?.id}`);
	const candidateFacts = $derived((ann?.facts ?? []).filter((f) => f.predicate === 'anchorCandidate'));
	const candidateSet = $derived(new Set(candidateFacts.map((f) => f.value)));
	const verdictFacts = $derived((ann?.facts ?? []).filter((f) => f.predicate === 'depictedIn'));
	const parseFacts = $derived(
		(ann?.facts ?? []).filter(
			(f) =>
				f.predicate !== 'anchorCandidate' &&
				f.predicate !== 'depictedIn' &&
				f.predicate !== 'depicts' &&
				isAboutAnn(f)
		)
	);
	const otherFacts = $derived(
		(ann?.facts ?? []).filter(
			(f) =>
				f.predicate !== 'anchorCandidate' &&
				f.predicate !== 'depictedIn' &&
				!isAboutAnn(f) &&
				!candidateSet.has(f.subject ?? '')
		)
	);

	interface MatchResult {
		id: string;
		photo_id: string;
		status: string;
		raw_matches: number | null;
		inliers: number | null;
		ratio: number | null;
	}
	let matchResults = $state<MatchResult[]>([]);
	const metadataFor = (uri: string) => (ann?.facts ?? []).filter((f) => f.subject === uri);

	let cand = $state<CandidatesResponse | null>(null);
	let sugg = $state<SuggestResponse | null>(null);
	let sq = $state('');
	let suggesting = $state(false);
	let wq = $state('');
	let wikiBusy = $state(false);
	let wikiMsg = $state<string | null>(null);
	let proposedLabel = $state<string | null>(null);
	let pin = $state<{ lat: number; lon: number } | null>(null);
	let anchorBusy = $state(false);
	let selCand = $state<string | null>(null);

	async function load() {
		try {
			ann = await api.get<AnnotationRow>(`/annotations/${page.params.id}`);
			err = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
		try {
			cand = await api.get<CandidatesResponse>(`/annotations/${page.params.id}/candidates`);
		} catch {
			cand = null;
		}
		try {
			matchResults = await api.get<MatchResult[]>(
				`/matching/results?annotation_id=${page.params.id}`
			);
		} catch {
			matchResults = [];
		}
	}

	$effect(() => {
		void page.params.id;
		sugg = null;
		sq = '';
		pin = null;
		load();
		loadPois();
	});

	async function runSuggest() {
		suggesting = true;
		try {
			const qs = sq.trim() ? `?q=${encodeURIComponent(sq.trim())}` : '';
			sugg = await api.get<SuggestResponse>(`/annotations/${page.params.id}/suggest${qs}`);
			if (!sq.trim()) sq = sugg.query;
			err = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			suggesting = false;
		}
	}
	async function adopt(s: Suggestion) {
		anchorBusy = true;
		try {
			await api.post(`/annotations/${page.params.id}/anchor`, {
				candidate: {
					osm_type: s.osm_type,
					osm_id: s.osm_id,
					lat: s.lat,
					lon: s.lon,
					display_name: s.display_name,
					type: s.type
				}
			});
			await load();
			if (sugg) runSuggest();
		} finally {
			anchorBusy = false;
		}
	}
	async function pinHere() {
		if (!pin) return;
		anchorBusy = true;
		try {
			await api.post(`/annotations/${page.params.id}/anchor`, { point: pin });
			pin = null;
			await load();
		} finally {
			anchorBusy = false;
		}
	}

	const approvedAnchor = $derived(
		(cand?.candidates ?? []).find((c) => c.status === 'approved') ?? null
	);

	// hillview.cz zoomview deep link: the production viewer restores x1..y2
	// viewport bounds (OSD coords: x normalized to width, y scaled by aspect) —
	// open it pre-zoomed to this annotation's rect, padded
	const zoomViewUrl = $derived.by(() => {
		if (!ann || ann.lat == null || !annRect || !ann.width || !ann.height) return null;
		const a = ann.height / ann.width;
		const r = annRect;
		const pad = 0.5;
		const b = {
			x1: r.x - r.w * pad,
			y1: (r.y - r.h * pad) * a,
			x2: r.x + r.w * (1 + pad),
			y2: (r.y + r.h * (1 + pad)) * a
		};
		return (
			`https://hillview.cz/?lat=${ann.lat}&lon=${ann.lon}&zoom=18` +
			`&photo=${encodeURIComponent('hillview-' + ann.photo_id)}` +
			`&x1=${b.x1.toFixed(6)}&y1=${b.y1.toFixed(6)}&x2=${b.x2.toFixed(6)}&y2=${b.y2.toFixed(6)}`
		);
	});

	// deep-zoom viewer inputs (pyramid rides in sizes.full, untyped in Sizes)
	const pyramid = $derived.by(() => {
		const p = (ann?.sizes?.full as { pyramid?: DziPyramid } | undefined)?.pyramid;
		return p?.type === 'dzi' ? p : null;
	});
	const fullUrl = $derived(
		ann?.sizes?.full?.url ?? ann?.sizes?.['1024']?.url ?? null
	);
	const annRect = $derived.by((): OsdRect | null => {
		try {
			const g = (ann?.target as { selector?: { geometry?: Record<string, number> } })?.selector
				?.geometry;
			if (!g || g.x == null) return null;
			const label = (ann?.body ?? '').split('|')[0].trim() || undefined;
			return { id: ann!.id, x: g.x, y: g.y ?? 0, w: g.w ?? 0.01, h: g.h ?? 0.1, label, kind: 'current' };
		} catch {
			return null;
		}
	});
	// existing candidates ∪ suggestions (deduped) for the map
	const mapCandidates = $derived.by(() => {
		const seen = new Map<string, Candidate>();
		for (const c of cand?.candidates ?? []) if (c.lat != null) seen.set(c.candidate, c);
		for (const s of sugg?.suggestions ?? [])
			if (!seen.has(s.candidate))
				seen.set(s.candidate, {
					candidate: s.candidate,
					lat: s.lat,
					lon: s.lon,
					status: 'proposed',
					displayName: s.display_name,
					km: s.km,
					bearing_offset: s.bearing_offset
				} as Candidate);
		return [...seen.values()];
	});

	// the workbench-native name: approved labelText fact wins over the parser's,
	// which wins over the raw mirrored body
	const currentLabel = $derived(
		(ann?.facts ?? []).find((f) => f.predicate === 'labelText' && f.status === 'approved')
			?.value ??
			(ann?.facts ?? []).find((f) => f.predicate === 'labelText')?.value ??
			ann?.body ??
			''
	);
	async function setLabel(v: string) {
		if (!ann || !v.trim()) return;
		await api.post(`/annotations/${ann.id}/label`, { label: v.trim() });
		await load();
	}
	async function editLabel() {
		const v = prompt(
			'Label (saved as a curated labelText fact — the mirrored body is untouched until graduation; geocode follows this):',
			currentLabel
		);
		if (v == null) return;
		await setLabel(v);
	}
	async function adoptWikiLabel() {
		if (!proposedLabel) return;
		await setLabel(proposedLabel);
		proposedLabel = null;
	}
	// the Nominatim hit's leading name component — same text shown in the row
	const hitName = (s: Suggestion) => s.display_name.split(',')[0].trim();

	// POI relations for triangulation: this annotation may depict a shared POI
	interface PoiRow {
		poi_id: string;
		label: string | null;
		n_annotations: number;
	}
	let pois = $state<PoiRow[]>([]);
	let poiLabel = $state('');
	let relatePoiId = $state('');
	let poiBusy = $state(false);
	const depictsFacts = $derived((ann?.facts ?? []).filter((f) => f.predicate === 'depicts'));

	async function loadPois() {
		try {
			pois = (await api.get<{ pois: PoiRow[] }>('/pois')).pois;
		} catch {
			pois = [];
		}
	}
	async function createPoi() {
		if (!ann) return;
		poiBusy = true;
		try {
			await api.post('/pois', {
				label: poiLabel.trim() || null,
				annotation_ids: [ann.id]
			});
			poiLabel = '';
			await Promise.all([load(), loadPois()]);
		} finally {
			poiBusy = false;
		}
	}
	async function relateToPoi() {
		if (!ann || !relatePoiId) return;
		poiBusy = true;
		try {
			await api.post(`/pois/${relatePoiId}/annotations`, { annotation_id: ann.id });
			relatePoiId = '';
			await Promise.all([load(), loadPois()]);
		} finally {
			poiBusy = false;
		}
	}

	async function attachWiki() {
		if (!ann || !wq.trim()) return;
		wikiBusy = true;
		wikiMsg = null;
		proposedLabel = null;
		try {
			const r = await api.post<{ label: string; coords: { lat: number; lon: number } | null }>(
				`/annotations/${ann.id}/wikipedia`,
				{ url: wq.trim() }
			);
			const coordsMsg = r.coords
				? ` · coords ${r.coords.lat.toFixed(5)}, ${r.coords.lon.toFixed(5)} minted as a proposed candidate below`
				: ' (the page has no coordinates)';
			wikiMsg = `📖 ${r.label} attached${coordsMsg}`;
			// the page title is proposed as the label; offer adopt unless it's
			// already the approved name
			const approved = (ann.facts ?? []).find(
				(f) => f.predicate === 'labelText' && f.status === 'approved'
			)?.value;
			proposedLabel = r.label !== approved ? r.label : null;
			wq = '';
			await load();
		} catch (e) {
			wikiMsg = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			wikiBusy = false;
		}
	}

	async function reparse() {
		if (!ann) return;
		reparsing = true;
		try {
			await api.post('/parse/run', { scope: 'annotations', annotation_ids: [ann.id] });
			await load();
		} finally {
			reparsing = false;
		}
	}
</script>

{#if err}<div class="card" style="border-color:var(--bad)">{err}</div>{/if}

{#if ann}
	<div class="row" style="align-items:baseline">
		<h1 class="mono" style="font-size:16px">{ann.id.slice(0, 8)}</h1>
		{#if currentLabel && currentLabel !== ann.body}<b>{currentLabel}</b>{/if}
		<a href="/annotations">← back to list</a>
		<div style="flex:1"></div>
		<button onclick={editLabel} title="set the curated label (labelText fact)">✎ label</button>
		<button onclick={reparse} disabled={reparsing}>{reparsing ? 'parsing…' : 're-parse'}</button>
	</div>

	<div class="row" style="align-items:flex-start; gap:20px">
		<div style="flex:1; min-width:320px">
			<h2>Photo</h2>
			<div class="card">
				{#if (pyramid || fullUrl) && ann.width && ann.height}
					{#key ann.id}
						<OsdViewer
							pyramid={pyramid}
							url={fullUrl ?? ''}
							fallbackUrl={ann.sizes?.['640']?.url ?? ann.sizes?.['320']?.url ?? null}
							width={pyramid?.width ?? ann.width}
							height={pyramid?.height ?? ann.height}
							rects={annRect ? [annRect] : []}
							focus={annRect}
							viewHeight={320}
						/>
					{/key}
				{:else}
					<a href="/photos/{ann.photo_id}">
						<PhotoThumb sizes={ann.sizes} size={340} alt={ann.photo_title ?? ''} />
					</a>
				{/if}
				<table style="margin-top:8px">
					<tbody>
						<tr>
							<td class="muted">photo</td>
							<td><a href="/photos/{ann.photo_id}" class="mono">{ann.photo_id.slice(0, 8)} →</a></td>
						</tr>
						{#if ann.photo_title}<tr><td class="muted">title</td><td>{ann.photo_title}</td></tr>{/if}
						{#if ann.place_name}<tr><td class="muted">place</td><td>{ann.place_name}</td></tr>{/if}
						{#if ann.lat != null}
							<tr>
								<td class="muted">position</td>
								<td class="mono">{ann.lat?.toFixed(5)}, {ann.lon?.toFixed(5)}
									{ann.compass_angle != null ? ` · ${Math.round(ann.compass_angle)}°` : ''}</td>
							</tr>
						{/if}
						<tr>
							<td class="muted">links</td>
							<td>
								<a href={ann.web_url} target="_blank" rel="noreferrer">hillview.cz ↗</a>
								{#if zoomViewUrl}
									· <a href={zoomViewUrl} target="_blank" rel="noreferrer" title="open the production zoom view, pre-zoomed to this annotation's rect">zoomview ↗</a>
								{/if}
							</td>
						</tr>
					</tbody>
				</table>
			</div>

			<h2>Body</h2>
			<div class="card mono" style="font-size:13px">{ann.body || '(empty)'}</div>

			{#if (ann.history ?? []).length > 1}
				<h2>History</h2>
				<table>
					<tbody>
						{#each ann.history ?? [] as h (h.id)}
							<tr>
								<td class="muted mono" style="font-size:11px">{h.depth}</td>
								<td class="mono" style="font-size:12px">
									{#if h.id === ann.id}<b>{h.body}</b>{:else}
										<a href="/annotations/{h.id}">{h.body || '(empty)'}</a>{/if}
								</td>
								<td class="muted" style="font-size:11px">{h.event_type}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		</div>

		<div style="flex:1.2; min-width:360px">
			<h2>
				Facts <span class="muted" style="text-transform:none">— ✓ approve · ✗ reject · ↺ reset</span>
				<button
					onclick={() => (showHelp = !showHelp)}
					title="what are these?"
					style="font-size:11px; padding:0 7px; border-radius:50%">?</button>
			</h2>
			{#if showHelp}
				<div class="card muted" style="font-size:12px; line-height:1.55">
					<p style="margin-top:0">
						Each chip is one machine-derived statement, stored with provenance and a curation
						status (your ✓/✗ sticks to the statement itself and survives re-runs). Two
						processes produce them:
					</p>
					<p>
						<b>Parsed from the body</b> — a pure-text pass over the annotation body: label,
						context, embedded wikipedia link / coordinates, a cheap type guess. No external
						calls. Re-runnable via <i>re-parse</i> above or in bulk from the
						<a href="/annotations">annotations bench</a>.
					</p>
					<p>
						<b>Anchor candidates</b> — from a geocode run: the label is sent to
						<b>Nominatim</b> (OSM search, results cached), and if the body carries a
						wikipedia link its coordinates are fetched too. Each candidate is an OSM object
						or wikipedia page; the indented chips underneath (coords, display name, OSM
						type) describe <i>that candidate</i>, not the annotation.
					</p>
					<p style="margin-bottom:0">
						Approving one <span class="mono">anchorCandidate</span> designates it as THE
						real-world anchor — the same act as picking it on the
						<a href="/geocode">geocode bench's map</a> (two views of the same facts).
						Every fact links to the run that produced it — see <a href="/runs">runs</a>.
					</p>
				</div>
			{/if}
			{#if parseFacts.length}
				<h3 class="muted" style="font-size:11px; text-transform:uppercase; margin:10px 0 2px">parsed from body</h3>
				{#each parseFacts as f (f.fact)}
					<div style="margin:6px 0"><FactChip fact={f} interactive onchange={() => {}} /></div>
				{/each}
			{/if}
			{#if candidateFacts.length}
				<h3 class="muted" style="font-size:11px; text-transform:uppercase; margin:12px 0 2px">
					anchor candidates ({candidateFacts.length}) — approve one to set the anchor
				</h3>
				{#each candidateFacts as c (c.fact)}
					<div style="margin:8px 0 2px"><FactChip fact={c} interactive onchange={() => {}} /></div>
					<div style="margin-left:22px">
						{#each metadataFor(c.value) as f (f.fact)}
							<FactChip fact={f} interactive onchange={() => {}} />
						{/each}
					</div>
				{/each}
			{/if}
			{#if verdictFacts.length}
				<h3 class="muted" style="font-size:11px; text-transform:uppercase; margin:12px 0 2px">
					matching verdicts (gold set)
				</h3>
				{#each verdictFacts as f (f.fact)}
					<div style="margin:6px 0"><FactChip fact={f} interactive onchange={() => {}} /></div>
				{/each}
			{/if}
			{#if otherFacts.length}
				<h3 class="muted" style="font-size:11px; text-transform:uppercase; margin:12px 0 2px">other</h3>
				{#each otherFacts as f (f.fact)}
					<div style="margin:6px 0"><FactChip fact={f} interactive onchange={() => {}} /></div>
				{/each}
			{/if}
			{#if !ann.facts.length}
				<p class="muted">No facts yet — hit re-parse.</p>
			{/if}
		</div>
	</div>

	<h2 style="margin-top:16px">Anchor</h2>
	<p class="muted" style="font-size:12px; margin:2px 0 8px">
		{#if approvedAnchor}
			anchored to <span class="mono">{approvedAnchor.displayName ?? approvedAnchor.candidate}</span>
			({approvedAnchor.km ?? '?'} km) —
		{:else}
			no approved anchor yet —
		{/if}
		suggestions rank by view geometry (distance, bearing{sugg?.calibrated
			? ', predicted-x vs the drawn rect'
			: ''}); or click the map to pin the exact point.
	</p>
	<div class="row" style="align-items:flex-start; gap:18px">
		<div style="flex:1.1; min-width:360px">
			<div class="row">
				<input
					style="flex:1; min-width:200px"
					placeholder="search nominatim (default: the label)"
					bind:value={sq}
					onkeydown={(e) => e.key === 'Enter' && runSuggest()}
				/>
				<button onclick={runSuggest} disabled={suggesting}>
					{suggesting ? '…' : 'suggest'}
				</button>
			</div>
			<div class="row" style="margin-top:6px">
				<input
					style="flex:1; min-width:200px"
					placeholder="https://cs.wikipedia.org/wiki/… — attach the page (curated fact → body wiki segment on graduation)"
					bind:value={wq}
					onkeydown={(e) => e.key === 'Enter' && attachWiki()}
				/>
				<button onclick={attachWiki} disabled={wikiBusy}>{wikiBusy ? '…' : '📖 attach'}</button>
			</div>
			{#if wikiMsg}
				<div class="muted" style="font-size:11px; margin-top:3px">
					{wikiMsg}
					{#if proposedLabel}
						· <b>{proposedLabel}</b> proposed as label —
						<button style="font-size:10px; padding:0 7px" onclick={adoptWikiLabel}>✎ adopt as name</button>
					{/if}
				</div>
			{/if}
			{#if sugg}
				<table style="margin-top:8px">
					<thead><tr><th>score</th><th>hit</th><th>km</th><th>Δ°</th><th>Δx</th><th></th></tr></thead>
					<tbody>
						{#each sugg.suggestions as s (s.candidate)}
							<tr
								style={selCand === s.candidate ? 'background:var(--panel2)' : ''}
								onmouseenter={() => (selCand = s.candidate)}
							>
								<td class="mono" style={s.in_view === false ? 'color:var(--muted)' : ''}>{s.score.toFixed(2)}</td>
								<td style="max-width:280px">
									<a href={s.candidate} target="_blank" rel="noreferrer" style="font-size:12px">
										{hitName(s)}
									</a>
									<div class="muted" style="font-size:10px">
										{s.type}
										{#if s.type_match}<span class="pill ok" style="font-size:9px">type ✓</span>{/if}
										{#if s.in_view === false}<span class="pill" style="font-size:9px">out of view</span>{/if}
									</div>
								</td>
								<td class="mono" style="font-size:11px">{s.km ?? '—'}</td>
								<td class="mono" style="font-size:11px">{s.bearing_offset ?? '—'}</td>
								<td class="mono" style="font-size:11px">{s.dx ?? '—'}</td>
								<td style="white-space:nowrap">
									<button
										style="font-size:11px"
										title={`adopt "${hitName(s)}" as the label (curated name)`}
										onclick={() => setLabel(hitName(s))}>✎</button>
									{#if s.already === 'approved'}
										<span class="pill ok" style="font-size:10px">⚓</span>
									{:else}
										<button
											style="font-size:11px"
											disabled={anchorBusy}
											title="approve as THE anchor"
											onclick={() => adopt(s)}>⚓ set</button>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
			{#if pin}
				<div class="card row" style="margin-top:8px; align-items:center">
					<span class="mono" style="font-size:12px">📍 {pin.lat.toFixed(5)}, {pin.lon.toFixed(5)}</span>
					<button class="primary" disabled={anchorBusy} onclick={pinHere}>⚓ pin anchor here</button>
					<button onclick={() => (pin = null)}>cancel</button>
				</div>
			{/if}
		</div>
		<div style="flex:1; min-width:380px">
			{#if cand}
				<CandidateMap
					photo={cand.photo}
					candidates={mapCandidates}
					target={pin ? { lat: pin.lat, lon: pin.lon, label: 'pin' } : null}
					annotationPie={cand.annotation_pie}
					selected={selCand}
					onselect={(c) => (selCand = c)}
					onmapclick={(lat, lon) => (pin = { lat, lon })}
				/>
				<p class="muted" style="font-size:11px; margin-top:3px">
					green = approved · gray = proposed / suggestion · red = rejected ·
					<span style="color:#b48cff">violet ray</span> = the annotation's sight-line{cand.annotation_pie?.calibrated
						? ' (calibrated)'
						: ''} · dashed blue = pano view pie · click the map to place a pin (ideally along the ray)
				</p>
			{/if}
		</div>
	</div>

	<h2 style="margin-top:16px">
		POI / triangulation
		{#if depictsFacts.length}
			<a href="/triangulate?poi={depictsFacts[0].value.split('/').pop()}" style="font-size:13px; margin-left:10px; text-transform:none">triangulate →</a>
		{/if}
	</h2>
	<p class="muted" style="font-size:12px; margin:2px 0 8px">
		If this annotation and others depict the SAME real-world thing, relate them to one POI —
		then their sight-rays triangulate its location on the <a href="/triangulate">Triangulate</a> page.
	</p>
	{#if depictsFacts.length}
		<div class="card" style="font-size:12px">
			depicts:
			{#each depictsFacts as f (f.value)}
				<a href="/triangulate?poi={f.value.split('/').pop()}" class="mono">
					{pois.find((p) => f.value.endsWith(p.poi_id))?.label ?? f.value.split('/').pop()?.slice(0, 8)}
				</a>{' '}
			{/each}
		</div>
	{/if}
	<div class="card row" style="gap:14px; font-size:12px; flex-wrap:wrap; align-items:center">
		<div class="row" style="gap:6px">
			<input placeholder="new POI label (optional)" bind:value={poiLabel} style="width:200px" />
			<button disabled={poiBusy} onclick={createPoi}>＋ new POI from this annotation</button>
		</div>
		{#if pois.length}
			<div class="row" style="gap:6px">
				<span class="muted">or add to:</span>
				<select bind:value={relatePoiId} style="max-width:220px">
					<option value="">— existing POI —</option>
					{#each pois as p (p.poi_id)}
						<option value={p.poi_id}>{p.label ?? p.poi_id.slice(0, 8)} ({p.n_annotations})</option>
					{/each}
				</select>
				<button disabled={poiBusy || !relatePoiId} onclick={relateToPoi}>relate</button>
			</div>
		{/if}
	</div>

	<h2 style="margin-top:16px">
		Matching
		<a href="/matching?annotation={ann.id}" style="font-size:13px; margin-left:10px; text-transform:none">
			matching bench →
		</a>
	</h2>
	{#if matchResults.length}
		<table style="max-width:560px">
			<thead><tr><th>candidate</th><th>status</th><th>inliers</th></tr></thead>
			<tbody>
				{#each matchResults.slice(0, 8) as m (m.id)}
					<tr>
						<td><a href="/photos/{m.photo_id}" class="mono" style="font-size:12px">{m.photo_id.slice(0, 8)}</a></td>
						<td style="font-size:12px">{m.status}</td>
						<td class="mono" style="font-size:12px">
							{#if m.status === 'done'}
								{m.inliers}/{m.raw_matches} = {Math.round((m.ratio ?? 0) * 100)}%
							{:else}—{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{#if matchResults.length > 8}
			<p class="muted" style="font-size:11px">…{matchResults.length - 8} more on the bench</p>
		{/if}
	{:else}
		<p class="muted" style="font-size:12px">
			no match evidence yet — the bench finds candidate photos
			({approvedAnchor ? 'target mode: pie gate against the anchor' : "ray mode: this annotation has no anchor, so candidates come from the pano's sight ray through the rect"})
			and queues MASt3R pair matches.
		</p>
	{/if}
{/if}

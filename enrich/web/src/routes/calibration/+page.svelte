<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { fitRectilinear, fitSummary, residual } from '$lib/theilsen';
	import CalibScatter from '$lib/components/CalibScatter.svelte';
	import Help from '$lib/components/Help.svelte';
	import PhotoThumb from '$lib/components/PhotoThumb.svelte';

	interface Pano {
		id: string;
		title: string | null;
		n_annotations: number;
		calibrated: boolean;
		compass_angle: number | null;
		sizes: Record<string, { url?: string }> | null;
	}
	interface CalRow {
		annotation_id: string;
		body: string;
		rect_x: number | null;
		rule: string;
		anchor: { candidate: string; displayName?: string; status: string } | null;
		azimuth: number | null;
		delta: number | null;
		km: number | null;
		usable: boolean;
	}
	interface CalData {
		photo: {
			id: string;
			title: string | null;
			compass_angle: number | null;
			sizes: Record<string, { url?: string }> | null;
		};
		rows: CalRow[];
	}

	let panos = $state<Pano[]>([]);
	let sel = $state<Pano | null>(null);
	let data = $state<CalData | null>(null);
	let excluded = $state<Set<string>>(new Set());
	let err = $state<string | null>(null);
	let accepting = $state(false);
	let accepted = $state<string | null>(null);

	// azimuth↔x law: linear for cylindrical/equirect stitches (f1/f2), atan
	// for rectilinear (f0) — per pano, read off the .pto p-line, never assume
	let model = $state<'linear' | 'rectilinear'>('linear');
	function fitWith(pts: { x: number; delta: number }[]) {
		const compass = data?.photo.compass_angle ?? null;
		return model === 'rectilinear' ? fitRectilinear(pts, compass) : fitSummary(pts, compass);
	}

	const usableRows = $derived((data?.rows ?? []).filter((r) => r.usable));
	const unusableRows = $derived((data?.rows ?? []).filter((r) => !r.usable));
	// rule "none" = no located candidate at all — the geocoder has not run on these
	// (distinct from an anchor that exists but was rejected or judged out of view)
	const noAnchorRows = $derived(unusableRows.filter((r) => r.rule === 'none'));
	const includedRows = $derived(usableRows.filter((r) => !excluded.has(r.annotation_id)));
	const fit = $derived(fitWith(includedRows.map((r) => ({ x: r.rect_x!, delta: r.delta! }))));
	const scatterPoints = $derived(
		usableRows.map((r) => ({
			id: r.annotation_id,
			x: r.rect_x!,
			delta: r.delta!,
			label: r.body,
			included: !excluded.has(r.annotation_id)
		}))
	);

	function rowResidual(r: CalRow): number | null {
		if (!fit || excluded.has(r.annotation_id) || r.rect_x == null || r.delta == null) return null;
		return residual({ x: r.rect_x, delta: r.delta }, fit);
	}

	// the include/exclude working set persists per pano in REAL TIME as a
	// server-side draft (plain mutable RDF in a per-pano draft graph), so it
	// survives reloads, pano switches, and browser/device changes
	async function loadDraft(id: string): Promise<Set<string>> {
		try {
			const d = await api.get<{ excluded: string[] }>(`/calibrate/draft?photo_id=${id}`);
			return new Set(d.excluded);
		} catch {
			return new Set();
		}
	}
	function saveDraft() {
		if (!sel) return;
		api.put(`/calibrate/draft`, { photo_id: sel.id, excluded: [...excluded] }).catch(() => {
			/* draft save is best-effort */
		});
	}

	async function loadPanos() {
		panos = await api.get<Pano[]>('/panos');
	}
	async function select(p: Pano) {
		sel = p;
		data = null;
		excluded = new Set();
		accepted = null;
		const draft = loadDraft(p.id);
		try {
			data = await api.get<CalData>(`/panos/${p.id}/calibration`);
			err = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
		excluded = await draft;
	}

	// re-pick anchors + rows server-side WITHOUT touching the selection —
	// for after approving/pinning an annotation's coords in another tab
	let refreshing = $state(false);
	async function refresh() {
		if (!sel) return;
		refreshing = true;
		try {
			data = await api.get<CalData>(`/panos/${sel.id}/calibration`);
			err = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			refreshing = false;
		}
	}
	// Anchors come from anchorCandidate facts, which only a GEOCODE run mints —
	// parse alone leaves freshly-imported annotations with rule "none". Scoped to
	// this pano so it never turns into an all-current external-lookup sweep.
	let geocoding = $state<string | null>(null);
	async function geocodePano() {
		if (!sel || geocoding) return;
		geocoding = 'starting…';
		try {
			const res = await api.post<{ run_id: string; annotations: number }>('/geocode/run', {
				scope: 'photo',
				photo_id: sel.id,
				note: 'from calibration bench'
			});
			// the run is a background task; poll it, then re-pick anchors
			for (;;) {
				await new Promise((r) => setTimeout(r, 1500));
				const run = await api.get<{ status: string; stats: { done?: number } | null; error: string | null }>(
					`/runs/${res.run_id}`
				);
				if (run.status === 'running') {
					geocoding = `${run.stats?.done ?? 0}/${res.annotations}…`;
					continue;
				}
				if (run.status === 'failed') err = `geocode run failed: ${run.error ?? ''}`;
				break;
			}
			await refresh();
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			geocoding = null;
		}
	}

	// selection lives in the URL (?pano=…) so pano links are shareable/reloadable
	function pick(p: Pano) {
		goto(`?pano=${p.id}`, { noScroll: true, keepFocus: true });
	}
	$effect(() => {
		const id = page.url.searchParams.get('pano');
		if (id && panos.length && id !== sel?.id) {
			const p = panos.find((x) => x.id === id);
			if (p) select(p);
		}
	});
	function toggle(id: string) {
		const s = new Set(excluded);
		if (s.has(id)) s.delete(id);
		else s.add(id);
		excluded = s;
		saveDraft();
	}
	function includeAll() {
		excluded = new Set();
		saveDraft();
	}
	function autoKick(threshold: number) {
		// exclude worst residuals iteratively until all |resid| <= threshold
		const s = new Set(excluded);
		for (let i = 0; i < 50; i++) {
			const rows = usableRows.filter((r) => !s.has(r.annotation_id));
			const f = fitWith(rows.map((r) => ({ x: r.rect_x!, delta: r.delta! })));
			if (!f || rows.length <= 3) break;
			const worst = rows.reduce((w, r) =>
				Math.abs(residual({ x: r.rect_x!, delta: r.delta! }, f)) >
				Math.abs(residual({ x: w.rect_x!, delta: w.delta! }, f))
					? r
					: w
			);
			if (Math.abs(residual({ x: worst.rect_x!, delta: worst.delta! }, f)) <= threshold) break;
			s.add(worst.annotation_id);
		}
		excluded = s;
		saveDraft();
	}

	async function acceptFit() {
		if (!sel || !fit) return;
		accepting = true;
		try {
			const res = await api.post<{ run_id: string; fit: Record<string, number> }>(
				'/calibrate/accept',
				{ photo_id: sel.id, annotation_ids: includedRows.map((r) => r.annotation_id), model }
			);
			accepted = `saved — run ${res.run_id.slice(0, 8)}, bearing ${res.fit.centre_bearing}°, FOV ${res.fit.fov}°`;
			loadPanos();
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			accepting = false;
		}
	}

	onMount(loadPanos);
	const f1 = (v: number | null | undefined) => (v == null ? '—' : v.toFixed(1));
</script>

<div class="row" style="gap:8px">
	<h1>Calibration</h1>
	<Help>
		<h4>what this page does</h4>
		<p>
			Turns a pano into a compass: fits a linear map from horizontal image position
			(rect-x, 0–1) to absolute azimuth, using the pano's own annotations as evidence.
			Each annotation with a geolocated anchor gives one point — where its rectangle
			sits in the image vs the true bearing from the pano's position to the anchor.
			The fit is Theil-Sen (median of pairwise slopes), so a few wrong anchors don't
			drag it; you exclude the rest by hand or with auto-kick.
		</p>
		<h4>pano list (left)</h4>
		<dl>
			<dt>pano</dt>
			<dd>title + short id; sorted most-annotated first (more annotations = better fit)</dd>
			<dt>anns</dt>
			<dd>current annotations on the pano</dd>
			<dt>🧭</dt>
			<dd>calibration facts already accepted for this pano</dd>
		</dl>
		<h4>fit stats</h4>
		<dl>
			<dt>FOV</dt>
			<dd>|slope| — angular width the full image spans</dd>
			<dt>centre bearing</dt>
			<dd>absolute azimuth at image centre (x = 0.5)</dd>
			<dt>bias vs compass</dt>
			<dd>fit centre minus the stored phone compass — how wrong the compass was</dd>
			<dt>RMS</dt>
			<dd>root-mean-square residual over the n included points</dd>
		</dl>
		<h4>scatter</h4>
		<p>
			x = rectangle centre across the image, y = Δ° (bearing to anchor relative to
			stored compass, wrapped ±180). Line = current fit. Click a point to
			exclude/re-include it — same as the table checkboxes.
		</p>
		<h4>table columns (sorted worst residual first)</h4>
		<dl>
			<dt>☑</dt>
			<dd>include this point in the fit</dd>
			<dt>annotation</dt>
			<dd>body text, with the chosen anchor's display name under it</dd>
			<dt>rule</dt>
			<dd>
				how the anchor was picked, in precedence order: <b>approved</b> (human-approved
				candidate) &gt; <b>pinned</b> (author coordinate / map pin) &gt;
				<b>wikipedia</b> &gt; <b>auto</b> (best in-view Nominatim hit by importance).
				Trust approved/pinned; treat auto with suspicion when the residual is large.
			</dd>
			<dt>km</dt>
			<dd>distance to the anchor. &lt; 0.2 km is unusable — "at camera", no azimuth signal</dd>
			<dt>Δ°</dt>
			<dd>bearing to anchor minus stored compass</dd>
			<dt>resid°</dt>
			<dd>distance from the current fit line; &gt; 10° highlighted amber</dd>
		</dl>
		<h4>model</h4>
		<p>
			The azimuth↔x law depends on the pano's stitch <b>output projection</b> — read the
			.pto p-line f-value, it varies per pano (see docs/pano-source-archaeology.md):
			<b>linear</b> fits cylindrical/equirect stitches (f1/f2); <b>rectilinear</b> (f0)
			fits Δ = atan(k·(x−x₀)) — needs ≥ 4 points and also reports x₀, the principal-point
			x. The tell for a wrong model: residuals <i>bow</i> — both ends one sign, the middle
			the other, worst on far approved anchors (a straight line through an atan curve).
			Accepting a rectilinear fit also writes calibratedProjection/calibratedX0 facts;
			FOV stays "azimuth span across the image", so pie consumers are unaffected.
		</p>
		<h4>actions</h4>
		<dl>
			<dt>↻ recalc</dt>
			<dd>
				re-pick anchors and recompute rows server-side, keeping your selection —
				use after approving/pinning an annotation's coords in another tab
			</dd>
			<dt>auto-kick &gt;10°</dt>
			<dd>iteratively exclude the worst residual until all are ≤ 10° (keeps ≥ 3 points)</dd>
			<dt>accept fit</dt>
			<dd>
				server-side refit over the included set → writes calibratedBearing /
				calibratedFov / calibrationRms facts, run-tracked
			</dd>
		</dl>
		<p>
			The include/exclude set is a per-pano <b>draft</b>: every toggle saves it
			server-side (a mutable draft graph in the store), so it survives reloads, pano
			switches, and browser/device changes (until you include all).
		</p>
		<h4>downstream</h4>
		<p>
			Calibration is what makes a pano's geometry trustworthy: the matching bench uses
			it for the view pie, triangulation for sight-rays, and the transfer bench only
			lets <i>calibrated</i> donors contribute azimuth datapoints to its prior.
		</p>
	</Help>
</div>
<p class="muted">
	Per-pano Theil-Sen fit: anchor azimuth vs rectangle-x. Click points or checkboxes to
	exclude outliers — the fit updates live. Accept writes calibration facts.
</p>

{#if err}<div class="card" style="border-color:var(--bad)">{err}</div>{/if}

<div class="row" style="align-items:flex-start; gap:18px">
	<div style="flex:0 0 330px">
		<table>
			<thead><tr><th>pano</th><th>anns</th><th></th></tr></thead>
			<tbody>
				{#each panos.filter((p) => p.n_annotations > 0) as p (p.id)}
					<tr
						style="cursor:pointer; {sel?.id === p.id ? 'background:var(--panel2)' : ''}"
						onclick={() => pick(p)}
					>
						<td>
							<div style="font-size:12px">{p.title ?? p.id.slice(0, 8)}</div>
							<div class="muted mono" style="font-size:10px">{p.id.slice(0, 8)}</div>
						</td>
						<td>{p.n_annotations}</td>
						<td>{p.calibrated ? '🧭' : ''}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<div style="flex:1; min-width:520px">
		{#if sel && data}
			<div class="row" style="margin-bottom:6px">
				<a href="/photos/{sel.id}"><PhotoThumb sizes={data.photo.sizes} size={70} /></a>
				<div>
					<b>{data.photo.title ?? sel.id.slice(0, 8)}</b>
					<a href="/photos/{sel.id}" style="font-size:12px; margin-left:8px">photo page →</a>
					<div class="muted" style="font-size:12px">
						stored compass {f1(data.photo.compass_angle)}° ·
						{usableRows.length}/{data.rows.length} anchors usable
					</div>
				</div>
			</div>

			<div class="row" style="margin:8px 0">
				<div class="stat"><div class="n">{f1(fit?.fov)}°</div><div class="l">FOV</div></div>
				<div class="stat"><div class="n">{f1(fit?.centre_bearing)}°</div><div class="l">centre bearing</div></div>
				<div class="stat"><div class="n">{f1(fit?.centre_bias)}°</div><div class="l">bias vs compass</div></div>
				<div class="stat"><div class="n">{f1(fit?.rms)}°</div><div class="l">RMS ({fit?.n ?? 0} pts)</div></div>
				{#if fit?.model === 'rectilinear'}
					<div class="stat"><div class="n">{fit.x0?.toFixed(3)}</div><div class="l">x₀ (proj centre)</div></div>
				{/if}
				<div style="flex:1"></div>
				<label style="font-size:12px; display:flex; align-items:center; gap:4px"
					title="The pano's stitch OUTPUT projection sets the azimuth↔x law: linear for cylindrical/equirect (f1/f2), atan for rectilinear (f0). Read the .pto p-line f-value — it varies per pano, never assume (docs/pano-source-archaeology.md). Symptom of the wrong model: residuals bow — both ends one sign, middle the other, worst on far APPROVED anchors. Rectilinear needs ≥ 4 included points.">
					model
					<select bind:value={model}>
						<option value="linear">linear — cylindrical/equirect (f1/f2)</option>
						<option value="rectilinear">rectilinear — f0, Δ = atan(k·(x−x₀))</option>
					</select>
				</label>
				{#if excluded.size}<span class="muted" style="font-size:11px">{excluded.size} excluded (kept as draft)</span>{/if}
				<button onclick={refresh} disabled={refreshing}
					title="re-pick anchors and recompute rows — use after approving/pinning coords in another tab; keeps your selection">
					{refreshing ? '↻ …' : '↻ recalc'}
				</button>
				<button onclick={geocodePano} disabled={!!geocoding}
					title="run the geocoder over THIS pano's annotations: mints anchorCandidate facts (body coords → geo: pin, wiki link → Wikipedia coords, label → Nominatim), then recalcs. Needed after new annotations arrive — parse alone gives them no anchor.">
					{geocoding ? `⌖ ${geocoding}` : '⌖ geocode pano'}
				</button>
				<button onclick={() => autoKick(10)} title="iteratively exclude worst residuals > 10°">auto-kick &gt;10°</button>
				<button onclick={includeAll} disabled={excluded.size === 0}>include all</button>
				<button class="primary" onclick={acceptFit} disabled={accepting || !fit}>
					{accepting ? 'saving…' : 'accept fit'}
				</button>
			</div>
			{#if accepted}<div class="card" style="border-color:var(--ok)">{accepted}</div>{/if}

			<CalibScatter points={scatterPoints} {fit} ontoggle={toggle} />

			<table style="margin-top:10px">
				<thead>
					<tr><th></th><th>annotation</th><th>rule</th><th>km</th><th>Δ°</th><th>resid°</th></tr>
				</thead>
				<tbody>
					{#each [...usableRows].sort((a, b) => Math.abs(rowResidual(b) ?? 0) - Math.abs(rowResidual(a) ?? 0)) as r (r.annotation_id)}
						{@const res = rowResidual(r)}
						<tr style={excluded.has(r.annotation_id) ? 'opacity:0.45' : ''}>
							<td>
								<input
									type="checkbox"
									checked={!excluded.has(r.annotation_id)}
									onchange={() => toggle(r.annotation_id)}
								/>
							</td>
							<td style="max-width:260px">
								<a href="/annotations/{r.annotation_id}" style="font-size:12px">{r.body || '(unnamed)'}</a>
								{#if r.anchor}
									<div class="muted" style="font-size:10px">
										{r.anchor.displayName ?? r.anchor.candidate.replace('https://', '')}
									</div>
								{/if}
							</td>
							<td><span class="pill {r.rule === 'approved' ? 'ok' : ''}" style="font-size:10px">{r.rule}</span></td>
							<td class="mono">{r.km}</td>
							<td class="mono">{f1(r.delta)}</td>
							<td class="mono" style={res != null && Math.abs(res) > 10 ? 'color:var(--warn)' : ''}>
								{res == null ? '—' : res.toFixed(1)}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
			{#if unusableRows.length}
				<p class="muted" style="font-size:12px">
					{unusableRows.length} annotations unusable
					(no anchor / bad rect / no compass): {unusableRows.map((r) => r.body || '(unnamed)').slice(0, 8).join(' · ')}…
				</p>
				{#if noAnchorRows.length}
					<p class="muted" style="font-size:12px">
						{noAnchorRows.length} of those have <b>no located candidate at all</b> — run
						<button onclick={geocodePano} disabled={!!geocoding} style="font-size:11px">
							{geocoding ? `⌖ ${geocoding}` : '⌖ geocode pano'}
						</button>
						to mint anchors for them.
					</p>
				{/if}
			{/if}
		{:else}
			<p class="muted">← pick a pano</p>
		{/if}
	</div>
</div>


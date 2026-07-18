<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { apiBase } from '$lib/config';
	import type { DziPyramid } from '$zoomview/tileSource';
	import CandidateMap from '$lib/components/CandidateMap.svelte';
	import FactChip from '$lib/components/FactChip.svelte';
	import OsdViewer, { type OsdMark, type OsdRect } from '$lib/components/OsdViewer.svelte';
	import PhotoThumb from '$lib/components/PhotoThumb.svelte';

	interface Fact {
		fact: string;
		predicate: string;
		value: string;
		value_type: 'uri' | 'literal';
		datatype: string | null;
		status: 'proposed' | 'approved' | 'rejected';
	}
	interface Ann {
		id: string;
		body: string | null;
		is_current: boolean;
		created_at: string | null;
		missing: boolean;
		origin: string; // 'hillview' | 'workbench'
		rect: { x: number; y?: number; w?: number; h?: number } | null;
		// approved reshape (pending graduation) for a mirrored annotation
		proposed_rect: { x: number; y: number; w: number; h: number } | null;
	}
	interface MatchRow {
		id: string;
		annotation_id: string;
		status: string;
		raw_matches: number | null;
		inliers: number | null;
		ratio: number | null;
		error: string | null;
		has_overlay: boolean;
		body: string | null;
		// as_pano:
		candidate_id?: string;
		candidate_title?: string | null;
		candidate_sizes?: Record<string, { url?: string }> | null;
		// as_candidate:
		pano_id?: string;
		pano_title?: string | null;
		pano_sizes?: Record<string, { url?: string }> | null;
		verdict?: string;
	}
	interface PhotoData {
		photo: {
			id: string;
			title: string | null;
			description: string | null;
			place_name: string | null;
			width: number | null;
			height: number | null;
			compass_angle: number | null;
			altitude: number | null;
			captured_at: string | null;
			missing_since: string | null;
			lon: number | null;
			lat: number | null;
			is_pano: boolean;
			web_url: string;
			sizes: Record<string, { url?: string }> | null;
			pie: { bearing: number; half: number; radius_m: number; calibrated: boolean } | null;
		};
		annotations: Ann[];
		facts: Fact[];
		matches: { as_pano: MatchRow[]; as_candidate: MatchRow[] };
	}
	interface Proto {
		proto: string;
		label: string | null;
		wikipedia_url: string | null;
		x: number | null;
		x_error: number | null;
		x_status?: string;
		facts: Fact[];
	}
	interface Placement {
		label: string;
		azimuth: number;
		km: number;
		delta_vs_compass: number | null;
		calibrated: boolean;
		x: number | null;
		x_error: number | null;
		in_frame: boolean | null;
		off_frame_deg: number | null;
		saved: { run_id: string; proto: string } | null;
	}

	let data = $state<PhotoData | null>(null);
	let protos = $state<Proto[]>([]);
	let err = $state<string | null>(null);
	let showOld = $state(false);
	let poiUrl = $state('');
	let poiFov = $state(90);
	let poiBusy = $state(false);
	let poiErr = $state<string | null>(null);
	let placement = $state<Placement | null>(null);

	const calibrated = $derived(data?.facts.some((f) => f.predicate === 'calibratedBearing' && f.status !== 'rejected') ?? false);

	async function load() {
		try {
			data = await api.get<PhotoData>(`/photos/${page.params.id}`);
			err = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		}
		loadProtos();
	}
	async function loadProtos() {
		try {
			protos = await api.get<Proto[]>(`/panos/${page.params.id}/protos`);
		} catch {
			/* decoration only */
		}
	}
	$effect(() => {
		void page.params.id;
		placement = null;
		poiErr = null;
		drawing = false;
		editMsg = null;
		load();
	});

	// draw a new workbench-native annotation on this photo (for triangulation etc.)
	let drawing = $state(false);
	let drawBusy = $state(false);
	let editMsg = $state<string | null>(null);
	async function saveDrawnRect(target: Record<string, unknown>) {
		if (!data) return;
		drawBusy = true;
		try {
			await api.post('/annotations/native', { photo_id: data.photo.id, body: '?', target });
			await load(); // the persisted rect returns via the rects prop
		} finally {
			drawBusy = false;
		}
	}

	// an existing rect was moved/resized. Native (workbench-drawn) → save in place;
	// mirrored (hillview) → can't persist here (the mirror faithfully copies the
	// source, and reconcile would revert it), so revert with a note.
	async function saveEditedRect(id: string, target: Record<string, unknown>) {
		const a = data?.annotations.find((x) => x.id === id);
		if (!a) return; // transient/unknown id — ignore
		drawBusy = true;
		try {
			if (a.origin === 'workbench') {
				await api.put(`/annotations/native/${id}`, { target });
				editMsg = null;
			} else {
				// mirrored hillview rect: can't reshape in place; record a curated
				// reshape proposal that graduates as a set_annotation_target op.
				// The view reverts to the current shape until the change lands.
				await api.post(`/annotations/${id}/geometry`, { target });
				editMsg = 'Hillview annotation — reshape proposed (shown as pending; graduates as a target change on the Graduation page).';
			}
			await load();
		} finally {
			drawBusy = false;
		}
	}
	async function deleteRect(id: string) {
		const a = data?.annotations.find((x) => x.id === id);
		if (!a) return;
		if (a.origin !== 'workbench') {
			editMsg = 'That is a Hillview annotation — delete it in Hillview. Reverted.';
			await load();
			return;
		}
		drawBusy = true;
		try {
			await api.del(`/annotations/native/${id}`);
			editMsg = null;
			await load();
		} finally {
			drawBusy = false;
		}
	}

	async function placePoi(save: boolean) {
		if (!data || !poiUrl.trim()) return;
		poiBusy = true;
		poiErr = null;
		try {
			placement = await api.post<Placement>(`/panos/${data.photo.id}/place_poi`, {
				wikipedia_url: poiUrl.trim(),
				save,
				assumed_fov: calibrated ? null : poiFov
			});
			if (save) loadProtos();
		} catch (e) {
			poiErr = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
		} finally {
			poiBusy = false;
		}
	}

	const stripUrl = $derived.by(() => {
		const sizes = data?.photo.sizes;
		if (!sizes) return null;
		for (const k of ['1024', 'full', '640', '320']) {
			const u = sizes[k]?.url;
			if (u) return u;
		}
		return null;
	});
	const shownAnns = $derived((data?.annotations ?? []).filter((a) => showOld || (a.is_current && !a.missing)));
	const rectAnns = $derived(shownAnns.filter((a) => a.rect && a.is_current && !a.missing));
	const protoColor = (p: Proto) =>
		p.x_status === 'approved' ? '#46c281' : p.x_status === 'rejected' ? '#e0603a' : '#6ca4ff';

	// deep-zoom viewer inputs
	const pyramid = $derived.by(() => {
		const p = (data?.photo.sizes?.full as { pyramid?: DziPyramid } | undefined)?.pyramid;
		return p?.type === 'dzi' ? p : null;
	});
	const osdRects = $derived.by((): OsdRect[] =>
		rectAnns.map((a) => {
			// show the PROPOSED shape when a reshape is pending graduation (so the
			// edit "sticks" visually), otherwise the mirror's current rect
			const r = a.proposed_rect ?? a.rect!;
			const base = (a.body ?? '').split('|')[0].trim();
			return {
				id: a.id,
				x: r.x,
				y: r.y ?? 0,
				w: r.w ?? 0.01,
				h: r.h ?? 0.1,
				label: a.proposed_rect ? `${base || '?'} · reshape pending` : base || undefined,
				kind: (a.proposed_rect ? 'current' : 'other') as 'current' | 'other'
			};
		})
	);
	const osdMarks = $derived.by((): OsdMark[] => {
		const out: OsdMark[] = protos
			.filter((pr) => pr.x != null)
			.map((pr) => ({
				id: pr.proto,
				x: pr.x!,
				color: protoColor(pr),
				label: pr.label ?? undefined,
				band:
					pr.x_error != null ? ([pr.x! - pr.x_error, pr.x! + pr.x_error] as [number, number]) : undefined
			}));
		if (placement?.x != null)
			out.push({
				id: 'poi-preview',
				x: placement.x,
				color: '#e0a23a',
				label: placement.label,
				band:
					placement.x_error != null
						? [placement.x - placement.x_error, placement.x + placement.x_error]
						: undefined
			});
		return out;
	});
	const f1 = (v: number | null | undefined) => (v == null ? '—' : v.toFixed(1));
	const pct = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);
</script>

{#if err}<div class="card" style="border-color:var(--bad)">{err}</div>{/if}

{#if data}
	{@const p = data.photo}
	<div class="row" style="align-items:baseline">
		<h1 style="font-size:17px">{p.title ?? p.id.slice(0, 8)}</h1>
		<span class="mono muted" style="font-size:11px">{p.id.slice(0, 8)}</span>
		{#if p.is_pano}<span class="pill" style="font-size:11px">pano</span>{/if}
		{#if calibrated}<span class="pill ok" style="font-size:11px">calibrated 🧭</span>{/if}
		{#if p.missing_since}<span class="pill" style="font-size:11px; border-color:var(--bad); color:var(--bad)">missing from source</span>{/if}
		<div style="flex:1"></div>
		{#if p.is_pano}<a href="/calibration?pano={p.id}">calibration bench →</a>{/if}
		<a href={p.web_url} target="_blank" rel="noreferrer">hillview.cz ↗</a>
	</div>
	<div class="muted" style="font-size:12px; margin:2px 0 10px">
		{p.width}×{p.height} · compass {f1(p.compass_angle)}°
		{#if p.altitude != null}· alt {f1(p.altitude)} m{/if}
		{#if p.place_name}· {p.place_name}{/if}
		{#if p.captured_at}· captured {String(p.captured_at).slice(0, 10)}{/if}
	</div>

	{#if (pyramid || stripUrl) && p.width && p.height}
		<div class="row" style="justify-content:space-between; align-items:center; margin-bottom:4px">
			<span class="muted" style="font-size:11px">
				{#if drawing}<b style="color:var(--accent, #6ca4ff)">editing</b> — drag empty space for a new rect, or move/resize a rect (Del removes){drawBusy ? ' · saving…' : ''}{:else}click a rect to open its annotation{/if}
			</span>
			<button
				class:primary={drawing}
				style="font-size:12px"
				title="edit mode: draw new rects, and move/resize/delete existing ones (workbench-drawn rects save; hillview rects revert)"
				onclick={() => {
					drawing = !drawing;
					editMsg = null;
				}}
			>
				{drawing ? '✓ done editing' : '✎ edit rects'}
			</button>
		</div>
		{#if editMsg}<div class="muted" style="font-size:11px; color:var(--warn, #e0a23a); margin-bottom:4px">{editMsg}</div>{/if}
		{#key p.id}
			<OsdViewer
				pyramid={pyramid}
				url={stripUrl ?? ''}
				fallbackUrl={pyramid ? stripUrl : null}
				width={pyramid?.width ?? p.width}
				height={pyramid?.height ?? p.height}
				rects={osdRects}
				marks={osdMarks}
				viewHeight={340}
				editable={drawing}
				ondraw={saveDrawnRect}
				onedit={saveEditedRect}
				ondelete={deleteRect}
				onrectclick={(id) => (drawing ? null : goto(`/annotations/${id}`))}
			/>
		{/key}
		<p class="muted" style="font-size:11px; margin:3px 0 0">
			{rectAnns.length} annotation rects · {protos.length} proto-annotations — in edit mode,
			draw new rects or adjust workbench-drawn ones (then label / relate to a POI on the detail page)
		</p>
	{/if}

	<div class="row" style="align-items:flex-start; gap:18px; margin-top:12px">
		<div style="flex:1; min-width:420px">
			<h2>Facts about this photo</h2>
			{#if data.facts.length}
				{#each data.facts as f (f.fact)}
					<FactChip fact={f} interactive onchange={load} />
				{/each}
			{:else}
				<p class="muted" style="font-size:12px">
					none yet{#if p.is_pano} — <a href="/calibration?pano={p.id}">accept a calibration fit</a>{/if}
				</p>
			{/if}

			{#if p.is_pano}
				<div class="card" style="margin-top:12px">
					<b>Place a POI</b>
					<p class="muted" style="font-size:12px; margin:4px 0 8px">
						The calibration run backwards: a wikipedia page's coordinates → predicted x on this
						pano. Save mints a proto-annotation (curatable facts; approved ones are future anchors).
					</p>
					<div class="row">
						<input
							style="flex:1; min-width:240px"
							placeholder="https://cs.wikipedia.org/wiki/Ještěd"
							bind:value={poiUrl}
							onkeydown={(e) => e.key === 'Enter' && placePoi(false)}
						/>
						{#if !calibrated}
							<label class="muted" style="font-size:12px">
								assumed FOV° <input type="number" style="width:64px" bind:value={poiFov} min="10" max="360" />
							</label>
						{/if}
						<button onclick={() => placePoi(false)} disabled={poiBusy || !poiUrl.trim()}>preview</button>
						<button class="primary" onclick={() => placePoi(true)} disabled={poiBusy || !poiUrl.trim()}>
							{poiBusy ? '…' : 'save proto'}
						</button>
					</div>
					{#if poiErr}<div class="card" style="border-color:var(--bad); margin-top:8px">{poiErr}</div>{/if}
					{#if placement}
						<div style="margin-top:8px; font-size:13px">
							<b>{placement.label}</b> — {placement.km} km, azimuth {f1(placement.azimuth)}°
							{#if placement.x != null}
								· x = {placement.x.toFixed(3)}{placement.x_error != null ? ` ± ${placement.x_error.toFixed(3)}` : ''}
								{#if placement.in_frame}
									<span class="pill ok" style="font-size:11px">in frame</span>
								{:else}
									<span class="pill" style="font-size:11px; border-color:var(--warn); color:var(--warn)">
										out of frame ({placement.off_frame_deg}° past the {(placement.x ?? 0) < 0 ? 'left' : 'right'} edge)
									</span>
								{/if}
								{#if !placement.calibrated}
									<span class="muted" style="font-size:11px">(compass + assumed FOV — no accepted calibration)</span>
								{/if}
							{:else}
								<span class="muted">no x — accept a calibration fit first (or set an assumed FOV)</span>
							{/if}
							{#if placement.saved}
								<span class="pill ok" style="font-size:11px">saved</span>
							{/if}
						</div>
					{/if}
				</div>

				{#if protos.length}
					<h2 style="margin-top:14px">Proto-annotations</h2>
					<table>
						<thead><tr><th>label</th><th>x</th><th>facts</th></tr></thead>
						<tbody>
							{#each protos as pr (pr.proto)}
								<tr>
									<td style="max-width:180px">
										{#if pr.wikipedia_url}
											<a href={pr.wikipedia_url} target="_blank" rel="noreferrer" style="font-size:12px">{pr.label ?? '?'}</a>
										{:else}
											<span style="font-size:12px">{pr.label ?? '?'}</span>
										{/if}
									</td>
									<td class="mono" style="white-space:nowrap">
										{pr.x?.toFixed(3) ?? '—'}{pr.x_error != null ? ` ±${pr.x_error.toFixed(3)}` : ''}
									</td>
									<td>
										{#each pr.facts.filter((f) => f.predicate !== 'type') as f (f.fact)}
											<FactChip fact={f} interactive onchange={loadProtos} />
										{/each}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			{/if}

			<div class="row" style="align-items:baseline; margin-top:14px">
				<h2>Annotations ({shownAnns.length})</h2>
				{#if data.annotations.length > shownAnns.length || showOld}
					<label class="muted" style="font-size:12px">
						<input type="checkbox" bind:checked={showOld} /> show superseded/missing
						({data.annotations.length} total)
					</label>
				{/if}
			</div>
			<table>
				<thead><tr><th>body</th><th>rect x</th><th></th></tr></thead>
				<tbody>
					{#each shownAnns as a (a.id)}
						<tr style={!a.is_current || a.missing ? 'opacity:0.5' : ''}>
							<td style="max-width:330px">
								<a href="/annotations/{a.id}" style="font-size:12px">{a.body || '(unnamed)'}</a>
								<a href="/matching?annotation={a.id}" class="muted" style="font-size:10px" title="matching bench">match ↗</a>
							</td>
							<td class="mono" style="font-size:11px">
								{a.rect ? pct(a.rect.x + (a.rect.w ?? 0) / 2) : '—'}
							</td>
							<td style="font-size:10px">
								{#if !a.is_current}<span class="pill">superseded</span>{/if}
								{#if a.missing}<span class="pill" style="border-color:var(--bad)">missing</span>{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<div style="flex:0 0 340px">
			{#if p.lat != null}
				<CandidateMap
					photo={{ lat: p.lat, lon: p.lon, bearing: p.compass_angle, pie: p.pie }}
					candidates={[]}
				/>
				<p class="muted mono" style="font-size:11px">
					{p.lat?.toFixed(5)}, {p.lon?.toFixed(5)}
					{#if p.pie}
						<span class="muted" style="font-family:inherit">
							· view pie {p.pie.calibrated ? 'calibrated' : 'compass'} ±{p.pie.half}° / {(p.pie.radius_m / 1000).toFixed(1)} km
						</span>
					{/if}
				</p>
			{:else}
				<p class="muted">no position</p>
			{/if}

			{#if data.matches.as_pano.length}
				<h2>Matches from this pano</h2>
				<table>
					<thead><tr><th>annotation</th><th>candidate</th><th>result</th></tr></thead>
					<tbody>
						{#each data.matches.as_pano as m (m.id)}
							<tr>
								<td style="max-width:120px"><a href="/annotations/{m.annotation_id}" style="font-size:11px">{m.body || m.annotation_id.slice(0, 8)}</a></td>
								<td>
									<a href="/photos/{m.candidate_id}">
										<PhotoThumb sizes={m.candidate_sizes ?? null} size={46} />
									</a>
								</td>
								<td style="font-size:11px">
									{#if m.status === 'done'}
										{m.inliers}/{m.raw_matches}
										{#if m.has_overlay}· <a href="{apiBase}/matching/overlay/{m.id}" target="_blank">overlay</a>{/if}
									{:else}{m.status}{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}

			{#if data.matches.as_candidate.length}
				<h2>Matched as candidate</h2>
				<table>
					<thead><tr><th>pano / annotation</th><th>result</th><th>verdict</th></tr></thead>
					<tbody>
						{#each data.matches.as_candidate as m (m.id)}
							<tr>
								<td style="max-width:140px">
									<a href="/photos/{m.pano_id}" style="font-size:11px">{m.pano_title ?? m.pano_id?.slice(0, 8)}</a>
									<div><a href="/annotations/{m.annotation_id}" class="muted" style="font-size:10px">{m.body || m.annotation_id.slice(0, 8)}</a></div>
								</td>
								<td style="font-size:11px">
									{#if m.status === 'done'}
										{m.inliers}/{m.raw_matches}
										{#if m.has_overlay}· <a href="{apiBase}/matching/overlay/{m.id}" target="_blank">overlay</a>{/if}
									{:else}{m.status}{/if}
								</td>
								<td>
									<span class="pill {m.verdict === 'approved' ? 'ok' : ''}" style="font-size:10px">{m.verdict}</span>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		</div>
	</div>
{/if}


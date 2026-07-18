<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api';
	import { fitSummary, residual } from '$lib/theilsen';
	import CalibScatter from '$lib/components/CalibScatter.svelte';
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

	const usableRows = $derived((data?.rows ?? []).filter((r) => r.usable));
	const includedRows = $derived(usableRows.filter((r) => !excluded.has(r.annotation_id)));
	const fit = $derived(
		fitSummary(
			includedRows.map((r) => ({ x: r.rect_x!, delta: r.delta! })),
			data?.photo.compass_angle ?? null
		)
	);
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

	async function loadPanos() {
		panos = await api.get<Pano[]>('/panos');
	}
	async function select(p: Pano) {
		sel = p;
		data = null;
		excluded = new Set();
		accepted = null;
		try {
			data = await api.get<CalData>(`/panos/${p.id}/calibration`);
			err = null;
		} catch (e) {
			err = e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
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
	}
	function autoKick(threshold: number) {
		// exclude worst residuals iteratively until all |resid| <= threshold
		const s = new Set(excluded);
		for (let i = 0; i < 50; i++) {
			const rows = usableRows.filter((r) => !s.has(r.annotation_id));
			const f = fitSummary(
				rows.map((r) => ({ x: r.rect_x!, delta: r.delta! })),
				data?.photo.compass_angle ?? null
			);
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
	}

	async function acceptFit() {
		if (!sel || !fit) return;
		accepting = true;
		try {
			const res = await api.post<{ run_id: string; fit: Record<string, number> }>(
				'/calibrate/accept',
				{ photo_id: sel.id, annotation_ids: includedRows.map((r) => r.annotation_id) }
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

<h1>Calibration</h1>
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
				<div style="flex:1"></div>
				<button onclick={() => autoKick(10)} title="iteratively exclude worst residuals > 10°">auto-kick &gt;10°</button>
				<button onclick={() => (excluded = new Set())} disabled={excluded.size === 0}>include all</button>
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
			{#if data.rows.some((r) => !r.usable)}
				<p class="muted" style="font-size:12px">
					{data.rows.filter((r) => !r.usable).length} annotations unusable
					(no anchor / bad rect / no compass): {data.rows.filter((r) => !r.usable).map((r) => r.body || '(unnamed)').slice(0, 8).join(' · ')}…
				</p>
			{/if}
		{:else}
			<p class="muted">← pick a pano</p>
		{/if}
	</div>
</div>


<script lang="ts">
	import type { FitSummary } from '$lib/theilsen';

	export interface ScatterPoint {
		id: string;
		x: number;
		delta: number;
		label: string;
		included: boolean;
	}

	let {
		points,
		fit,
		ontoggle
	}: {
		points: ScatterPoint[];
		fit: FitSummary | null;
		ontoggle?: (id: string) => void;
	} = $props();

	const W = 720,
		H = 340,
		M = { l: 46, r: 14, t: 12, b: 34 };
	const iw = W - M.l - M.r,
		ih = H - M.t - M.b;

	const ymin = $derived(Math.min(-10, ...points.map((p) => p.delta)) - 5);
	const ymax = $derived(Math.max(10, ...points.map((p) => p.delta)) + 5);
	const sx = (x: number) => M.l + x * iw;
	const sy = $derived((y: number) => M.t + ih - ((y - ymin) / (ymax - ymin)) * ih);

	const yticks = $derived.by(() => {
		const span = ymax - ymin;
		const step = span > 200 ? 60 : span > 100 ? 30 : span > 40 ? 15 : 5;
		const out: number[] = [];
		for (let v = Math.ceil(ymin / step) * step; v <= ymax; v += step) out.push(v);
		return out;
	});

	let hover = $state<ScatterPoint | null>(null);
</script>

<svg viewBox="0 0 {W} {H}" style="width:100%; background:var(--panel); border-radius:10px; border:1px solid var(--border)">
	<!-- recessive grid -->
	{#each yticks as t (t)}
		<line x1={M.l} x2={W - M.r} y1={sy(t)} y2={sy(t)} stroke="var(--border)" stroke-width="1" />
		<text x={M.l - 6} y={sy(t) + 4} text-anchor="end" font-size="10" fill="var(--muted)">{t}°</text>
	{/each}
	{#each [0, 0.25, 0.5, 0.75, 1] as t (t)}
		<line x1={sx(t)} x2={sx(t)} y1={M.t} y2={H - M.b} stroke="var(--border)" stroke-width="1" />
		<text x={sx(t)} y={H - M.b + 14} text-anchor="middle" font-size="10" fill="var(--muted)">{t}</text>
	{/each}
	<text x={M.l + iw / 2} y={H - 4} text-anchor="middle" font-size="11" fill="var(--muted)">
		rectangle centre x (0…1 across pano)
	</text>
	<text x="12" y={M.t + ih / 2} font-size="11" fill="var(--muted)" transform="rotate(-90 12 {M.t + ih / 2})" text-anchor="middle">
		Δ azimuth vs compass (°)
	</text>

	<!-- fit line + residual whiskers -->
	{#if fit}
		<line
			x1={sx(0)} y1={sy(fit.intercept)} x2={sx(1)} y2={sy(fit.intercept + fit.slope)}
			stroke="var(--accent)" stroke-width="2" opacity="0.85"
		/>
		{#each points.filter((p) => p.included) as p (p.id)}
			<line
				x1={sx(p.x)} y1={sy(p.delta)} x2={sx(p.x)} y2={sy(fit.intercept + fit.slope * p.x)}
				stroke="var(--muted)" stroke-width="1" opacity="0.35"
			/>
		{/each}
	{/if}

	<!-- points: filled accent = included, hollow gray = excluded; ≥8px hit target -->
	{#each points as p (p.id)}
		<circle
			cx={sx(p.x)} cy={sy(p.delta)} r={hover === p ? 7 : 5}
			fill={p.included ? 'var(--accent)' : 'transparent'}
			stroke={p.included ? 'var(--panel)' : 'var(--muted)'}
			stroke-width="2"
			style="cursor:pointer"
			role="button"
			tabindex="-1"
			onclick={() => ontoggle?.(p.id)}
			onkeydown={(e) => e.key === 'Enter' && ontoggle?.(p.id)}
			onmouseenter={() => (hover = p)}
			onmouseleave={() => (hover = null)}
		/>
	{/each}

	<!-- tooltip -->
	{#if hover}
		{@const tx = Math.min(sx(hover.x) + 10, W - 190)}
		{@const ty = Math.max(sy(hover.delta) - 34, 4)}
		<g pointer-events="none">
			<rect x={tx} y={ty} width="185" height="30" rx="5" fill="var(--panel2)" stroke="var(--border)" />
			<text x={tx + 7} y={ty + 12} font-size="10" fill="var(--fg)">{hover.label.slice(0, 30)}</text>
			<text x={tx + 7} y={ty + 24} font-size="10" fill="var(--muted)">
				x {hover.x.toFixed(3)} · Δ {hover.delta.toFixed(1)}°
				{fit && hover.included ? ` · resid ${(hover.delta - (fit.intercept + fit.slope * hover.x)).toFixed(1)}°` : ''}
			</text>
		</g>
	{/if}
</svg>

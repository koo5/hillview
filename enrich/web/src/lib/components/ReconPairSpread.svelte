<script lang="ts">
	// Per-pair error spread on a log axis — the reason the bench shows pairs at all.
	// A run-level median hides the tail, and a false link (the Doppelganger hazard) or a
	// collapsed segment shows up as a handful of pairs far to the right of an otherwise
	// tight cluster. Hover a dot for the pair; click to select it.
	type Pair = {
		i: number;
		j: number;
		n_corres: number;
		baseline_m?: number | null;
		degenerate_baseline?: boolean;
		reproj?: { median: number } | null;
		epipolar?: { median: number } | null;
	};
	let {
		pairs = [],
		metric = 'reproj',
		selected = null,
		onselect
	}: {
		pairs?: Pair[];
		metric?: 'reproj' | 'epipolar';
		selected?: string | null;
		onselect?: (key: string | null) => void;
	} = $props();

	const W = 900;
	const H = 108;
	const padL = 18;
	const padR = 54;
	const padB = 26;
	const rowY = 46;

	const vals = $derived(
		pairs
			.map((p) => ({ p, v: (metric === 'reproj' ? p.reproj : p.epipolar)?.median }))
			.filter((d): d is { p: Pair; v: number } => typeof d.v === 'number' && d.v > 0)
	);
	const lo = $derived(vals.length ? Math.min(...vals.map((d) => d.v)) * 0.6 : 0.1);
	const hi = $derived(vals.length ? Math.max(...vals.map((d) => d.v)) * 1.6 : 10);
	const a = $derived(Math.log10(lo));
	const b = $derived(Math.log10(hi));
	const median = $derived(
		vals.length
			? [...vals.map((d) => d.v)].sort((x, y) => x - y)[Math.floor(vals.length / 2)]
			: null
	);

	function x(v: number): number {
		return padL + ((Math.log10(Math.max(v, lo)) - a) / (b - a || 1)) * (W - padL - padR);
	}
	const ticks = $derived(
		[0.01, 0.1, 1, 10, 100, 1000, 10000, 100000].filter((t) => t >= lo && t <= hi)
	);
	const key = (p: Pair) => `${p.i}-${p.j}`;
	let hovered = $state<string | null>(null);
	const tipFor = $derived(vals.find((d) => key(d.p) === hovered));
</script>

<div class="wrap">
	<svg viewBox="0 0 {W} {H}" role="img" aria-label="per-pair error spread">
		{#each ticks as t (t)}
			<line class="grid" x1={x(t)} x2={x(t)} y1={rowY - 26} y2={rowY + 26} />
			<text class="tick" x={x(t)} y={H - padB + 16} text-anchor="middle">{t}</text>
		{/each}
		<text class="tick" x={W - padR + 8} y={H - padB + 16}>px</text>
		<line class="axis" x1={padL} x2={W - padR} y1={rowY} y2={rowY} />
		{#if median != null}
			<line class="med" x1={x(median)} x2={x(median)} y1={rowY - 22} y2={rowY + 22} />
			<text class="medlab" x={x(median)} y={rowY - 27} text-anchor="middle"
				>median {median.toFixed(2)}</text
			>
		{/if}
		{#each vals as d (key(d.p))}
			<circle
				class="dot"
				class:sel={selected === key(d.p)}
				class:degen={d.p.degenerate_baseline}
				cx={x(d.v)}
				cy={rowY}
				r={selected === key(d.p) ? 7 : 4.5}
				role="button"
				tabindex="0"
				aria-label="pair {d.p.i} to {d.p.j}"
				onmouseenter={() => (hovered = key(d.p))}
				onmouseleave={() => (hovered = null)}
				onfocus={() => (hovered = key(d.p))}
				onblur={() => (hovered = null)}
				onclick={() => onselect?.(selected === key(d.p) ? null : key(d.p))}
				onkeydown={(e) => e.key === 'Enter' && onselect?.(key(d.p))}
			/>
		{/each}
	</svg>
	{#if tipFor}
		<div class="tip">
			<b>{tipFor.v.toFixed(2)} px</b> · pair {tipFor.p.i}→{tipFor.p.j} ·
			{tipFor.p.n_corres.toLocaleString()} corres{#if tipFor.p.baseline_m != null}
				· baseline {tipFor.p.baseline_m} m{/if}
		</div>
	{:else}
		<div class="tip muted">
			{vals.length} pairs · hover a dot for its pair, click to pin it in the table below
		</div>
	{/if}
</div>

<style>
	.wrap {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	svg {
		width: 100%;
		height: auto;
	}
	.grid {
		stroke: var(--line, #2c2c2a);
		stroke-width: 1;
	}
	.axis {
		stroke: var(--line, #383835);
		stroke-width: 1;
		opacity: 0.6;
	}
	.med {
		stroke: currentColor;
		stroke-width: 2;
		opacity: 0.8;
	}
	.medlab,
	.tick {
		fill: var(--muted-fg, #898781);
		font-size: 11px;
		font-variant-numeric: tabular-nums;
	}
	.dot {
		fill: #3987e5;
		fill-opacity: 0.4;
		stroke: var(--bg, #12120f);
		stroke-width: 1.2;
		cursor: pointer;
	}
	.dot:hover,
	.dot:focus {
		fill-opacity: 0.95;
		outline: none;
	}
	.dot.sel {
		fill: #e0a23a;
		fill-opacity: 1;
	}
	.dot.degen {
		fill: #8b93a1;
	}
	.tip {
		font-size: 12px;
		min-height: 1.3em;
	}
</style>

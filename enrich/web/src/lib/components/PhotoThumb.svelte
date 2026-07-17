<script lang="ts">
	let {
		sizes,
		alt = '',
		size = 120
	}: { sizes: Record<string, { url?: string }> | null; alt?: string; size?: number } = $props();

	let broken = $state(false);

	const url = $derived.by(() => {
		if (!sizes) return null;
		for (const k of ['320', '640', 'thumb_640', '1024', 'full']) {
			const u = sizes[k]?.url;
			if (u) return u;
		}
		return null;
	});
</script>

{#if url && !broken}
	<img
		src={url}
		{alt}
		loading="lazy"
		style="max-width:{size}px; max-height:{size}px; border-radius:6px; border:1px solid var(--border)"
		onerror={() => (broken = true)}
	/>
{:else}
	<div
		class="muted"
		style="width:{size}px; height:{Math.round(size * 0.66)}px; display:flex; align-items:center;
		justify-content:center; background:var(--panel2); border-radius:6px; font-size:11px"
	>
		no image
	</div>
{/if}

<script lang="ts">
	import type { Snippet } from 'svelte';

	// page-level help: a ? button next to the h1 that drops down an explainer
	// panel (columns, symbols, workflow, where the page sits in the pipeline).
	// Content is authored per page as the children snippet; shared typography
	// for it lives in app.css under .help-panel (snippet markup compiles in the
	// parent's scope, so scoped styles here can't reach it).
	let { children }: { children: Snippet } = $props();
	let open = $state(false);
</script>

<svelte:window onkeydown={(e) => open && e.key === 'Escape' && (open = false)} />

<span class="wrap">
	<button
		class="help-btn"
		class:on={open}
		title={open ? 'hide help' : 'what am I looking at?'}
		onclick={() => (open = !open)}>?</button
	>
	{#if open}
		<div class="help-panel card">
			<button class="close" title="close" onclick={() => (open = false)}>×</button>
			{@render children()}
		</div>
	{/if}
</span>

<style>
	.wrap {
		position: relative;
		display: inline-block;
	}
	.help-btn {
		width: 22px;
		height: 22px;
		padding: 0;
		border-radius: 50%;
		font-size: 12px;
		line-height: 1;
		color: var(--muted);
	}
	.help-btn.on {
		color: var(--accent);
		border-color: var(--accent);
	}
	.help-panel {
		position: absolute;
		left: 0;
		top: 28px;
		z-index: 40;
		width: min(620px, 86vw);
		max-height: 72vh;
		overflow: auto;
		font-size: 13px;
		box-shadow: 0 10px 34px rgba(0, 0, 0, 0.55);
	}
	.close {
		position: absolute;
		top: 8px;
		right: 10px;
		padding: 0 8px;
		font-size: 14px;
		border: none;
		background: none;
		color: var(--muted);
	}
	.close:hover {
		color: var(--fg);
	}
</style>

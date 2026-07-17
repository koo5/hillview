<script lang="ts">
	import { api } from '$lib/api';
	import type { Fact } from '$lib/types';

	let {
		fact,
		interactive = false,
		onchange
	}: { fact: Fact; interactive?: boolean; onchange?: () => void } = $props();

	let busy = $state(false);

	async function curate(decision: 'approved' | 'rejected' | 'proposed') {
		busy = true;
		try {
			await api.post('/facts/curate', { fact: fact.fact, decision });
			fact.status = decision;
			onchange?.();
		} finally {
			busy = false;
		}
	}

	const display = $derived(
		fact.value_type === 'uri' ? fact.value.replace(/^https?:\/\//, '').slice(0, 46) : fact.value
	);
</script>

<span class="fact status-{fact.status}" title={fact.fact}>
	<span class="pred">{fact.predicate}</span>
	{#if fact.value_type === 'uri' && fact.value.startsWith('http') && !fact.value.includes('rdf.hillview.cz')}
		<a href={fact.value} target="_blank" rel="noreferrer">{display}</a>
	{:else}
		<span class="val">{display}</span>
	{/if}
	{#if interactive}
		<span class="verbs">
			{#if fact.status !== 'approved'}
				<button disabled={busy} title="approve" onclick={() => curate('approved')}>✓</button>
			{/if}
			{#if fact.status !== 'rejected'}
				<button disabled={busy} title="reject" onclick={() => curate('rejected')}>✗</button>
			{/if}
			{#if fact.status !== 'proposed'}
				<button disabled={busy} title="reset to proposed" onclick={() => curate('proposed')}>↺</button>
			{/if}
		</span>
	{/if}
</span>

<style>
	.fact {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		border: 1px solid var(--border);
		border-radius: 7px;
		padding: 2px 8px;
		margin: 2px 3px 2px 0;
		font-size: 12px;
		background: var(--panel2);
	}
	.pred {
		color: var(--muted);
	}
	.val {
		max-width: 300px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.status-approved {
		border-color: var(--approved);
	}
	.status-approved .pred {
		color: var(--approved);
	}
	.status-rejected {
		border-color: var(--rejected);
		opacity: 0.65;
	}
	.status-rejected .val {
		text-decoration: line-through;
	}
	.verbs button {
		padding: 0 6px;
		font-size: 11px;
		border-radius: 5px;
		margin-left: 2px;
	}
</style>

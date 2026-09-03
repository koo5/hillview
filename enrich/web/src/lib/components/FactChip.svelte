<script lang="ts">
	import { api } from '$lib/api';
	import type { Fact } from '$lib/types';

	let {
		fact,
		interactive = false,
		verdict = false,
		onchange
	}: { fact: Fact; interactive?: boolean; verdict?: boolean; onchange?: () => void } = $props();

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

	// a hillview.cz view link (hv:webPage from the parser) reads as what it points
	// at — "hillview view · 50.15163, 14.52344 · z16 · 181° · photo c39895fd" — so
	// the operator sees the annotator's reference without decoding a query string
	function hillviewView(u: string): string | null {
		const m = /^https?:\/\/(?:www\.)?hillview\.cz\/\?(.+)$/.exec(u);
		if (!m) return null;
		const q = new URLSearchParams(m[1]);
		const parts: string[] = [];
		if (q.get('lat') && q.get('lon')) parts.push(`${Number(q.get('lat')).toFixed(5)}, ${Number(q.get('lon')).toFixed(5)}`);
		if (q.get('zoom')) parts.push(`z${Math.round(Number(q.get('zoom')))}`);
		if (q.get('bearing')) parts.push(`${Math.round(Number(q.get('bearing')))}°`);
		if (q.get('photo')) parts.push(`photo ${q.get('photo')!.replace(/^hillview-/, '').slice(0, 8)}`);
		return `hillview view · ${parts.join(' · ')}`;
	}
	const display = $derived(
		fact.value_type === 'uri'
			? (hillviewView(fact.value) ?? fact.value.replace(/^https?:\/\//, '').slice(0, 46))
			: fact.value
	);

	// verdict mode: a rejected depictedIn is a negative verdict ("not depicted
	// in this photo"), not a discarded fact — say so instead of striking through
	const photoId = $derived(fact.value.split('/').pop() ?? '');
	const verdictLabel = $derived(
		fact.status === 'approved'
			? '✓ depicted in'
			: fact.status === 'rejected'
				? '✗ not depicted in'
				: '? depicted in — undecided'
	);
</script>

<span class="fact status-{fact.status}" class:verdict title={fact.fact}>
	{#if verdict}
		<span class="pred">{verdictLabel}</span>
		<a class="val" href="/photos/{photoId}">{photoId.slice(0, 8)}</a>
	{:else}
		<span class="pred">{fact.predicate}</span>
		{#if fact.value_type === 'uri' && fact.value.startsWith('http') && !fact.value.includes('rdf.hillview.cz')}
			<a href={fact.value} target="_blank" rel="noreferrer">{display}</a>
		{:else}
			<span class="val">{display}</span>
		{/if}
	{/if}
	{#if interactive}
		<span class="verbs">
			{#if fact.status !== 'approved'}
				<button
					disabled={busy}
					title={verdict ? 'mark depicted' : 'approve'}
					onclick={() => curate('approved')}>✓</button
				>
			{/if}
			{#if fact.status !== 'rejected'}
				<button
					disabled={busy}
					title={verdict ? 'mark not depicted' : 'reject'}
					onclick={() => curate('rejected')}>✗</button
				>
			{/if}
			{#if fact.status !== 'proposed'}
				<button
					disabled={busy}
					title={verdict ? 'reset to undecided' : 'reset to proposed'}
					onclick={() => curate('proposed')}>↺</button
				>
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
	}
	.status-rejected:not(.verdict) {
		opacity: 0.65;
	}
	.status-rejected:not(.verdict) .val {
		text-decoration: line-through;
	}
	.verdict.status-rejected .pred {
		color: var(--rejected);
	}
	.verbs button {
		padding: 0 6px;
		font-size: 11px;
		border-radius: 5px;
		margin-left: 2px;
	}
</style>

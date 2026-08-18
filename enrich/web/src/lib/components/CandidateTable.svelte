<script lang="ts">
	import { api } from '$lib/api';
	import type { Candidate } from '$lib/types';
	import { candidateLabel, candidateKind } from '$lib/candidateLabel';

	// The persisted anchorCandidate rows of one annotation (GET
	// /annotations/{id}/candidates — nearest first) with ✓/✗/↺ curation. Shared
	// by the geocode bench and the annotation page's Anchor section. Posts
	// /facts/curate itself (like FactChip) and then calls onchange — the parent
	// refetches; statuses are NOT mutated locally, the reload is the truth.
	let {
		candidates,
		selected = null,
		onselect,
		onchange,
		emptyText = 'no candidates — run geocode, or the label found nothing'
	}: {
		candidates: Candidate[];
		// highlighted candidate URI (shared with CandidateMap's `selected`)
		selected?: string | null;
		// row click
		onselect?: (candidate: string) => void;
		// after a decision was posted → refetch
		onchange?: () => void;
		// null hides the empty row
		emptyText?: string | null;
	} = $props();

	// fact IRI currently being posted (disables that row's verbs)
	let busy = $state<string | null>(null);

	async function curate(c: Candidate, decision: Candidate['status']) {
		busy = c.fact;
		try {
			await api.post('/facts/curate', { fact: c.fact, decision });
			onchange?.();
		} finally {
			busy = null;
		}
	}
</script>

<table data-testid="candidate-table">
	<thead><tr><th></th><th>candidate</th><th>km</th><th>Δ°</th><th>type</th><th></th></tr></thead>
	<tbody>
		{#each candidates as c (c.candidate)}
			<tr
				data-testid="candidate-row"
				class:sel={selected === c.candidate}
				style="cursor:pointer"
				onclick={() => onselect?.(c.candidate)}
			>
				<td>
					<span
						class="pill {c.status === 'approved' ? 'ok' : c.status === 'rejected' ? 'bad' : ''}"
						title={c.status}>{c.status[0]}</span
					>
				</td>
				<td style="max-width:340px">
					<a href={c.candidate} target="_blank" rel="noreferrer" style="font-size:12px" title={c.candidate}>
						{candidateLabel(c)}
					</a>
				</td>
				<td class="mono">{c.km ?? ''}</td>
				<td
					class="mono"
					style={Math.abs(c.bearing_offset ?? 0) > 60 ? 'color:var(--warn)' : ''}
				>
					{c.bearing_offset ?? ''}
				</td>
				<td class="muted" style="font-size:11px">{candidateKind(c)}</td>
				<td style="white-space:nowrap">
					{#if c.status !== 'approved'}
						<button
							data-testid="candidate-approve"
							disabled={busy === c.fact}
							title="approve = the anchor (supersedes a previously approved one)"
							onclick={(e) => { e.stopPropagation(); curate(c, 'approved'); }}>✓</button
						>
					{/if}
					{#if c.status !== 'rejected'}
						<button
							data-testid="candidate-reject"
							disabled={busy === c.fact}
							title="reject"
							onclick={(e) => { e.stopPropagation(); curate(c, 'rejected'); }}>✗</button
						>
					{/if}
					{#if c.status !== 'proposed'}
						<button
							data-testid="candidate-reset"
							disabled={busy === c.fact}
							title="reset to proposed"
							onclick={(e) => { e.stopPropagation(); curate(c, 'proposed'); }}>↺</button
						>
					{/if}
				</td>
			</tr>
		{:else}
			{#if emptyText}<tr><td colspan="6" class="muted">{emptyText}</td></tr>{/if}
		{/each}
	</tbody>
</table>

<style>
	/* the selected candidate (= CandidateMap's enlarged marker): an accent bar,
	   not just a tinted background — that read as a mere hover */
	tr.sel {
		background: var(--panel2);
	}
	tr.sel td:first-child {
		box-shadow: inset 3px 0 0 var(--accent);
	}
</style>

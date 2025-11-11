<script lang="ts">
	import {captureQueue, type QueueStats} from '$lib/captureQueue';
	import {Save, Loader2} from 'lucide-svelte';

	let stats: QueueStats;

	captureQueue.stats.subscribe(value => {
		stats = value;
	});
</script>

{#if stats}
	<div class="queue-indicator" data-testid="capture-queue-indicator">

		{#if stats.size > 0}
			<Save size={16}/>
			<span class="queue-count">{stats.size}</span>
			{#if stats.processing}
				<Loader2 size={14} class="spinner"/>
			{/if}
		{/if}

		{#if stats.totalCaptured}
			<div>({stats.totalCaptured})</div>
		{/if}

		{#if stats.processing}
			<div>...</div>
		{/if}

	</div>
{/if}

<style>
	.queue-indicator {
		display: flex;
		align-items: center;
		gap: 4px;
		background: rgba(0, 0, 0, 0.7);
		color: white;
		padding: 6px 10px;
		border-radius: 20px;
		font-size: 14px;
		font-weight: 500;
		backdrop-filter: blur(10px);
		border: 1px solid rgba(255, 255, 255, 0.2);
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
	}

	.queue-count {
		min-width: 1em;
		text-align: center;
	}

	:global(.queue-indicator .spinner) {
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		from {
			transform: rotate(0deg);
		}
		to {
			transform: rotate(360deg);
		}
	}
</style>

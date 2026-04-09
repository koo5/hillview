<script lang="ts">
	import { portal } from '$lib/actions/portal';
	import type { Snippet } from 'svelte';

	interface Props {
		open: boolean;
		onclose: () => void;
		title?: string;
		testId?: string;
		children: Snippet;
		actions?: Snippet;
	}

	let { open, onclose, title, testId, children, actions }: Props = $props();

	// Ignore backdrop clicks until modal has fully rendered (prevents click-through from triggers)
	let acceptClicks = $state(false);

	$effect(() => {
		if (open) {
			acceptClicks = false;
			// Wait for next frame to start accepting clicks
			requestAnimationFrame(() => {
				requestAnimationFrame(() => {
					acceptClicks = true;
				});
			});
		}
	});

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			onclose();
		}
	}

	function handleBackdropClick(event: MouseEvent) {
		if (!acceptClicks) return;
		if (event.target === event.currentTarget) {
			onclose();
		}
	}
</script>

<svelte:document onkeydown={open ? handleKeydown : undefined} />

{#if open}
	<div
		class="modal-overlay"
		onclick={handleBackdropClick}
		onkeydown={handleKeydown}
		role="button"
		tabindex="-1"
		use:portal
		data-testid={testId ?? 'modal'}
	>
		<div class="modal" role="dialog" aria-modal="true">
			{#if title}
				<div class="modal-header">
					<h3>{title}</h3>
					<button class="close-button" onclick={onclose} aria-label="Close">
						&times;
					</button>
				</div>
			{/if}
			<div class="modal-content">
				{@render children()}
			</div>
			{#if actions}
				<div class="modal-actions">
					{@render actions()}
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.5);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1100000;
		padding: 20px;
	}

	.modal {
		background: white;
		border-radius: 12px;
		max-width: 400px;
		width: 100%;
		max-height: 90vh;
		display: flex;
		flex-direction: column;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px 20px;
		border-bottom: 1px solid #e5e7eb;
	}

	.modal-header h3 {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
		color: #1f2937;
	}

	.close-button {
		background: none;
		border: none;
		font-size: 24px;
		color: #6b7280;
		cursor: pointer;
		padding: 0;
		line-height: 1;
	}

	.close-button:hover {
		color: #1f2937;
	}

	.modal-content {
		padding: 20px;
		overflow-y: auto;
	}

	.modal-actions {
		display: flex;
		gap: 12px;
		justify-content: flex-end;
		padding: 16px 20px;
		border-top: 1px solid #e5e7eb;
	}
</style>

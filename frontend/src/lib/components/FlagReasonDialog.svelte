<script lang="ts">
	import { portal } from '$lib/actions/portal';
	import { flagPhotoRequest } from '$lib/photoActions';
	import type { PhotoData } from '$lib/sources';

	export let show = false;
	export let photo: PhotoData | null = null;
	// Invoked after a successful flag (e.g. to flip the flagged state in the parent).
	export let onFlagged: ((message: string) => void) | undefined = undefined;

	const PRESETS = ['Wrong geolocation', 'Privacy', 'Abuse / spam'];

	// Default preselected so flagging is one confirm click; refine only if wanted.
	let choice = PRESETS[0];
	let otherText = '';
	let isFlagging = false;
	let message = '';
	let messageTimeout: ReturnType<typeof setTimeout> | null = null;

	function reset() {
		choice = PRESETS[0];
		otherText = '';
		message = '';
	}

	function cancel() {
		show = false;
		reset();
	}

	async function confirm() {
		if (!photo || isFlagging) return;
		const reason = choice === 'Other' ? otherText.trim() || 'Other' : choice;
		isFlagging = true;
		message = '';
		try {
			const result = await flagPhotoRequest(photo, reason);
			if (!result.success) {
				message = result.message;
				if (messageTimeout) clearTimeout(messageTimeout);
				messageTimeout = setTimeout(() => { message = ''; }, 5000);
				return;
			}
			show = false;
			reset();
			onFlagged?.(result.message);
		} finally {
			isFlagging = false;
		}
	}

	function switchToOther() {
		choice = 'Other';
	}

</script>

{#if show && photo}
	<div class="dialog-overlay" use:portal>
		<div class="dialog" data-testid="flag-reason-dialog">
			<h3>Flag this photo</h3>
			<p>What's wrong with it?</p>

			<div class="options">
				{#each PRESETS as p}
					<label class="option">
						<input type="radio" name="flag-reason" value={p} bind:group={choice} data-testid={`flag-reason-${p.replace(/\W+/g, '-').toLowerCase()}`} />
						<span>{p}</span>
					</label>
				{/each}
				<label class="option">
					<input type="radio" name="flag-reason" value="Other" bind:group={choice} data-testid="flag-reason-other" />
					<input
						class="other-text"
						type="text"
						bind:value={otherText}
						on:click={switchToOther}
						on:input={switchToOther}
						placeholder="Describe the issue"
						maxlength="500"
						data-testid="flag-reason-other-text"
					/>
				</label>
			</div>

			{#if message}
				<div class="error-message" data-testid="flag-reason-error">{message}</div>
			{/if}

			<div class="dialog-buttons">
				<button class="cancel-button" on:click={cancel} disabled={isFlagging} data-testid="flag-reason-cancel">Cancel</button>
				<button class="confirm-button" on:click={confirm} disabled={isFlagging} data-testid="flag-reason-confirm">
					{isFlagging ? 'Flagging…' : 'Flag photo'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.dialog-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.7);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 100000;
		animation: fadeIn 0.2s ease;
	}

	.dialog {
		background: white;
		padding: 24px;
		border-radius: 12px;
		max-width: 400px;
		width: 90%;
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
		animation: slideIn 0.2s ease;
	}

	@keyframes fadeIn {
		from { opacity: 0; }
		to { opacity: 1; }
	}

	@keyframes slideIn {
		from { opacity: 0; transform: translateY(-20px) scale(0.95); }
		to { opacity: 1; transform: translateY(0) scale(1); }
	}

	.dialog h3 {
		margin: 0 0 12px 0;
		color: #333;
		font-size: 1.25rem;
	}

	.dialog p {
		margin: 0 0 16px 0;
		color: #666;
		line-height: 1.4;
	}

	.options {
		display: flex;
		flex-direction: column;
		gap: 8px;
		margin-bottom: 8px;
	}

	.option {
		display: flex;
		align-items: center;
		gap: 8px;
		color: #333;
		cursor: pointer;
	}

	.other-text {
		width: 100%;
		box-sizing: border-box;
		margin-top: 4px;
		padding: 8px 12px;
		border: 1px solid #ddd;
		border-radius: 6px;
		font-size: 14px;
	}

	.other-text:focus {
		outline: none;
		border-color: #4a90e2;
		box-shadow: 0 0 0 2px rgba(74, 144, 226, 0.2);
	}

	.error-message {
		color: #dc3545;
		font-size: 14px;
		margin: 12px 0 0 0;
	}

	.dialog-buttons {
		display: flex;
		gap: 12px;
		justify-content: flex-end;
		margin-top: 24px;
	}

	.dialog-buttons button {
		padding: 10px 20px;
		border: none;
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.cancel-button {
		background: #f8f9fa;
		color: #495057;
		border: 1px solid #dee2e6;
	}

	.cancel-button:hover:not(:disabled) {
		background: #e9ecef;
	}

	.confirm-button {
		background: #dc2626;
		color: white;
	}

	.confirm-button:hover:not(:disabled) {
		background: #b91c1c;
	}

	.dialog-buttons button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
</style>

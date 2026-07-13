<script lang="ts">
	import { portal } from '$lib/actions/portal';
	import { deletePhotoRequest } from '$lib/photoActions';
	import { getUserName } from '$lib/photoUtils';
	import type { PhotoData } from '$lib/sources';

	export let show = false;
	export let photo: PhotoData | null = null;
	// Optional callback invoked after a successful delete.
	export let onDeleted: (() => void) | undefined = undefined;

	let reason = '';
	let isDeleting = false;
	let message = '';
	let messageTimeout: ReturnType<typeof setTimeout> | null = null;

	$: ownerName = photo ? getUserName(photo) : null;

	function cancel() {
		show = false;
		reason = '';
		message = '';
	}

	async function confirm() {
		if (!photo || isDeleting) return;

		isDeleting = true;
		message = '';
		try {
			const result = await deletePhotoRequest(photo, reason.trim() || undefined);
			if (!result.success) {
				message = result.message;
				if (messageTimeout) clearTimeout(messageTimeout);
				messageTimeout = setTimeout(() => { message = ''; }, 5000);
				return;
			}
			show = false;
			reason = '';
			onDeleted?.();
		} finally {
			isDeleting = false;
		}
	}
</script>

{#if show && photo}
	<div class="dialog-overlay" use:portal>
		<div class="dialog" data-testid="delete-photo-dialog">
			<h3>Delete photo</h3>
			<p>
				This permanently removes
				<strong>{ownerName ? `@${ownerName}'s` : 'this'}</strong> photo and its files.
				This can't be undone.
			</p>

			<div class="form-group">
				<label for="delete-reason">Reason (recorded in the moderation log):</label>
				<input
					id="delete-reason"
					type="text"
					bind:value={reason}
					placeholder="e.g., Inappropriate content, copyright, spam"
					maxlength="500"
					data-testid="delete-photo-reason"
				/>
			</div>

			{#if message}
				<div class="error-message" data-testid="delete-photo-error">{message}</div>
			{/if}

			<div class="dialog-buttons">
				<button
					class="cancel-button"
					onclick={cancel}
					disabled={isDeleting}
					data-testid="delete-photo-cancel"
				>
					Cancel
				</button>
				<button
					class="confirm-button"
					onclick={confirm}
					disabled={isDeleting}
					data-testid="delete-photo-confirm"
				>
					{isDeleting ? 'Deleting…' : 'Delete photo'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.dialog-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
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
		from {
			opacity: 0;
			transform: translateY(-20px) scale(0.95);
		}
		to {
			opacity: 1;
			transform: translateY(0) scale(1);
		}
	}

	.dialog h3 {
		margin: 0 0 16px 0;
		color: #333;
		font-size: 1.25rem;
	}

	.dialog p {
		margin: 0 0 20px 0;
		color: #666;
		line-height: 1.4;
	}

	.form-group {
		margin-bottom: 16px;
	}

	.form-group label {
		display: block;
		margin-bottom: 6px;
		color: #333;
		font-weight: 500;
	}

	.form-group input[type="text"] {
		width: 100%;
		padding: 8px 12px;
		border: 1px solid #ddd;
		border-radius: 6px;
		font-size: 14px;
		box-sizing: border-box;
	}

	.form-group input[type="text"]:focus {
		outline: none;
		border-color: #4a90e2;
		box-shadow: 0 0 0 2px rgba(74, 144, 226, 0.2);
	}

	.error-message {
		color: #dc3545;
		font-size: 14px;
		margin-bottom: 12px;
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
		background: #dc3545;
		color: white;
	}

	.confirm-button:hover:not(:disabled) {
		background: #c82333;
	}

	.dialog-buttons button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
</style>

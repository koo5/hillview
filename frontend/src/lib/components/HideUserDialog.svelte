<script lang="ts">
	import { http, handleApiError } from '$lib/http';
	import { simplePhotoWorker } from '$lib/simplePhotoWorker';
	import { portal } from '$lib/actions/portal';

	export let show = false;
	export let userId: string;
	export let username: string | null = null;
	export let userSource: 'hillview' | 'mapillary' = 'hillview';

	let hideUserReason = '';
	let flagUserForReview = false;
	let isHiding = false;
	let message = '';
	let messageTimeout: ReturnType<typeof setTimeout> | null = null;

	function cancel() {
		show = false;
		hideUserReason = '';
		flagUserForReview = false;
	}

	async function confirm() {
		if (!userId || isHiding) return;

		isHiding = true;
		message = '';

		try {
			const requestBody: any = {
				target_user_source: userSource,
				target_user_id: userId,
				reason: hideUserReason || 'Hidden from gallery'
			};

			if (flagUserForReview) {
				requestBody.extra_data = { flagged_for_review: true };
			}

			const response = await http.post('/hidden/users', requestBody);

			if (!response.ok) {
				throw new Error(`Failed to hide user: ${response.status}`);
			}

			// Clear web worker cache for this user's photos
			simplePhotoWorker.removeUserPhotosFromCache?.(userId, userSource);

			show = false;
			hideUserReason = '';
			flagUserForReview = false;
		} catch (error) {
			console.error('Error hiding user:', error);
			message = `Error: ${handleApiError(error)}`;
			if (messageTimeout) clearTimeout(messageTimeout);
			messageTimeout = setTimeout(() => { message = ''; }, 5000);
		} finally {
			isHiding = false;
		}
	}
</script>

{#if show}
	<div class="dialog-overlay" use:portal>
		<div class="dialog" data-testid="hide-user-dialog">
			<h3>Hide User</h3>
			<p>This will hide all photos by
				<strong>{username ? `@${username}` : 'this user'}</strong> from your view.
			</p>

			<div class="form-group">
				<label for="hide-reason">Reason (optional):</label>
				<input
					id="hide-reason"
					type="text"
					bind:value={hideUserReason}
					placeholder="e.g., Inappropriate content, spam, etc."
					maxlength="100"
					data-testid="hide-user-reason"
				/>
			</div>

			<div class="form-group">
				<label class="checkbox-label">
					<input
						type="checkbox"
						bind:checked={flagUserForReview}
						data-testid="hide-user-flag"
					/>
					Flag user for review by moderators
				</label>
			</div>

			{#if message}
				<div class="error-message">{message}</div>
			{/if}

			<div class="dialog-buttons">
				<button
					class="cancel-button"
					onclick={cancel}
					disabled={isHiding}
					data-testid="hide-user-cancel"
				>
					Cancel
				</button>
				<button
					class="confirm-button"
					onclick={confirm}
					disabled={isHiding}
					data-testid="hide-user-confirm"
				>
					{isHiding ? 'Hiding...' : 'Hide User'}
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

	.checkbox-label {
		display: flex !important;
		align-items: center;
		gap: 8px;
		cursor: pointer;
	}

	.checkbox-label input[type="checkbox"] {
		width: auto;
		margin: 0;
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
		background: #ff851b;
		color: white;
	}

	.confirm-button:hover:not(:disabled) {
		background: #e76500;
	}

	.dialog-buttons button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
</style>

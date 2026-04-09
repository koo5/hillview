<script lang="ts">
	import Modal from './Modal.svelte';
	import { signInModalState, closeSignInModal, signInAndNavigate } from './signInModal.svelte';
</script>

<Modal open={$signInModalState.visible} onclose={closeSignInModal} title="Sign in required" testId="sign-in-modal">
	<p class="sign-in-message">{$signInModalState.message}</p>
	<div class="sign-in-actions">
		<button class="sign-in-btn" onclick={signInAndNavigate} data-testid="sign-in-modal-login">Sign In</button>
		<button class="sign-in-cancel-btn" onclick={closeSignInModal} data-testid="sign-in-modal-cancel">Cancel</button>
	</div>
</Modal>

<style>
	.sign-in-message {
		margin: 0 0 16px;
		color: #374151;
		font-size: 14px;
	}

	.sign-in-actions {
		display: flex;
		gap: 12px;
		justify-content: flex-end;
	}

	.sign-in-btn {
		padding: 8px 20px;
		border: none;
		border-radius: 6px;
		background: #2563eb;
		color: white;
		font-weight: 600;
		cursor: pointer;
		font-size: 14px;
	}

	.sign-in-btn:hover {
		background: #1d4ed8;
	}

	.sign-in-cancel-btn {
		padding: 8px 20px;
		border: 1px solid #d1d5db;
		border-radius: 6px;
		background: white;
		color: #374151;
		font-weight: 500;
		cursor: pointer;
		font-size: 14px;
	}

	.sign-in-cancel-btn:hover {
		background: #f3f4f6;
	}
</style>

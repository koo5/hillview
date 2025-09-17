<script lang="ts">
	import { createEventDispatcher, onDestroy } from 'svelte';
	import { TAURI } from '$lib/tauri';
	import { invoke } from '@tauri-apps/api/core';
	import { navigateWithHistory } from '$lib/navigation.svelte';

	// Event from parent when a photo was captured
	export let photoCaptured = false;

	const dispatch = createEventDispatcher();

	let autoUploadEnabled = false;
	let autoUploadPromptEnabled = true;
	let loading = false;
	let visible = false;
	let showTimer: ReturnType<typeof setTimeout> | null = null;
	let hideTimer: ReturnType<typeof setTimeout> | null = null;

	// When a photo is captured, wait a bit then check if we should show prompt
	$: if (photoCaptured && TAURI) {
		schedulePromptCheck();
	}

	// Only show if TAURI, prompt is enabled, and auto-upload is not already enabled
	$: visible = TAURI && autoUploadPromptEnabled && !autoUploadEnabled && !loading;

	function schedulePromptCheck() {
		// Clear any existing timers
		if (showTimer) {
			clearTimeout(showTimer);
		}
		if (hideTimer) {
			clearTimeout(hideTimer);
		}

		// Wait 500ms after capture before showing prompt (avoid UI confusion)
		showTimer = setTimeout(() => {
			checkSettings();
		}, 500);
	}

	async function checkSettings() {
		loading = true;
		try {
			const result = await invoke('plugin:hillview|get_upload_status') as {
				autoUploadEnabled: boolean;
				autoUploadPromptEnabled: boolean;
			};

			autoUploadEnabled = result.autoUploadEnabled || false;
			autoUploadPromptEnabled = result.autoUploadPromptEnabled !== false;

			// If we should show the prompt, auto-hide it after 10 seconds
			if (!autoUploadEnabled && autoUploadPromptEnabled) {
				hideTimer = setTimeout(() => {
					hidePrompt();
				}, 10000);
			}
		} catch (err) {
			console.error('Failed to load auto-upload settings:', err);
			// Default to not showing prompt on error
			autoUploadPromptEnabled = false;
		} finally {
			loading = false;
		}
	}

	function goToSettings() {
		hidePrompt();
		navigateWithHistory('/settings');
	}

	function dismissPrompt() {
		// Just hide for this session - don't permanently disable prompting
		hidePrompt();
	}

	function hidePrompt() {
		// Reset state so prompt can show again on next capture
		autoUploadPromptEnabled = false; // Hide for this capture
		clearTimers();

		// Reset photoCaptured so parent can trigger again
		dispatch('hidden');
	}

	function clearTimers() {
		if (showTimer) {
			clearTimeout(showTimer);
			showTimer = null;
		}
		if (hideTimer) {
			clearTimeout(hideTimer);
			hideTimer = null;
		}
	}

	onDestroy(() => {
		clearTimers();
	});

	async function neverAskAgain() {
		// Permanently disable prompting
		try {
			await invoke('plugin:hillview|set_auto_upload_enabled', {
				enabled: false,
				promptEnabled: false
			});
			autoUploadPromptEnabled = false;
			dispatch('dismiss');
		} catch (err) {
			console.error('Failed to save settings:', err);
		}
	}
</script>

{#if visible}
	<div class="auto-upload-prompt" data-testid="auto-upload-prompt">
		<div class="prompt-content">
			<button
				class="configure-btn"
				on:click={goToSettings}
				data-testid="configure-auto-upload"
			>
				⚙️ Configure auto-upload
			</button>
			<button
				class="dismiss-btn"
				on:click={dismissPrompt}
				data-testid="dismiss-prompt"
				aria-label="Dismiss for now"
				title="Dismiss for now"
			>
				×
			</button>
		</div>
		<button
			class="never-ask-btn"
			on:click={neverAskAgain}
			data-testid="never-ask-again"
		>
			Don't show this again
		</button>
	</div>
{/if}

<style>
	.auto-upload-prompt {
		position: absolute;
		top: 140px; /* Below the location overlay */
		left: 1rem;
		background: rgba(255, 255, 255, 0.95);
		backdrop-filter: blur(10px);
		border-radius: 8px;
		border: 1px solid rgba(255, 255, 255, 0.3);
		padding: 0;
		box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
		display: flex;
		flex-direction: column;
		max-width: 250px;
		animation: slideIn 0.3s ease-out;
	}

	@keyframes slideIn {
		from {
			opacity: 0;
			transform: translateY(-10px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.prompt-content {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem;
	}

	.configure-btn {
		flex: 1;
		padding: 0.5rem 1rem;
		background: #4CAF50;
		color: white;
		border: none;
		border-radius: 4px;
		font-size: 0.9rem;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.2s;
		white-space: nowrap;
	}

	.configure-btn:hover {
		background: #45a049;
	}

	.configure-btn:active {
		transform: scale(0.98);
	}

	.dismiss-btn {
		width: 24px;
		height: 24px;
		padding: 0;
		background: rgba(0, 0, 0, 0.1);
		border: none;
		border-radius: 50%;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.2rem;
		line-height: 1;
		color: #666;
		transition: background 0.2s;
	}

	.dismiss-btn:hover {
		background: rgba(0, 0, 0, 0.2);
	}

	.never-ask-btn {
		width: 100%;
		padding: 0.5rem;
		background: transparent;
		border: none;
		border-top: 1px solid rgba(0, 0, 0, 0.1);
		color: #666;
		font-size: 0.8rem;
		cursor: pointer;
		transition: background 0.2s;
	}

	.never-ask-btn:hover {
		background: rgba(0, 0, 0, 0.05);
	}

	@media (prefers-color-scheme: dark) {
		.auto-upload-prompt {
			background: rgba(30, 30, 30, 0.95);
			border-color: rgba(255, 255, 255, 0.1);
		}

		.dismiss-btn {
			background: rgba(255, 255, 255, 0.1);
			color: #aaa;
		}

		.dismiss-btn:hover {
			background: rgba(255, 255, 255, 0.2);
		}

		.never-ask-btn {
			border-top-color: rgba(255, 255, 255, 0.1);
			color: #999;
		}

		.never-ask-btn:hover {
			background: rgba(255, 255, 255, 0.05);
		}
	}
</style>
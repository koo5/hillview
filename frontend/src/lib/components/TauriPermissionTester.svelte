<script lang="ts">
	import { invoke } from '@tauri-apps/api/core';

	export let onResult = (message: string) => {};
	export let onError = (message: string) => {};

	let isLoading = false;

	async function testTauriPermissions() {
		isLoading = true;

		try {
			// Test direct Tauri permission commands (likely to fail) (from js directly to kotlin)
			/*console.log('🔔 ttttttttttTesting direct Tauri checkPermissions...');
			try {
				const directCheck = await invoke('plugin:hillview|checkPermissions');
				console.log('🔔 Direct checkPermissions result:', JSON.stringify(directCheck));
			} catch (e) {
				console.log('🔔 Direct checkPermissions failed (expected):', e);
			}*/

			// Test our Rust wrapper commands
			console.log('🔔 Testing Rust wrapper checkTauriPermissions...');
			const checkResult = await invoke('plugin:hillview|check_tauri_permissions');
			console.log('🔔 checkTauriPermissions result:', JSON.stringify(checkResult));

			console.log('🔔 Testing Rust wrapper request_tauri_permission (post_notification)...');
			const requestResult = await invoke('plugin:hillview|request_tauri_permission', {
				permission: 'post_notification'
			});
			console.log('🔔 request_tauri_permission result:', JSON.stringify(requestResult));

			onResult(`Check: ${JSON.stringify(checkResult)}, Request: ${JSON.stringify(requestResult)}`);
		} catch (error) {
			console.error('🔔 Tauri permissions test failed:', error);
			const errorMessage = error instanceof Error ? error.message : 'Tauri permissions test failed';
			onError(errorMessage);
		} finally {
			isLoading = false;
		}
	}
</script>

<div class="test-section">
	<button
		class="test-button"
		on:click={testTauriPermissions}
		disabled={isLoading}
	>
		{isLoading ? 'Testing...' : 'Test Tauri Permissions'}
	</button>
	<p class="test-description">
		Test Tauri's built-in checkPermissions and requestPermissions commands
	</p>
</div>

<style>
	.test-section {
		margin: 1.5rem 0;
		padding: 1rem;
		background: #f8fafc;
		border: 1px solid #e2e8f0;
		border-radius: 0.5rem;
	}

	.test-button {
		background: #3b82f6;
		color: white;
		border: none;
		padding: 0.75rem 1.5rem;
		border-radius: 0.375rem;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.2s ease;
		width: 100%;
		margin-bottom: 0.5rem;
	}

	.test-button:hover:not(:disabled) {
		background: #2563eb;
	}

	.test-button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.test-description {
		margin: 0;
		color: #64748b;
		font-size: 0.75rem;
		text-align: center;
	}
</style>

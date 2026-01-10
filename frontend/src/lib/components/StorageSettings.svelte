<script lang="ts">
	import { storageSettings, type StorageMethod } from '$lib/storageSettings';
	import SettingsSectionHeader from "$lib/components/SettingsSectionHeader.svelte";

	export let onSaveSuccess: (message: string) => void = () => {};

	let preferredStorage: StorageMethod = 'public_folder';

	// Subscribe to store
	$: preferredStorage = $storageSettings.preferred_storage;

	const methodLabels: Record<StorageMethod, string> = {
		public_folder: 'Public folder',
		private_folder: 'Private folder',
		mediastore_api: 'MediaStore API'
	};

	function handleChange(method: StorageMethod) {
		storageSettings.set({ preferred_storage: method });
		onSaveSuccess(`Preferred storage: ${methodLabels[method]}`);
	}
</script>

<div class="storage-settings">
	<SettingsSectionHeader>Storage</SettingsSectionHeader>
	<p class="description">
		Choose your preferred storage method. If it fails, the app will automatically try the other methods.
	</p>

	<div class="radio-group">
		<label class="radio-option">
			<input
				type="radio"
				name="storage-method"
				value="public_folder"
				bind:group={preferredStorage}
				on:change={() => handleChange('public_folder')}
			/>
			<div class="option-content">
				<span class="option-title">Public folder first</span>
				<span class="option-description">
					DCIM/Hillview - visible in gallery, persists after uninstall.
				</span>
			</div>
		</label>

		<label class="radio-option">
			<input
				type="radio"
				name="storage-method"
				value="private_folder"
				bind:group={preferredStorage}
				on:change={() => handleChange('private_folder')}
			/>
			<div class="option-content">
				<span class="option-title">Private folder first</span>
				<span class="option-description">
					App-private storage - deleted if you uninstall the app.
				</span>
			</div>
		</label>

		<label class="radio-option">
			<input
				type="radio"
				name="storage-method"
				value="mediastore_api"
				bind:group={preferredStorage}
				on:change={() => handleChange('mediastore_api')}
			/>
			<div class="option-content">
				<span class="option-title">MediaStore API first</span>
				<span class="option-description">
					Android MediaStore - photos appear in gallery.
				</span>
			</div>
		</label>
	</div>
</div>

<style>

	.description {
		font-size: 0.875rem;
		color: #6b7280;
		margin: 0 0 1rem 0;
	}

	.radio-group {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.radio-option {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		padding: 0.75rem;
		border: 1px solid #e5e7eb;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: border-color 0.2s, background-color 0.2s;
	}

	.radio-option:hover {
		border-color: #d1d5db;
		background-color: #f9fafb;
	}

	.radio-option:has(input:checked) {
		border-color: #3b82f6;
		background-color: #eff6ff;
	}

	.radio-option input {
		margin-top: 0.125rem;
	}

	.option-content {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.option-title {
		font-weight: 500;
		font-size: 0.875rem;
		color: #1f2937;
	}

	.option-description {
		font-size: 0.75rem;
		color: #6b7280;
		line-height: 1.4;
	}
</style>

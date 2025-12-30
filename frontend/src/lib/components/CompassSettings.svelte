<script lang="ts">
	import { onMount } from 'svelte';
	import { compassSettings } from '$lib/compassSettings';
	import SettingsSectionHeader from "$lib/components/SettingsSectionHeader.svelte";

	export let onSaveSuccess: (message: string) => void = () => {};

	let landscapeWorkaround = false;
	let loading = true;

	onMount(() => {
		const unsubscribe = compassSettings.subscribe(value => {
			if (value.value) {
				landscapeWorkaround = value.value.landscape_armor22_workaround;
				loading = false;
			}
		});
		return unsubscribe;
	});

	async function handleToggle() {
		landscapeWorkaround = !landscapeWorkaround;
		await compassSettings.persist({
			landscape_armor22_workaround: landscapeWorkaround
		});
		onSaveSuccess(`Landscape compass workaround ${landscapeWorkaround ? 'enabled' : 'disabled'}`);
	}
</script>

<div class="compass-settings">
	<SettingsSectionHeader>Compass</SettingsSectionHeader>

	<label class="toggle-option">
		<div class="option-content">
			<span class="option-title">Landscape mode workaround</span>
			<span class="option-description">
				Fix compass readings when device is held in landscape orientation.
				Enable this if compass direction is wrong when holding the phone sideways.
			</span>
		</div>
		<input
			type="checkbox"
			checked={landscapeWorkaround}
			disabled={loading}
			on:change={handleToggle}
		/>
	</label>
</div>

<style>

	.toggle-option {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem;
		border: 1px solid #e5e7eb;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: border-color 0.2s, background-color 0.2s;
	}

	.toggle-option:hover {
		border-color: #d1d5db;
		background-color: #f9fafb;
	}

	.toggle-option input[type="checkbox"] {
		width: 1.25rem;
		height: 1.25rem;
		margin-top: 0.125rem;
		cursor: pointer;
	}

	.option-content {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		flex: 1;
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

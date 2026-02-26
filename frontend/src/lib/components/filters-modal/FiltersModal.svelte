<script lang="ts">
	import Modal from '../Modal.svelte';
	import { Sun, Moon, Sunrise, Home, Trees, RotateCcw } from 'lucide-svelte';
	import { filters, filtersModalState, closeFiltersModal, type QueryOptions } from './filtersStore';

	function setTimeOfDay(value: string | null) {
		filters.update(f => ({ ...f, time_of_day: f.time_of_day === value ? null : value }));
	}

	function setLocationType(value: string | null) {
		filters.update(f => ({ ...f, location_type: f.location_type === value ? null : value }));
	}

	function setMinFarthestDistance(value: number | null) {
		filters.update(f => ({ ...f, min_farthest_distance: f.min_farthest_distance === value ? null : value }));
	}

	function toggleFeature(feature: string) {
		filters.update(f => ({
			...f,
			features: f.features.includes(feature)
				? f.features.filter(x => x !== feature)
				: [...f.features, feature]
		}));
	}

	function handleClear() {
		filters.set({
			time_of_day: null,
			location_type: null,
			min_farthest_distance: null,
			max_closest_distance: null,
			features: []
		});
	}

	const timeOptions = [
		{ value: 'day', label: 'Day', icon: Sun },
		{ value: 'night', label: 'Night', icon: Moon },
		{ value: 'dawn_dusk', label: 'Dawn/Dusk', icon: Sunrise }
	];

	const locationOptions = [
		{ value: 'outdoors', label: 'Outdoors', icon: Trees },
		{ value: 'indoors', label: 'Indoors', icon: Home },
		{ value: 'mixed', label: 'Mixed', icon: null }
	];

	const featureOptions = [
		'playground', 'hill', 'mountain', 'street', 'building', 'bench', 'cityscape', 'art'
	];

	const distancePresets = [
		{ label: '100m+', value: 100 },
		{ label: '500m+', value: 500 },
		{ label: '1km+', value: 1000 },
		{ label: '5km+', value: 5000 }
	];
</script>

<Modal
	open={$filtersModalState.visible}
	onclose={closeFiltersModal}
	title="Photo Filters"
	testId="filters-modal"
>
	<div class="filters-content">
		<section class="filter-section">
			<h4>Time of Day</h4>
			<div class="option-chips">
				{#each timeOptions as opt}
					<button
						class="chip"
						class:selected={$filters.time_of_day === opt.value}
						onclick={() => setTimeOfDay(opt.value)}
					>
						{#if opt.icon}
							<svelte:component this={opt.icon} size={16} />
						{/if}
						{opt.label}
					</button>
				{/each}
			</div>
		</section>

		<section class="filter-section">
			<h4>Location Type</h4>
			<div class="option-chips">
				{#each locationOptions as opt}
					<button
						class="chip"
						class:selected={$filters.location_type === opt.value}
						onclick={() => setLocationType(opt.value)}
					>
						{#if opt.icon}
							<svelte:component this={opt.icon} size={16} />
						{/if}
						{opt.label}
					</button>
				{/each}
			</div>
		</section>

		<section class="filter-section">
			<h4>Minimum View Distance</h4>
			<p class="hint">Show photos where you can see at least this far</p>
			<div class="option-chips">
				{#each distancePresets as preset}
					<button
						class="chip"
						class:selected={$filters.min_farthest_distance === preset.value}
						onclick={() => setMinFarthestDistance(preset.value)}
					>
						{preset.label}
					</button>
				{/each}
			</div>
		</section>

		<section class="filter-section">
			<h4>Features</h4>
			<p class="hint">Show photos with any of these features</p>
			<div class="option-chips wrap">
				{#each featureOptions as feature}
					<button
						class="chip"
						class:selected={$filters.features.includes(feature)}
						onclick={() => toggleFeature(feature)}
					>
						{feature}
					</button>
				{/each}
			</div>
		</section>

		{#if $filters.time_of_day || $filters.location_type || $filters.min_farthest_distance !== null || $filters.features.length > 0}
			<button class="clear-button" onclick={handleClear}>
				<RotateCcw size={14} />
				Clear all filters
			</button>
		{/if}
	</div>
</Modal>

<style>
	.filters-content {
		display: flex;
		flex-direction: column;
		gap: 20px;
	}

	.filter-section {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.filter-section h4 {
		margin: 0;
		font-size: 14px;
		font-weight: 600;
		color: #374151;
	}

	.filter-section .hint {
		margin: 0;
		font-size: 12px;
		color: #6b7280;
	}

	.option-chips {
		display: flex;
		gap: 8px;
	}

	.option-chips.wrap {
		flex-wrap: wrap;
	}

	.chip {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 12px;
		border: 1px solid #d1d5db;
		border-radius: 20px;
		background: white;
		font-size: 13px;
		color: #374151;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.chip:hover {
		border-color: #3b82f6;
		background: #f0f9ff;
	}

	.chip.selected {
		border-color: #3b82f6;
		background: #3b82f6;
		color: white;
	}

	.clear-button {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		width: 100%;
		padding: 10px 16px;
		margin-top: 8px;
		border: 1px solid #d1d5db;
		border-radius: 8px;
		background: white;
		font-size: 13px;
		color: #6b7280;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.clear-button:hover {
		background: #f3f4f6;
		color: #374151;
	}
</style>

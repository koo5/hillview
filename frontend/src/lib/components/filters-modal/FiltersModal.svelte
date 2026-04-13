<script lang="ts">
	import Modal from '../Modal.svelte';
	import { Sun, Moon, Sunrise, Home, Trees, RotateCcw } from 'lucide-svelte';
	import { maxPhotosInArea } from '$lib/data.svelte';
	import { filters, hasActiveFilters, clearFilters, filtersModalState, closeFiltersModal, type QueryOptions } from './filtersStore';
	import { track } from '$lib/analytics';

	function setTimeOfDay(value: string | null) {
		track('filter', {name: 'time_of_day', value: value ?? 'off'});
		filters.update(f => ({ ...f, time_of_day: f.time_of_day === value ? null : value }));
	}

	function setLocationType(value: string | null) {
		track('filter', {name: 'location_type', value: value ?? 'off'});
		filters.update(f => ({ ...f, location_type: f.location_type === value ? null : value }));
	}

	function setMinFarthestDistance(value: number | null) {
		track('filter', {name: 'min_farthest_distance', value: value ?? 'off'});
		filters.update(f => ({ ...f, min_farthest_distance: f.min_farthest_distance === value ? null : value }));
	}

	function setMaxClosestDistance(value: number | null) {
		track('filter', {name: 'max_closest_distance', value: value ?? 'off'});
		filters.update(f => ({ ...f, max_closest_distance: f.max_closest_distance === value ? null : value }));
	}

	function setMinScenicScore(value: number | null) {
		track('filter', {name: 'min_scenic_score', value: value ?? 'off'});
		filters.update(f => ({ ...f, min_scenic_score: f.min_scenic_score === value ? null : value }));
	}

	function setVisibilityDistance(value: string | null) {
		track('filter', {name: 'visibility_distance', value: value ?? 'off'});
		filters.update(f => ({ ...f, visibility_distance: f.visibility_distance === value ? null : value }));
	}

	function setTallestBuilding(value: string | null) {
		track('filter', {name: 'tallest_building', value: value ?? 'off'});
		filters.update(f => ({ ...f, tallest_building: f.tallest_building === value ? null : value }));
	}

	function toggleFeature(feature: string) {
		track('filter', {name: 'feature', value: feature});
		filters.update(f => ({
			...f,
			features: f.features.includes(feature)
				? f.features.filter(x => x !== feature)
				: [...f.features, feature]
		}));
	}

	function handleClear() {
		track('filter', {name: 'clear'});
		clearFilters();
	}

	const timeOptions = [
		{ value: 'day', label: 'Day', icon: Sun },
		{ value: 'night', label: 'Night', icon: Moon },
		{ value: 'dawn_dusk', label: 'Dawn/Dusk', icon: Sunrise }
	];

	const locationOptions = [
		{ value: 'outdoors', label: 'Outdoors', icon: Trees },
		{ value: 'indoors', label: 'Indoors', icon: Home },
	];

	// All features organized by category (matching analyze_photo.py schema)
	const featureCategories = [
		{
			name: 'Nature',
			features: ['hill', 'mountain', 'river', 'stream', 'water_body', 'landscape', 'rock_outcrop', 'tree_lined_path', 'path', 'nature']
		},
		{
			name: 'Urban',
			features: ['street', 'building', 'cityscape', 'high_rise_building', 'church', 'playground', 'bench']
		},
		{
			name: 'Structures',
			features: ['bridge', 'tower', 'observation_tower', 'water_tower', 'cooling_tower', 'crane', 'curved_structure', 'mast']
		},
		{
			name: 'Infrastructure',
			features: ['lamp_post', 'powerline_pole', 'utility_pole', 'high_mast_lighting', 'row_of_streetlights', 'ev_charger']
		},
		{
			name: 'Activity',
			features: ['construction', 'roadworks', 'ski_slope', 'accident']
		},
		{
			name: 'Animals',
			features: ['cat', 'dog']
		},
		{
			name: 'Other',
			features: ['art', 'signage']
		}
	];

	// Helper to format feature names for display
	function formatFeature(feature: string): string {
		return feature.replace(/_/g, ' ');
	}

	const distancePresets = [
		{ label: '100m+', value: 100 },
		{ label: '500m+', value: 500 },
		{ label: '1km+', value: 1000 },
		{ label: '5km+', value: 5000 }
	];

	const maxClosestPresets = [
		{ label: '<5m', value: 5 },
		{ label: '<20m', value: 20 },
		{ label: '<50m', value: 50 },
		{ label: '<100m', value: 100 },
		{ label: '<500m', value: 500 },
	];

	const scenicScoreOptions = [
		{ value: 2, label: '2+ Good' },
		{ value: 3, label: '3+ Nice' },
		{ value: 4, label: '4+ Great' },
		{ value: 5, label: '5 Exceptional' }
	];

	const visibilityOptions = [
		{ value: 'near', label: 'Near' },
		{ value: 'medium', label: 'Medium' },
		{ value: 'far', label: 'Far' },
		{ value: 'panoramic', label: 'Panoramic' }
	];

	const buildingOptions = [
		{ value: 'none', label: 'None' },
		{ value: 'low_rise', label: 'Low-rise' },
		{ value: 'mid_rise', label: 'Mid-rise' },
		{ value: 'high_rise', label: 'High-rise' },
		{ value: 'skyscraper', label: 'Skyscraper' }
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
			<h4>Max Photos in Area</h4>
			<p class="hint">Maximum number of photos to load and display on the map</p>
			<input
				type="number"
				class="max-photos-input"
				min="10"
				max="1000"
				step="10"
				value={$maxPhotosInArea}
				oninput={(e) => {
					const val = parseInt((e.target as HTMLInputElement).value);
					if (val !== undefined) maxPhotosInArea.set(val);
				}}
				data-testid="max-photos-input"
			/>
		</section>

		<section class="filter-section">
			<h4>Time of Day</h4>
			<div class="option-chips">
				{#each timeOptions as opt}
					<button
						class="chip"
						class:selected={$filters.time_of_day === opt.value}
						onclick={() => setTimeOfDay(opt.value)}
						data-testid="filter"
						data-filter-name="time_of_day"
						data-filter-value={opt.value}
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
						data-testid="filter"
						data-filter-name="location_type"
						data-filter-value={opt.value}
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
						data-testid="filter"
						data-filter-name="min_farthest_distance"
						data-filter-value={preset.value}
					>
						{preset.label}
					</button>
				{/each}
			</div>
		</section>

		<section class="filter-section">
			<h4>Maximum Close Object Distance</h4>
			<p class="hint">Show photos with a close subject within this distance</p>
			<div class="option-chips">
				{#each maxClosestPresets as preset}
					<button
						class="chip"
						class:selected={$filters.max_closest_distance === preset.value}
						onclick={() => setMaxClosestDistance(preset.value)}
						data-testid="filter"
						data-filter-name="max_closest_distance"
						data-filter-value={preset.value}
					>
						{preset.label}
					</button>
				{/each}
			</div>
		</section>

		<section class="filter-section">
			<h4>Scenic Score</h4>
			<p class="hint">Minimum scenic beauty rating</p>
			<div class="option-chips">
				{#each scenicScoreOptions as opt}
					<button
						class="chip"
						class:selected={$filters.min_scenic_score === opt.value}
						onclick={() => setMinScenicScore(opt.value)}
						data-testid="filter"
						data-filter-name="min_scenic_score"
						data-filter-value={opt.value}
					>
						{opt.label}
					</button>
				{/each}
			</div>
		</section>

		<section class="filter-section">
			<h4>Visibility Distance</h4>
			<p class="hint">How far you can see in the photo</p>
			<div class="option-chips">
				{#each visibilityOptions as opt}
					<button
						class="chip"
						class:selected={$filters.visibility_distance === opt.value}
						onclick={() => setVisibilityDistance(opt.value)}
						data-testid="filter"
						data-filter-name="visibility_distance"
						data-filter-value={opt.value}
					>
						{opt.label}
					</button>
				{/each}
			</div>
		</section>

		<section class="filter-section">
			<h4>Tallest Building</h4>
			<p class="hint">Minimum building height visible</p>
			<div class="option-chips">
				{#each buildingOptions as opt}
					<button
						class="chip"
						class:selected={$filters.tallest_building === opt.value}
						onclick={() => setTallestBuilding(opt.value)}
						data-testid="filter"
						data-filter-name="tallest_building"
						data-filter-value={opt.value}
					>
						{opt.label}
					</button>
				{/each}
			</div>
		</section>

		<section class="filter-section">
			<h4>Features</h4>
			<p class="hint">Show photos with any of these features</p>
			{#each featureCategories as category}
				<div class="feature-category">
					<h5>{category.name}</h5>
					<div class="option-chips wrap">
						{#each category.features as feature}
							<button
								class="chip"
								class:selected={$filters.features.includes(feature)}
								onclick={() => toggleFeature(feature)}
								data-testid="filter"
								data-filter-name="feature"
								data-filter-value={feature}
							>
								{formatFeature(feature)}
							</button>
						{/each}
					</div>
				</div>
			{/each}
		</section>

		<div class="bottom-controls">
			<label class="toggle-label" class:disabled={!$hasActiveFilters} data-testid="show-unanalyzed">
				<input
					type="checkbox"
					bind:checked={$filters.show_unanalyzed}
					disabled={!$hasActiveFilters}
				/>
				Show unanalyzed photos
			</label>
			<button class="clear-button" onclick={handleClear} disabled={!$hasActiveFilters} data-testid="clear-filters">
				<RotateCcw size={14} />
				Clear all filters
			</button>
		</div>
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

	.feature-category {
		margin-top: 8px;
	}

	.feature-category h5 {
		margin: 0 0 6px 0;
		font-size: 12px;
		font-weight: 500;
		color: #6b7280;
		text-transform: uppercase;
		letter-spacing: 0.5px;
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

	.bottom-controls {
		display: flex;
		flex-direction: column;
		gap: 10px;
		margin-top: 8px;
	}

	.toggle-label {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 13px;
		color: #374151;
		cursor: pointer;
	}

	.toggle-label.disabled {
		opacity: 0.4;
		cursor: default;
	}

	.clear-button {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		width: 100%;
		padding: 10px 16px;
		border: 1px solid #d1d5db;
		border-radius: 8px;
		background: white;
		font-size: 13px;
		color: #6b7280;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.clear-button:hover:not(:disabled) {
		background: #f3f4f6;
		color: #374151;
	}

	.clear-button:disabled {
		opacity: 0.4;
		cursor: default;
	}

	.max-photos-input {
		width: 80px;
		padding: 6px 10px;
		border: 1px solid #d1d5db;
		border-radius: 8px;
		font-size: 14px;
		color: #374151;
	}

	.max-photos-input:focus {
		outline: none;
		border-color: #3b82f6;
		box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
	}
</style>

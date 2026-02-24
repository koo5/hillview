<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	let className: string = '';
	export { className as class };
	export let value: number;
	export let min: number;
	export let max: number;
	export let step: number = 0.1;
	export let label: string;
	export let id: string;
	export let ariaLabel: string;
	export let thumbColor: string = 'white';

	const dispatch = createEventDispatcher<{ change: number }>();

	function handleInput(event: Event) {
		const target = event.target as HTMLInputElement;
		dispatch('change', parseFloat(target.value));
	}
</script>

<div class="vertical-slider-control {className}">
	<label for={id} class="slider-label">
		{label}
	</label>
	<input
		{id}
		type="range"
		{min}
		{max}
		{step}
		{value}
		on:input={handleInput}
		class="vertical-slider"
		style="--thumb-color: {thumbColor}"
		aria-label={ariaLabel}
	/>
</div>

<style>
	.vertical-slider-control {
		position: absolute;
		height: 150px;
		width: 40px;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: flex-start;
		background: rgba(0, 0, 0, 0.2);
		border-radius: 8px;
		backdrop-filter: blur(2px);
		padding: 8px 0;
		z-index: 1002;
	}

	.slider-label {
		color: white;
		font-size: 0.85rem;
		font-weight: 500;
		min-width: 3em;
		text-align: center;
		margin-bottom: 4px;
		flex-shrink: 0;
	}

	.vertical-slider {
		width: 120px;
		height: 50px;
		transform: rotate(-90deg);
		transform-origin: center;
		margin: 40px 0;
		cursor: pointer;
		touch-action: none;
	}

	.vertical-slider::-webkit-slider-track {
		background: rgba(255, 255, 255, 0.3);
		height: 6px;
		border-radius: 3px;
	}

	.vertical-slider::-webkit-slider-thumb {
		-webkit-appearance: none;
		appearance: none;
		width: 28px;
		height: 28px;
		background: var(--thumb-color, white);
		border-radius: 50%;
		cursor: pointer;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
	}

	.vertical-slider::-moz-range-track {
		background: rgba(255, 255, 255, 0.3);
		height: 6px;
		border-radius: 3px;
	}

	.vertical-slider::-moz-range-thumb {
		width: 50px;
		height: 50px;
		background: var(--thumb-color, white);
		border-radius: 50%;
		border: none;
		cursor: pointer;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
	}

	@media (max-width: 600px) {
		.vertical-slider-control {
			height: 160px;
			width: 40px;
			padding: 6px 0;
		}

		.vertical-slider {
			width: 120px;
			height: 50px;
			margin: 35px 0;
		}
	}
</style>

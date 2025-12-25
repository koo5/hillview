<script lang="ts">
	import {Compass, Disc, Car, PersonStanding, ChevronDown} from 'lucide-svelte';
	import { type BearingMode } from '$lib/mapState';
	export let bearingMode: BearingMode;

	$: isTouch = typeof window !== 'undefined' && ('ontouchstart' in window || navigator.maxTouchPoints > 0);

</script>

<div class="button-content">
	<Compass/>
	<div class="mode-section">
		<div class="mode-indicator">
			{#if bearingMode === 'car'}
				<Car size={16}/>
			{:else}
				<PersonStanding size={16}/>
			{/if}
		</div>
		{#if !isTouch}
			<div class="dropdown-trigger">
				<ChevronDown size={12}/>
			</div>
		{:else}
			<div class="long-press-indicator">
				<ChevronDown size={12}/>
			</div>
		{/if}
	</div>
</div>

<style>
    .compass-button-container {
        position: relative;
        display: inline-block;
        /* Remove z-index to avoid creating stacking context */
    }

    .compass-button {
        background-color: rgba(255, 255, 255, 0.9);
        border: 2px solid #ddd;
        border-radius: 4px;
        padding: 8px;
        cursor: pointer;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
        transition: all 0.2s ease;
        position: relative;
        min-width: 60px;
        min-height: 44px;
        display: flex;
        align-items: center;
        justify-content: center;
        -webkit-user-select: none;
        user-select: none;
    }

    .compass-button:hover {
        background-color: rgba(255, 255, 255, 1);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }

    .compass-button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .compass-button.active {
        background-color: #4285F4;
        border-color: #4285F4;
        color: white;
    }

    .compass-button.loading {
        animation: pulse 1.5s ease-in-out infinite;
    }

    .compass-button.error {
        background-color: #f44336;
        border-color: #f44336;
        color: white;
    }

    .compass-button.dropdown-open {
        background-color: rgba(255, 255, 255, 1);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }

    .button-content {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 4px;
        position: relative;
    }

    .mode-section {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1px;
    }

    .mode-indicator {
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .dropdown-trigger {
        opacity: 0.7;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .long-press-indicator {
        opacity: 0.6;
        display: flex;
        align-items: center;
        justify-content: center;
        pointer-events: none;
    }


    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.6; }
        100% { opacity: 1; }
    }

    /* Mobile optimizations */
    @media (max-width: 768px) {
        .compass-button {
            /*min-width: 48px;*/
            /*min-height: 48px;*/
            touch-action: manipulation;
        }

        /*.dropdown-trigger {*/
        /*    display: none;*/
        /*}*/
    }
</style>

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


    </style>

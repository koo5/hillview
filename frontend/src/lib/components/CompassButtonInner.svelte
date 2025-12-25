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

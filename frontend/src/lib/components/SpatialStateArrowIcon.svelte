<script>
	import BearingStateArrow from './BearingStateArrow.svelte';

	export let centerX;
	export let centerY;
	export let arrowX;
	export let arrowY;

</script>

<div class="spatial-state-arrow-icon">

<BearingStateArrow
	{centerX}
	{centerY}
	{arrowX}
	{arrowY}
/>

</div>


<style>
	.spatial-state-arrow-icon {
		width: 24px;
		height: 16px;
	}
</style>

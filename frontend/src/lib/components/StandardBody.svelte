<script lang="ts">
    // StandardBody - provides proper spacing and common page styling
import InsetGradients from "$lib/components/InsetGradients.svelte";
</script>

<div class="standard-body page-scrollable">
    <slot />
</div>



<style>
    .standard-body {
        /* Offset for fixed StandardHeader + extra padding */
        min-height: calc(100vh - 66px);

        /* Common page container styling */
        max-width: 1200px;
        margin-top: 0px;
		margin-left: auto;
		margin-right: auto;
		margin-bottom: 100px;

        /*padding-top: 66px;*/
		padding-top: calc(66px + var(--safe-area-inset-top, 0px));
		padding-left: calc(20px + var(--safe-area-inset-left, 0px));
        /*padding-right: 20px;*/
		padding-right: calc(20px + var(--safe-area-inset-right, 0px));
        /*padding-bottom: 40px;*/ /* More bottom padding for scroll space */
		padding-bottom: calc(40px + var(--safe-area-inset-bottom, 0px));

        /* Ensure content can scroll */
        overflow-y: auto;
    }

    /* Responsive adjustments */
    @media (max-width: 640px) {
        .standard-body {
            min-height: calc(100vh - 72px);
			padding-top: calc(62px + var(--safe-area-inset-top, 0px));
			padding-left calc(16px + var(--safe-area-inset-left, 0px));
            /*padding-right: 16px;*/
			padding-right: calc(16px + var(--safe-area-inset-right, 0px));
            /*padding-bottom: 40px;*/
			padding-bottom: calc(40px + var(--safe-area-inset-bottom, 0px));

        }
    }
</style>

<script lang="ts">
    // StandardBody - provides proper spacing and common page styling
</script>

<div class="standard-body page-scrollable">
    <slot />
</div>

<style>
    .standard-body {
        /* Offset for fixed StandardHeader + extra padding */
        padding-top: 66px;
        min-height: calc(100vh - 66px);

        /* Common page container styling */
        max-width: 1200px;
        margin-top: 0px;
		margin-left: auto;
		margin-right: auto;
		margin-bottom: 100px;
        padding-left: 20px;
        padding-right: 20px;
        padding-bottom: 40px; /* More bottom padding for scroll space */

        /* Ensure content can scroll */
        overflow-y: auto;
    }

    /* Responsive adjustments */
    @media (max-width: 640px) {
        .standard-body {
			padding-top: calc(62px + var(--safe-area-inset-top, 0px));

            min-height: calc(100vh - 72px);
            padding-left: 16px;
            padding-right: 16px;
            padding-bottom: 40px;
        }
    }
</style>

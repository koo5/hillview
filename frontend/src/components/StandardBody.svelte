<script lang="ts">
    // StandardBody - provides proper spacing and common page styling
</script>

<div class="standard-body">
    <slot />
</div>

<style>
    .standard-body {
        /* Offset for fixed StandardHeader + extra padding */
        padding-top: 66px;
        min-height: calc(100vh - 66px);
        
        /* Common page container styling */
        max-width: 1200px;
        margin: 0 auto;
        padding-left: 20px;
        padding-right: 20px;
        padding-bottom: 20px;
    }

    /* Responsive adjustments */
    @media (max-width: 640px) {
        .standard-body {
            padding-top: 72px;
            min-height: calc(100vh - 72px);
            padding-left: 16px;
            padding-right: 16px;
        }
    }
</style>
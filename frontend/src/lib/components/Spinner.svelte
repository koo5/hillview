<script lang="ts">
    export let show = true;
    export let color = '#ffffff';
</script>

<style>

    .container {
        min-height: 2em;
        min-width: 2em;
        padding: 0px;
        margin: 0;
    }

    .spinner {
        padding: 0px;
        margin: 0;
        width: 2em;
        height: 2em;
        border-radius: 50%;
        background:
                radial-gradient(farthest-side, #fac, 94%, transparent) top/8px 8px no-repeat,
                conic-gradient(transparent 30%, var(--spinner-color));
        mask: radial-gradient(farthest-side, transparent calc(100% - 8px), var(--spinner-color) 0);
        -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 8px), var(--spinner-color) 0);
        animation: spinner 1s infinite linear;
    }

    @keyframes spinner {
        100% {
            transform: rotate(1turn);
        }
    }
</style>
{#if show}
<div class="container" style="--spinner-color: {color}">
    <div class="spinner"></div>
</div>
{/if}

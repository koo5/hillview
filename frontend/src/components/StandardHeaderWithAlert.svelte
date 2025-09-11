<script lang="ts">
    import StandardHeader from './StandardHeader.svelte';
    import AlertArea from './AlertArea.svelte';

    export let title: string;
    export let showBackButton: boolean = true;
    export let showMenuButton: boolean = true;
    export let onMenuClick: (() => void) | null = null;
    export let fallbackHref: string = '/';
    export let useSmartBack: boolean = true;
</script>

<div class="header-with-alert">
    <StandardHeader 
        {title}
        {showBackButton}
        {showMenuButton}
        {onMenuClick}
        {fallbackHref}
        {useSmartBack}
    >
        <slot name="actions" slot="actions" />
    </StandardHeader>
    
    <AlertArea position="header" />
</div>

<style>
    .header-with-alert {
        position: sticky;
        top: 0;
        z-index: 20;
    }
</style>
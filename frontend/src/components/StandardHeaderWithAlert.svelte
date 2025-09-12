<script lang="ts">
    import StandardHeader from './StandardHeader.svelte';
    import AlertArea from './AlertArea.svelte';
    import NavigationMenu from './NavigationMenu.svelte';

    export let title: string;
    export let showBackButton: boolean = true;
    export let showMenuButton: boolean = true;
    export let fallbackHref: string = '/';
    export let useSmartBack: boolean = true;

    let menuOpen = false;

    function toggleMenu() {
        menuOpen = !menuOpen;
    }

    function closeMenu() {
        menuOpen = false;
    }
</script>

<div class="header-with-alert">
    <StandardHeader
        {title}
        {showBackButton}
        {showMenuButton}
        onMenuClick={toggleMenu}
        {fallbackHref}
        {useSmartBack}
    >
		<AlertArea position="header" />
        <slot name="actions" slot="actions" />
    </StandardHeader>
    <NavigationMenu isOpen={menuOpen} onClose={closeMenu} />
</div>

<!-- No additional styles needed - header positioning is handled in StandardHeader -->

<script lang="ts">
    /**
     * Gates slotted content on the user profile being loaded. Composes <Loadable>
     * with the profile load state: a spinner while the profile is loading, a retry
     * (wired to retryUserData) if it failed, and the slot once it's available.
     *
     * Use at any view that needs $auth.user — instead of treating a missing profile
     * as "logged out". The auth truth is $auth.is_authenticated; this is just the
     * "is the profile here yet" layer.
     */
    import { profileLoading, profileError } from '$lib/authStore';
    import { retryUserData } from '$lib/auth.svelte';
    import Loadable from './Loadable.svelte';
</script>

<Loadable loading={$profileLoading} error={$profileError} on:retry={retryUserData}>
    <slot />
</Loadable>

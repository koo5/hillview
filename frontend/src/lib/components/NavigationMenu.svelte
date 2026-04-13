<script lang="ts">
    import {
        Map, Images, Activity, Award, Database, Info, Download, User, EyeOff, LogOut, Users, Settings, Maximize2, Minimize2
    } from 'lucide-svelte';
    import { auth, logout } from '$lib/auth.svelte.js';
    import { isFullscreen, toggleFullscreen } from '$lib/fullscreen.svelte';
    import { FEATURE_USER_ACCOUNTS } from '$lib/config';
    import { BUILD_TIME, BUILD_VERSION, BUILD_GIT_COMMIT, APP_VERSION, formatBuildTime } from '$lib/buildInfo';
    import { TAURI } from '$lib/tauri.js';
    import { browser } from '$app/environment';
    import { openExternalUrl } from '$lib/urlUtils';
	import {backendUrl} from "$lib/config";
    import { Bug } from 'lucide-svelte';
    import * as Sentry from '@sentry/sveltekit';

    export let isOpen = false;

    async function handleFeedbackClick() {
        closeMenu();
        const feedback = Sentry.getFeedback();
        if (feedback) {
            const form = await feedback.createForm();
            form.appendToDom();
            form.open();
        }
    }
    export let onClose: () => void = () => {};

    // Subscribe to auth store
    let is_authenticated = false;
    auth.subscribe(value => {
        is_authenticated = value.is_authenticated;
    });

    async function handleLogout() {
        await logout();
        onClose();
    }

    function closeMenu() {
        onClose();
    }

    // Handle click events on external links (same pattern as about page)
    async function handleExternalClick(event: Event) {
        const target = event.target as HTMLElement;
        const link = target.closest('a[data-external-link="true"]') as HTMLAnchorElement;

        if (link && link.href) {
            event.preventDefault(); // Prevent default navigation
            closeMenu();
            await openExternalUrl(link.href);
        }
    }

    function formatUtcDate(date: Date): string {
        // Pad helper
        const pad = (n: number) => n.toString().padStart(2, '0');
        return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}_` +
               `${pad(date.getUTCHours())}-${pad(date.getUTCMinutes())}-${pad(date.getUTCSeconds())}`;
    }
</script>

{#if isOpen}
    <!-- Menu backdrop for mobile -->
    <div
        class="menu-backdrop"
        role="button"
        tabindex="0"
        aria-label="Close menu"
        on:click={closeMenu}
        on:keydown={(e) => e.key === 'Escape' && closeMenu()}
    ></div>

    <nav class="nav-menu" data-testid="nav-menu">

        <ul class="menu-list" on:click={handleExternalClick} role="presentation">
            <li><a href="/" on:click={closeMenu}>
                <Map size={18}/>
                Map
            </a></li>

            <li><a href="/photos" on:click={closeMenu} data-testid="my-photos-link">
                <Images size={18}/>
                My Photos
            </a></li>

			<hr/>

            <li><a href="/activity" on:click={closeMenu} data-testid="nav-activity-link">
                <Activity size={18}/>
                Activity
            </a></li>

            <li><a href="/bestof" on:click={closeMenu} data-testid="bestof-menu-link">
                <Award size={18}/>
                Best of
            </a></li>

            <li><a href="/users" on:click={closeMenu} data-testid="nav-users-link">
                <Users size={18}/>
                Users
            </a></li>

            {#if FEATURE_USER_ACCOUNTS}

				<hr/>

                <li>
                    <a href="/settings" on:click={closeMenu} data-testid="settings-menu-link">
                        <Settings size={18}/>
                        Settings
                    </a>
                </li>
                <li>
                    <button class="menu-button" on:click={toggleFullscreen} data-testid="fullscreen-menu-btn">
                        {#if $isFullscreen}
                            <Minimize2 size={18}/>
                            Exit Fullscreen
                        {:else}
                            <Maximize2 size={18}/>
                            Fullscreen
                        {/if}
                    </button>
                </li>
                {#if is_authenticated}
                    <li>
                        <a href="/hidden" on:click={closeMenu}>
                            <EyeOff size={18}/>
                            Hidden Content
                        </a>
                    </li>
                    <li>
                        <a href="/account" on:click={closeMenu}>
                            <User size={18}/>
                            Account
                        </a>
                    </li>
                    <li>
                        <button class="menu-button logout" on:click={handleLogout} data-testid="nav-logout-button">
                            <LogOut size={18}/>
                            Logout{$auth.user ? ` (${$auth.user.username})` : ''}
                        </button>
                    </li>
                {:else}
                    <li>
                        <a href="/login" on:click={closeMenu} data-testid="nav-login-link">
                            <User size={18}/>
                            Login / Register
                        </a>
                    </li>
                {/if}
            {/if}

			<hr/>

            <li><a href="/about" on:click={closeMenu}>
                <Info size={18}/>
                About
            </a></li>

            <li>
                <button class="menu-button" on:click={handleFeedbackClick}>
                    <Bug size={18}/>
                    Report Bug
                </button>
            </li>

			{#if !TAURI}
				<li>
					<a href="/download" data-external-link="true" target="_blank" rel="noopener noreferrer">
						<Download size={18}/>
						Download App
					</a>
				</li>
			{/if}


			<hr/>
			<li>
					<div class="build-info">
						<div class="app-version">
							Hillview version {APP_VERSION}
						</div>
						<div class="build-commit">
							{BUILD_GIT_COMMIT}
						</div>
						<div class="build-version">
							Build timestamp: {formatUtcDate(new Date(BUILD_TIME))}
						</div>
						<div class="build-timestamp">
							API server: {backendUrl}
						</div>
					</div>

			</li>


        </ul>

    </nav>
{/if}

<style>

    .menu-backdrop {
        position: fixed;
        top: 0px;
        left: 0;
        right: 0;
        bottom: 0;
        background: transparent;
        z-index: 30002;
    }

    .nav-menu {
        position: fixed;
        top: calc(60px + var(--safe-area-inset-top, 0px));
        left: calc(0px + var(--safe-area-inset-left, 0px));
        width: 280px;
        height: calc(100vh - (60px + var(--safe-area-inset-top, 0px)));
        background: white;
        z-index: 130100;
        box-shadow: 2px 0 10px rgba(0, 0, 0, 0.2);
        padding: 0;
        overflow-y: auto;
        transform: translateX(0);
        transition: transform 0.3s ease;
    }


    .menu-list {
        list-style: none;
        padding: 20px 0 80px 0; /* Add bottom padding for build info */
        margin: 0;
    }

    .menu-list li {
        margin: 0;

    }

    .menu-list li a,
    .menu-button {
        display: flex;
        align-items: center;
        gap: 12px;
        text-decoration: none;
        color: #374151;
        font-size: 1rem;
        padding: 12px 24px;
        transition: background-color 0.2s, color 0.2s;
        border: none;
        background: none;
        width: 100%;
        text-align: left;
        cursor: pointer;
    }

    .menu-list li a:hover,
    .menu-button:hover {
        background-color: #f3f4f6;
        color: #1f2937;
    }

    .menu-button.logout {
        color: #dc2626;
    }

    .menu-button.logout:hover {
        background-color: #fef2f2;
        color: #991b1b;
    }

    .build-info {
        padding: 16px 24px;
        background: #f9fafb;
        font-family: monospace;
        font-size: 0.5rem;
        color: #6b7280;
        line-height: 1.4;
        user-select: text;
        -webkit-user-select: text;
    }

    .build-timestamp {
        margin-bottom: 2px;
    }

    .build-version {
        color: #4b5563;
    }

    /* Mobile-specific adjustments */
    @media (max-width: 640px) {
        .nav-menu {
            width: 85vw;
            max-width: 320px;
        }

        .menu-list li a,
        .menu-button {
            /*padding: 14px 20px;*/
            font-size: 1.1rem;
        }
    }
</style>

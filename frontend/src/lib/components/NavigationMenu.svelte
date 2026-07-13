<script lang="ts">
    import {
        Map, Images, Activity, Award, Database, Info, Download, User, EyeOff, LogOut, Users, Settings, Maximize2, Minimize2, Shield
    } from 'lucide-svelte';
    import { auth, logout } from '$lib/auth.svelte.js';
    import { Bell, ShieldCheck } from 'lucide-svelte';
    import { isAdmin, isModerator } from '$lib/adminNotifications';
    import { unreadCount } from '$lib/notifications';
    import AdminBadge from '$lib/components/AdminBadge.svelte';
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
        data-testid="menu-backdrop"
        role="button"
        tabindex="0"
        aria-label="Close menu"
        on:click={closeMenu}
        on:keydown={(e) => e.key === 'Escape' && closeMenu()}
    ></div>
{/if}

<nav
    class="nav-menu"
    class:open={isOpen}
    data-testid="nav-menu"
    aria-hidden={!isOpen}
    inert={!isOpen}
>

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
                Activity <span class="menu-desc">— latest photos</span>
            </a></li>

            <li><a href="/bestof" on:click={closeMenu} data-testid="bestof-menu-link">
                <Award size={18}/>
                Best of <span class="menu-desc">— annotated panoramas</span>
            </a></li>

            <li><a href="/users" on:click={closeMenu} data-testid="nav-users-link">
                <Users size={18}/>
                Users
            </a></li>

            {#if $isAdmin}
                <hr/>
                <li><a href="/admin" on:click={closeMenu} data-testid="nav-admin-link" class="admin-link">
                    <Shield size={18}/>
                    Admin
                    <AdminBadge variant="inline" />
                </a></li>
            {:else if $isModerator}
                <hr/>
                <li><a href="/moderate" on:click={closeMenu} data-testid="nav-moderate-link">
                    <ShieldCheck size={18}/>
                    Moderate
                </a></li>
            {/if}

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
                        <a href="/notifications" on:click={closeMenu} data-testid="nav-notifications-link" class="notifications-link">
                            <Bell size={18}/>
                            Notifications
                            {#if $unreadCount > 0}
                                <span class="unread-badge" data-testid="nav-notifications-badge">{$unreadCount > 99 ? '99+' : $unreadCount}</span>
                            {/if}
                        </a>
                    </li>
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
						{#if APP_VERSION !== 'unknown'}
							<div class="app-version">
								Hillview version {APP_VERSION}
							</div>
						{/if}
						{#if BUILD_GIT_COMMIT !== 'unknown'}
							<div class="build-commit">
								{BUILD_GIT_COMMIT}
							</div>
						{/if}
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
        /* Standard drawer pattern: kept in DOM (so text browsers + crawlers see the
           links) and slid off-screen until opened. `inert` on the element blocks focus
           and pointer events when closed, so keyboard users don't tab into it.
           `visibility: hidden` after the slide-out animation finishes so the element
           is also hidden to accessibility tools and headless tests (Playwright's
           `toBeHidden`). Re-shown instantly on open so the slide-in can play. */
        transform: translateX(-110%);
        visibility: hidden;
        transition: transform 0.1s ease, visibility 0s linear 0.1s;
    }

    .nav-menu.open {
        transform: translateX(0);
        visibility: visible;
        transition: transform 0.1s ease, visibility 0s linear 0s;
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
        -webkit-user-select: none;
        user-select: none;
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

    .menu-desc {
        font-size: 0.7rem;
        color: #9ca3af;
        font-weight: normal;
    }

    .unread-badge {
        margin-left: auto;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 18px;
        height: 18px;
        padding: 0 5px;
        box-sizing: border-box;
        border-radius: 9px;
        background: #2563eb;
        color: #fff;
        font-size: 0.7rem;
        font-weight: 700;
        line-height: 1;
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

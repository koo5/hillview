<svelte:head>
	<title>About - Hillview</title>
</svelte:head>

<script lang="ts">
    import { Info, MapPin, Camera, Globe, Github, Heart, FileText, Shield, Mail } from 'lucide-svelte';
    import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
    import StandardBody from '$lib/components/StandardBody.svelte';
    import { getCurrentProviderConfig, getProviderDisplayName, currentTileProvider } from '$lib/tileProviders';
    import { openExternalUrl } from '$lib/urlUtils';
    import { onMount } from 'svelte';
    import { TAURI } from '$lib/tauri';

    let appVersion = __APP_VERSION__;

    onMount(async () => {
        // In Tauri context, get the version from the native API
        if (TAURI) {
            try {
                const { getVersion } = await import('@tauri-apps/api/app');
                appVersion = await getVersion();
            } catch (e) {
                console.warn('Failed to get Tauri version:', e);
            }
        }
    });

    const technologies = [
        { name: 'SvelteKit', url: 'https://kit.svelte.dev' },
        { name: 'TypeScript', url: 'https://www.typescriptlang.org' },
        { name: 'Tauri', url: 'https://tauri.app' },
        { name: 'Leaflet', url: 'https://leafletjs.com' },
        { name: 'Lucide Icons', url: 'https://lucide.dev' },
        { name: 'Vite', url: 'https://vitejs.dev' }
    ];

    // Get current tile provider config
    $: tileConfig = getCurrentProviderConfig();
    $: tileProviderName = getProviderDisplayName($currentTileProvider);

    // Process attribution HTML to handle external links
    function processAttributionHTML(html: string): string {
        if (!html) return '';

        // Add target="_blank" and rel="noopener noreferrer" to all links
        // Also add a custom data attribute to identify them for click handling
        return html.replace(
            /<a([^>]*)href="([^"]*)"([^>]*)>/gi,
            '<a$1href="$2"$3 target="_blank" rel="noopener noreferrer" data-external-link="true">'
        );
    }

    // Handle click events on external links
    async function handleAttributionClick(event: Event) {
        const target = event.target as HTMLElement;
        const link = target.closest('a[data-external-link="true"]') as HTMLAnchorElement;

        if (link && link.href) {
            event.preventDefault(); // Prevent default navigation

            console.log('Opening external attribution link:', link.href);

            await openExternalUrl(link.href);
        }
    }
</script>

<StandardHeaderWithAlert
    title="About Hillview"
    showMenuButton={true}
    fallbackHref="/"
/>

<StandardBody>

    <header class="about-header">
        <div class="app-icon">
            <img src="/icons/icon.png" alt="Hillview Icon" width="48" height="48" />
        </div>
        <h1>Hillview</h1>
        <p class="version">Version {appVersion}</p>
        <p class="tagline">Identify what you're looking at from any hilltop</p>
    </header>

    <section class="about-section">
        <h2>About Hillview</h2>
        <p>
            Ever stood on a hilltop wondering "What am I looking at?" Hillview solves this age-old problem by using
            geotagged photos with directional data to help you identify distant landmarks, mountain peaks, and other
            features from any viewpoint. By combining GPS coordinates with compass bearing information, Hillview creates
            a directional photo database that turns your device into a smart viewfinder for the landscape around you.
        </p>
        <p>
            Whether you're hiking, exploring new cities, or just curious about your surroundings, Hillview helps you
            understand what you're seeing by showing you photos taken from other positions pointing in the same direction.
        </p>
    </section>

	<section class="about-section">
		<h2>Known issues</h2>
		<div class="attribution-links" on:click={handleAttributionClick} role="presentation">
		<p>
			Hillview is an early access project and has some rough edges. There is a list of <a href="https://github.com/koo5/hillview/issues/47" target="_blank" rel="noopener noreferrer" data-external-link="true">
			known issues</a>
			Please check it out and report any bugs or feature requests on our <a href="https://github.com/koo5/hillview/issues" target="_blank" rel="noopener noreferrer" data-external-link="true">GitHub issue tracker</a>
		</p>
		</div>
	</section>

    <section class="attribution-section">
        <h2>Acknowledgments</h2>
        <p>
            Hillview is built with modern web technologies and open-source libraries.
            We're grateful to the open-source community and photo services that make this project possible.
        </p>

        <h3>Map Data</h3>
        <div class="map-attribution">
            <p class="current-provider">
                <strong>Current Tile Provider:</strong> {tileProviderName}
            </p>
            <div
                class="attribution-text"
                on:click={handleAttributionClick}
                role="presentation"
            >
                {@html processAttributionHTML(tileConfig.attribution)}
            </div>
        </div>

        <h3>Libraries & Technologies</h3>
        <div class="attribution-links" on:click={handleAttributionClick} role="presentation">
            {#each technologies as tech}
                <a href={tech.url} target="_blank" rel="noopener noreferrer" data-external-link="true">
                    {tech.name}
                </a>
            {/each}
        </div>

        <h3>Services</h3>
        <div class="attribution-links" on:click={handleAttributionClick} role="presentation">
            <a href="https://tracestrack.com" target="_blank" rel="noopener noreferrer" data-external-link="true">
                <MapPin size={16} />
                TracesTrack
            </a>
            <a href="https://mapillary.com" target="_blank" rel="noopener noreferrer" data-external-link="true">
                <Camera size={16} />
                Mapillary
            </a>
        </div>

    </section>

    <section class="source-section">
        <h2>Source Code</h2>
        <p>
            Hillview is source-available software. You can view the source code, report issues, or contribute to the project on GitHub.
        </p>
        <div class="attribution-links" on:click={handleAttributionClick} role="presentation">
            <a href="https://github.com/koo5/hillview" target="_blank" rel="noopener noreferrer" data-external-link="true">
                <Github size={16} />
                GitHub Repository
            </a>
        </div>
    </section>

    <section class="legal-section">
        <h2>Legal</h2>
        <p>
            Please review our legal policies and terms of use.
        </p>
        <div class="attribution-links">
            <a href="/terms" class="legal-link">
                <FileText size={16} />
                Terms of Service
            </a>
            <a href="/privacy" class="legal-link">
                <Shield size={16} />
                Privacy Policy
            </a>
        </div>
    </section>

    <section class="contact-section">
        <h2>Contact Us</h2>
        <p>
            Have questions, feedback, or suggestions? We'd love to hear from you!
        </p>
        <div class="attribution-links">
            <a href="/contact">
                <Mail size={16} />
                Send us a message
            </a>
        </div>
    </section>


    <footer class="about-footer">
        <p>&copy; 2026 Hillview. Made with <Heart size={16} class="heart-icon" /> for photographers and explorers.</p>
    </footer>
</StandardBody>

<style>
    .about-header {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        line-height: 1.6;
        color: #374151;
        text-align: center;
		padding: 32px 16px;
        margin-bottom: 48px;
        position: relative;
        z-index: 10;
    }

    .app-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 20px;
        color: white;
        margin-bottom: 16px;
        box-shadow: 0 10px 25px rgba(22, 163, 74, 0.4);
    }

    .about-header h1 {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f2937;
        margin: 0 0 8px 0;
    }

    .version {
        font-size: 1rem;
        color: #6b7280;
        margin: 0 0 8px 0;
        font-family: monospace;
    }

    .tagline {
        font-size: 1.125rem;
        color: #4b5563;
        margin: 0;
        font-style: italic;
    }

    .about-section {
        margin-bottom: 48px;
        background: rgba(255, 255, 255, 0.8);
        padding: 32px;
        border-radius: 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .about-section h2,
    .attribution-section h2,
    .contact-section h2 {
        font-size: 1.5rem;
        font-weight: 600;
        color: #1f2937;
        margin: 0 0 24px 0;
    }

    .attribution-section h3 {
        font-size: 1.125rem;
        font-weight: 600;
        color: #374151;
        margin: 24px 0 16px 0;
    }

    .attribution-section h3:first-of-type {
        margin-top: 0;
    }

    .about-section p {
        font-size: 1.125rem;
        color: #4b5563;
        margin: 0;
    }


    .attribution-section,
    .contact-section,
    .source-section,
    .legal-section {
        margin-bottom: 48px;
        background: rgba(255, 255, 255, 0.8);
        padding: 32px;
        border-radius: 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .attribution-section p,
    .contact-section p,
    .source-section p,
    .legal-section p {
        color: #4b5563;
        margin-bottom: 16px;
    }

    .attribution-links {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
    }

    .attribution-links a {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 16px;
        color: #4f46e5;
        text-decoration: none;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        transition: all 0.2s ease;
        font-size: 0.875rem;
        position: relative;
    }

    .attribution-links a:hover {
        background: #f9fafb;
        border-color: #4f46e5;
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(79, 70, 229, 0.1);
    }

    .attribution-links a[data-external-link="true"]:after {
        content: '↗';
        font-size: 0.7em;
        margin-left: 4px;
        opacity: 0.6;
        transition: opacity 0.2s ease;
    }

    .attribution-links a[data-external-link="true"]:hover:after {
        opacity: 1;
    }

    .map-attribution {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 24px;
    }

    .current-provider {
        color: #374151;
        margin: 0 0 12px 0;
        font-size: 0.9rem;
    }

    .attribution-text {
        font-size: 0.875rem;
        color: #6b7280;
        line-height: 1.5;
        cursor: default;
    }

    .attribution-text :global(a) {
        color: #4f46e5;
        text-decoration: underline;
        cursor: pointer;
        transition: color 0.2s ease;
    }

    .attribution-text :global(a:hover) {
        color: #3730a3;
        text-decoration-color: #3730a3;
    }

    .attribution-text :global(a[data-external-link="true"]) {
        position: relative;
    }

    .attribution-text :global(a[data-external-link="true"]:after) {
        content: '↗';
        font-size: 0.75em;
        margin-left: 2px;
        opacity: 0.7;
    }

    .about-footer {
        text-align: center;
        padding-top: 32px;
        border-top: 1px solid #e5e7eb;
    }

    .about-footer p {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 4px;
        color: #6b7280;
        margin: 0;
    }

    .about-footer :global(.heart-icon) {
        color: #ef4444;
    }

    /* Responsive adjustments */
    @media (max-width: 768px) {

        .about-header h1 {
            font-size: 2rem;
        }


        .attribution-links {
            flex-direction: column;
        }

        .about-footer p {
            flex-direction: column;
            gap: 8px;
        }
    }
</style>

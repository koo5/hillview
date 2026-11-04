<script lang="ts">
    import { Globe, Map, Award, Camera, Smartphone, SquarePlus } from 'lucide-svelte';
    import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
    import StandardBody from '$lib/components/StandardBody.svelte';
    import PhotoHead from '$lib/components/PhotoHead.svelte';
    import { HILLVIEW_BASE_URL } from '$lib/urlUtilsServer';
    import MyExternalLink from "$lib/components/MyExternalLink.svelte";

    // appActions pulls in the app/map store modules; lazy-load it on click to
    // keep this page SSR-safe for crawlers (same as the About page).
    async function takePhoto() {
        const { openCamera } = await import('$lib/appActions');
        openCamera();
    }
</script>

<!-- Many visitors land here from search engines and AI chatbots asking for "an app".
     The web app is the most up-to-date Hillview while the new Android app is being
     built, so this page leads with "no download needed" and keeps the Play listing
     as a secondary option. -->
<PhotoHead
    title="Get Hillview - no download needed"
    description="Hillview runs right in your browser on any phone or computer — explore the photo map of annotated panoramas and hilltop views, and add your own photos. No install needed."
    ogType="website"
    ogImage={{ url: `${HILLVIEW_BASE_URL}/og-card.png`, width: 1200, height: 630 }}
    canonicalUrl={`${HILLVIEW_BASE_URL}/download`}
/>

<StandardHeaderWithAlert
    title="Get Hillview"
    showMenuButton={true}
    fallbackHref="/"
/>

<StandardBody>

    <div class="content">
        <div class="hero">
            <div class="icon-container">
                <Globe size={64} />
            </div>
            <h2 data-testid="download-no-install-heading">No download needed</h2>
            <p class="description">
                Hillview works right here in your browser — on Android, iPhone or a computer.
                Everything is on the website: the map, the panoramas, the labels, and taking
                and uploading your own photos.
            </p>

            <div class="cta-row">
                <a href="/" class="cta primary" data-testid="download-open-map">
                    <Map size={20} />
                    Open the map
                </a>
                <a href="/bestof" class="cta" data-testid="download-bestof">
                    <Award size={20} />
                    Browse the best views
                </a>
            </div>

            <ul class="features">
                <li>
                    <Camera size={18} />
                    <span>
                        <a href="/" on:click|preventDefault={takePhoto} data-testid="download-take-photo">Take a photo</a>
                        with your phone's camera, straight from the browser.
                    </span>
                </li>
                <li>
                    <SquarePlus size={18} />
                    <span>
                        Want an icon on your home screen? Use your browser's
                        <em>Add to Home screen</em> (or <em>Install app</em>) — it opens like an app,
                        without a store.
                    </span>
                </li>
            </ul>
        </div>

        <div class="android-section" data-testid="download-android-section">
            <h3><Smartphone size={18} /> The Android app</h3>
            <p>
                There is also an Android app on Google Play. Heads-up: it's an older version and
                is falling behind the website while we build a brand-new one, so for now the website
                is the best way to use Hillview.
            </p>

            <p class="play-link" data-testid="download-play-store-link">
                If you'd still like it:
                <MyExternalLink href="https://play.google.com/store/apps/details?id=cz.hillview">
                    Hillview on Google Play
                </MyExternalLink>
            </p>

            <p class="testing-link">
                Want the latest changes before they ship? Join the
                <MyExternalLink href="https://play.google.com/apps/testing/cz.hillview">
                    closed testing program
                </MyExternalLink>.
            </p>

            <p class="brave-testing-link">
                Feeling brave and want to try development builds, or taste the brand-new, faster, better, native android app? Grab them on the
                <MyExternalLink href="https://hillview.cz/downloads/">
                    development downloads
                </MyExternalLink> page.
            </p>
        </div>
    </div>
</StandardBody>

<style>
    .content {
        max-width: 800px;
        margin: 0 auto;
        padding: 2.5rem;
        text-align: center;
    }

    .hero {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        padding: 2rem;
    }

    .icon-container {
        margin-bottom: 0.5rem;
        opacity: 0.9;
    }

    .hero h2 {
        font-size: 1.6rem;
        margin: 0 0 0.5rem 0;
        font-weight: 600;
    }

    .description {
        opacity: 0.85;
        margin: 0 auto 1.5rem;
        max-width: 34rem;
        line-height: 1.5;
    }

    .cta-row {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 0.75rem;
        margin: 1.5rem 0;
    }

    .cta {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.75rem 1.25rem;
        border-radius: 8px;
        border: 1px solid #3b82f6;
        color: #3b82f6;
        text-decoration: none;
        font-weight: 500;
        font-size: 1.05rem;
    }

    .cta.primary {
        background: #3b82f6;
        color: white;
    }

    .cta:hover {
        filter: brightness(1.1);
    }

    .features {
        list-style: none;
        padding: 0;
        margin: 1.5rem auto 0;
        max-width: 34rem;
        text-align: left;
        font-size: 0.95rem;
    }

    .features li {
        display: flex;
        gap: 0.6rem;
        align-items: flex-start;
        margin: 0.75rem 0;
        opacity: 0.85;
    }

    .features li :global(svg) {
        flex-shrink: 0;
        margin-top: 0.15rem;
    }

    .android-section {
        margin-top: 2.5rem;
        font-size: 0.9rem;
        opacity: 0.85;
    }

    .android-section h3 {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        font-size: 1.05rem;
        font-weight: 500;
        margin: 0 0 0.5rem 0;
    }

    .android-section p {
        max-width: 34rem;
        margin-left: auto;
        margin-right: auto;
        line-height: 1.5;
    }

    .play-link {
        margin: 1rem auto;
    }

    .testing-link {
        margin-top: 2rem;
        padding-top: 1.5rem;
        border-top: 1px solid rgba(255, 255, 255, 0.2);
        font-size: 0.85rem;
        opacity: 0.8;
    }

    .brave-testing-link {
        margin-top: 2rem;
        padding-top: 1.5rem;
        border-top: 1px solid rgba(255, 255, 255, 0.2);
        font-size: 0.7rem;
        opacity: 0.7;
    }

    @media (max-width: 768px) {
        .content {
            padding: 1rem;
        }

        .hero {
            padding: 1.5rem;
        }

        .cta {
            flex: 1 1 100%;
            justify-content: center;
        }
    }
</style>

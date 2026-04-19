<svelte:head>
	<title>Download - Hillview</title>
	<meta name="description" content="Download the Hillview Android app — photo mapping on your phone." />
</svelte:head>

<script lang="ts">
    import { Smartphone } from 'lucide-svelte';
    import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
    import StandardBody from '$lib/components/StandardBody.svelte';
    import MyExternalLink from "$lib/components/MyExternalLink.svelte";
</script>

<StandardHeaderWithAlert
    title="Download Hillview"
    showMenuButton={true}
    fallbackHref="/"
/>

<StandardBody>

    <div class="content">
        <div class="hero">
            <div class="icon-container">
                <Smartphone size={64} />
            </div>
        </div>

        <div class="download-section">
            <h2>Hillview on Android</h2>
            <p class="description">
                Hillview is live on Google Play. Install it to explore the photo map and capture geotagged photos on the go.
            </p>

            <div class="play-link" data-testid="download-play-store-link">
                <MyExternalLink href="https://play.google.com/store/apps/details?id=cz.hillview">
                    Get it on Google Play
                </MyExternalLink>
            </div>

            <p class="testing-link">
                Want the latest changes before they ship? Join the
                <MyExternalLink href="https://play.google.com/apps/testing/cz.hillview">
                    closed testing program
                </MyExternalLink>.
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
        margin-bottom: 0rem;
    }

    .icon-container {
        margin-bottom: 0.5rem;
        opacity: 0.9;
    }

    .download-section {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        padding: 2rem;
    }

    .download-section h2 {
        font-size: 1.5rem;
        margin: 0 0 0.5rem 0;
        font-weight: 500;
    }

    .description {
        opacity: 0.85;
        margin-bottom: 1.5rem;
    }

    .play-link {
        margin: 1.5rem 0;
        font-size: 1.15rem;
    }

    .testing-link {
        margin-top: 2rem;
        padding-top: 1.5rem;
        border-top: 1px solid rgba(255, 255, 255, 0.2);
        font-size: 0.9rem;
        opacity: 0.8;
    }

    @media (max-width: 768px) {
        .content {
            padding: 1rem;
        }

        .download-section {
            padding: 1.5rem;
        }
    }
</style>

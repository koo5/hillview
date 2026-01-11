<script lang="ts">
    import { Download, Smartphone } from 'lucide-svelte';
    import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
    import StandardBody from '$lib/components/StandardBody.svelte';
</script>

<StandardHeaderWithAlert
    title="Download App"
    showMenuButton={true}
    fallbackHref="/"
/>

<StandardBody>

    <div class="content">
        <div class="hero">
            <div class="icon-container">
                <Smartphone size={64} />
            </div>
            <h1>Download Hillview</h1>
            <p class="subtitle">Explore and map your photos on Android</p>
        </div>

        <div class="download-section">

			<Download size={24} />
			Download Android APK from Google Play - <b>Coming Soon!</b>


        </div>
    </div>
</StandardBody>

<style>




    .content {
        max-width: 800px;
        margin: 0 auto;
        padding: 2rem;
        text-align: center;
    }

    .hero {
        margin-bottom: 3rem;
    }

    .icon-container {
        margin-bottom: 1.5rem;
        opacity: 0.9;
    }

    h1 {
        font-size: 3rem;
        margin: 0 0 1rem 0;
        font-weight: 300;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
    }

    .subtitle {
        font-size: 1.3rem;
        margin: 0;
        opacity: 0.9;
        font-weight: 300;
    }

    .download-section {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 2.5rem;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }

    @media (max-width: 768px) {
        .content {
            padding: 1rem;
        }

        h1 {
            font-size: 2.5rem;
        }

        .subtitle {
            font-size: 1.1rem;
        }

        .download-section {
            padding: 1.5rem;
        }
    }
</style>

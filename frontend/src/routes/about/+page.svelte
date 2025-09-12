<script lang="ts">
    import { Info, MapPin, Camera, Globe, Github, Heart, Compass } from 'lucide-svelte';
    import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
    import StandardBody from '../../components/StandardBody.svelte';
    import { getCurrentProviderConfig, getProviderDisplayName, currentTileProvider } from '$lib/tileProviders';

    const appVersion = '0.0.1';
    const features = [
        {
            icon: Compass,
            title: 'Directional Photos',
            description: 'Photos with compass bearing data help you identify what you\'re looking at from your viewpoint.'
        },
        {
            icon: MapPin,
            title: 'Hillview Navigation',
            description: 'Stand on a hill and use directional photos to identify distant landmarks, peaks, and features.'
        },
        {
            icon: Camera,
            title: 'Smart Capture',
            description: 'Capture photos with GPS coordinates and compass bearing to build your hillview database.'
        },
        {
            icon: Globe,
            title: 'Multiple Sources',
            description: 'Import photos from various sources to create comprehensive directional reference points.'
        }
    ];

    const technologies = [
        'SvelteKit',
        'TypeScript', 
        'Tauri',
        'Leaflet',
        'Lucide Icons',
        'Vite'
    ];

    // Get current tile provider config
    $: tileConfig = getCurrentProviderConfig();
    $: tileProviderName = getProviderDisplayName($currentTileProvider);
</script>

<StandardHeaderWithAlert 
    title="About Hillview" 
    showMenuButton={true}
    fallbackHref="/"
/>

<StandardBody>

    <header class="about-header">
        <div class="app-icon">
            <MapPin size={48} />
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
            understand what you're seeing by showing you photos taken from similar positions pointing in the same direction.
        </p>
    </section>

    <section class="features-section">
        <h2>Features</h2>
        <div class="features-grid">
            {#each features as feature}
                <div class="feature-card">
                    <div class="feature-icon">
                        <svelte:component this={feature.icon} size={24} />
                    </div>
                    <h3>{feature.title}</h3>
                    <p>{feature.description}</p>
                </div>
            {/each}
        </div>
    </section>

    <section class="tech-section">
        <h2>Built With</h2>
        <div class="tech-grid">
            {#each technologies as tech}
                <span class="tech-tag">{tech}</span>
            {/each}
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
            <div class="attribution-text">
                {@html tileConfig.attribution}
            </div>
        </div>
        
        <h3>Libraries & Technologies</h3>
        <div class="attribution-links">
            <a href="https://leafletjs.com" target="_blank" rel="noopener noreferrer">
                <Globe size={16} />
                Leaflet Maps
            </a>
            <a href="https://lucide.dev" target="_blank" rel="noopener noreferrer">
                <Heart size={16} />
                Lucide Icons
            </a>
            <a href="https://kit.svelte.dev" target="_blank" rel="noopener noreferrer">
                <Info size={16} />
                SvelteKit
            </a>
        </div>

        <h3>Services</h3>
        <div class="attribution-links">
            <a href="https://tracestrack.com" target="_blank" rel="noopener noreferrer">
                <MapPin size={16} />
                TracesTrack
            </a>
            <a href="https://mapillary.com" target="_blank" rel="noopener noreferrer">
                <Camera size={16} />
                Mapillary
            </a>
        </div>


    </section>

    <footer class="about-footer">
        <p>&copy; 2024 Hillview. Made with <Heart size={16} class="heart-icon" /> for photographers and explorers.</p>
    </footer>
</StandardBody>

<style>
    .about-header {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        line-height: 1.6;
        color: #374151;
        text-align: center;
        margin-bottom: 48px;
        position: relative;
        z-index: 10;
    }

    .app-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 80px;
        height: 80px;
        background: linear-gradient(135deg, #16a34a, #15803d);
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
    .features-section h2,
    .tech-section h2,
    .attribution-section h2 {
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

    .features-section {
        margin-bottom: 48px;
        background: rgba(255, 255, 255, 0.8);
        padding: 32px;
        border-radius: 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .features-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 24px;
    }

    .feature-card {
        padding: 24px;
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }

    .feature-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }

    .feature-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 48px;
        height: 48px;
        background: linear-gradient(135deg, #dcfce7, #bbf7d0);
        border-radius: 12px;
        color: #15803d;
        margin-bottom: 16px;
    }

    .feature-card h3 {
        font-size: 1.125rem;
        font-weight: 600;
        color: #1f2937;
        margin: 0 0 8px 0;
    }

    .feature-card p {
        color: #6b7280;
        margin: 0;
    }

    .tech-section {
        margin-bottom: 48px;
        background: rgba(255, 255, 255, 0.8);
        padding: 32px;
        border-radius: 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .tech-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
    }

    .tech-tag {
        padding: 8px 16px;
        background: #f3f4f6;
        color: #374151;
        border-radius: 20px;
        font-size: 0.875rem;
        font-weight: 500;
        transition: background-color 0.2s ease;
    }

    .tech-tag:hover {
        background: #e5e7eb;
    }

    .attribution-section {
        margin-bottom: 48px;
        background: rgba(255, 255, 255, 0.8);
        padding: 32px;
        border-radius: 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .attribution-section p {
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
    }

    .attribution-links a:hover {
        background: #f9fafb;
        border-color: #4f46e5;
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
    }

    .attribution-text :global(a) {
        color: #4f46e5;
        text-decoration: underline;
    }

    .attribution-text :global(a:hover) {
        color: #3730a3;
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

        .features-grid {
            grid-template-columns: 1fr;
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
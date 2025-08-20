<script lang="ts">
    import { Download, Smartphone, ArrowLeft } from 'lucide-svelte';
</script>

<div class="download-page">
    <nav class="nav-header">
        <a href="/" class="back-link">
            <ArrowLeft size={20} />
            Back to Map
        </a>
    </nav>

    <div class="content">
        <div class="hero">
            <div class="icon-container">
                <Smartphone size={64} />
            </div>
            <h1>Download Hillview</h1>
            <p class="subtitle">Explore and map your photos on Android</p>
        </div>

        <div class="download-section">
            <a href="/downloads/hillview.apk" download class="download-button" data-testid="download-apk-button">
                <Download size={24} />
                Download Android APK
            </a>
            
            <div class="info">
                <h3>Installation Instructions</h3>
                <ol>
                    <li>Download the APK file above</li>
                    <li>Enable "Install from unknown sources" in your Android settings</li>
                    <li>Open the downloaded APK file and follow the installation prompts</li>
                    <li>Launch Hillview and start mapping your photos!</li>
                </ol>
            </div>

            <div class="requirements">
                <h3>System Requirements</h3>
                <ul>
                    <li>Android 7.0 (API level 24) or higher</li>
                    <li>Camera permissions for photo capture</li>
                    <li>Location permissions for GPS tracking</li>
                    <li>Internet connection for map data</li>
                </ul>
            </div>
        </div>
    </div>
</div>

<style>
    .download-page {
        min-height: 100vh;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 0;
        margin: 0;
    }

    .nav-header {
        padding: 1rem 2rem;
    }

    .back-link {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        color: rgba(255, 255, 255, 0.9);
        text-decoration: none;
        font-size: 1rem;
        transition: color 0.2s ease;
    }

    .back-link:hover {
        color: white;
    }

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

    .download-button {
        display: inline-flex;
        align-items: center;
        gap: 0.75rem;
        background: #4a90e2;
        color: white;
        text-decoration: none;
        padding: 1rem 2rem;
        border-radius: 8px;
        font-size: 1.2rem;
        font-weight: 500;
        margin-bottom: 2.5rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 12px rgba(74, 144, 226, 0.3);
    }

    .download-button:hover {
        background: #357abd;
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(74, 144, 226, 0.4);
    }

    .info, .requirements {
        text-align: left;
        margin-bottom: 2rem;
    }

    .info:last-child, .requirements:last-child {
        margin-bottom: 0;
    }

    h3 {
        font-size: 1.5rem;
        margin: 0 0 1rem 0;
        font-weight: 400;
    }

    ol, ul {
        padding-left: 1.5rem;
        line-height: 1.6;
    }

    li {
        margin-bottom: 0.5rem;
        opacity: 0.9;
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

        .download-button {
            padding: 0.875rem 1.5rem;
            font-size: 1.1rem;
        }
    }
</style>
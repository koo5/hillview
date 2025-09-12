<script lang="ts">
    import { sources, type Source, type subtype } from '$lib/data.svelte';
    import { fetchSourcePhotos } from '$lib/sources';
    import { localStorageSharedStore } from '$lib/svelte-shared-store';
    import { Plus, Trash2, Globe, MapPin, Folder, Camera } from 'lucide-svelte';
    import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
    import StandardBody from '../../components/StandardBody.svelte';
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';

    // Store for custom sources - using regular Source interface
    const customSources = localStorageSharedStore<Source[]>('customSources', []);

    // Form state for adding new source
    let newSourceName = '';
    let newSourceUrl = '';
    let newSourcePath = '';
    let newSourceType: 'stream' | 'device' = 'stream';
    let newsubtype: subtype = 'folder';
    let showAddForm = false;
    let formError = '';

    // Built-in sources info
    const builtInSourcesInfo = [
        {
            id: 'hillview',
            name: 'Hillview',
            description: 'The main Hillview photo collection. A curated set of geotagged photos.',
            icon: Globe,
            color: '#000'
        },
        {
            id: 'mapillary',
            name: 'Mapillary',
            description: 'Street-level imagery from the Mapillary platform. Community-contributed photos from around the world.',
            icon: MapPin,
            color: '#888'
        },
        {
            id: 'device',
            name: 'My Device',
            description: 'Photos captured directly from your device using the app.',
            icon: MapPin,
            color: '#4a90e2'
        }
    ];

    function toggleSource(sourceId: string) {
        sources.update(srcs => {
            const source = srcs.find(s => s.id === sourceId);
            if (source) {
                source.enabled = !source.enabled;
            }
            return srcs;
        });
        
        // When disabling, the data.svelte.ts subscription will handle filtering
        // When enabling a source, we need to fetch its photos
        const source = $sources.find(s => s.id === sourceId);
        if (source && source.enabled && source.type === 'device') {
            // Only reload this specific source when enabling
            fetchSourcePhotos(sourceId);
        }
    }

    function validateUrl(url: string): boolean {
        try {
            new URL(url);
            return true;
        } catch {
            return false;
        }
    }

    function addCustomSource() {
        formError = '';

        if (!newSourceName.trim()) {
            formError = 'Please enter a name for the source';
            return;
        }

        if (newSourceType === 'stream') {
            if (!newSourceUrl.trim()) {
                formError = 'Please enter a URL for the photo source';
                return;
            }

            if (!validateUrl(newSourceUrl)) {
                formError = 'Please enter a valid URL';
                return;
            }
        } else if (newSourceType === 'device') {
            if (newsubtype === 'folder' && !newSourcePath.trim()) {
                formError = 'Please enter a folder path';
                return;
            }
        }

        const newSource: Source = {
            id: `custom_${Date.now()}`,
            name: newSourceName.trim(),
            type: newSourceType,
            ...(newSourceType === 'stream' ? { url: newSourceUrl.trim() } : {}),
            ...(newSourceType === 'device' ? { 
                subtype: newsubtype,
                ...(newsubtype === 'folder' ? { path: newSourcePath.trim() } : {})
            } : {}),
            requests: [],
            enabled: false,
            color: `#${Math.floor(Math.random()*16777215).toString(16)}`
        };

        customSources.update(srcs => [...srcs, newSource]);

        // Add to main sources store
        sources.update(srcs => [...srcs, newSource]);

        // Reset form
        newSourceName = '';
        newSourceUrl = '';
        newSourcePath = '';
        newSourceType = 'stream';
        newsubtype = 'folder';
        showAddForm = false;
    }

    function removeCustomSource(sourceId: string) {
        customSources.update(srcs => srcs.filter(s => s.id !== sourceId));
        sources.update(srcs => srcs.filter(s => s.id !== sourceId));
    }

    // Initialize custom sources in main sources store
    onMount(() => {
        const customSrcs = $customSources;
        if (customSrcs.length > 0) {
            sources.update(srcs => {
                // Add custom sources that aren't already in the store
                const existingIds = new Set(srcs.map(s => s.id));
                const newSources = customSrcs
                    .filter(cs => !existingIds.has(cs.id))
                    .map(cs => ({ ...cs, requests: [] }));
                return [...srcs, ...newSources];
            });
        }
    });
</script>

<StandardHeaderWithAlert 
    title="Photo Sources" 
    showMenuButton={true}
    fallbackHref="/"
/>

<StandardBody>
    
    <div class="sources-description">
        <p>Manage where photos are loaded from</p>
    </div>

    <!-- Built-in Sources -->
    <div class="section">
        <h2>Built-in Sources</h2>
        <div class="sources-list">
            {#each builtInSourcesInfo as sourceInfo}
                {@const source = $sources.find(s => s.id === sourceInfo.id)}
                {#if source}
                    <div class="source-item">
                        <div class="source-header">
                            <div class="source-info">
                                <div class="source-icon" style="background-color: {sourceInfo.color}20">
                                    <svelte:component this={sourceInfo.icon} style="color: {sourceInfo.color}" />
                                </div>
                                <div class="source-details">
                                    <h3>{sourceInfo.name}</h3>
                                    <p class="description">{sourceInfo.description}</p>
                                    {#if source.requests.length > 0}
                                        <p class="loading">Loading...</p>
                                    {/if}
                                </div>
                            </div>
                            <label class="toggle" data-testid="source-toggle-{source.id}">
                                <input 
                                    type="checkbox" 
                                    checked={source.enabled}
                                    on:change={() => toggleSource(source.id)}
                                    data-testid="source-checkbox-{source.id}"
                                >
                                <span class="slider"></span>
                            </label>
                        </div>
                    </div>
                {/if}
            {/each}
        </div>
    </div>

    <!-- Custom Sources -->
    <div class="section">
        <div class="section-header">
            <h2>Custom Sources</h2>
            <div class="add-buttons">
                <button
                    on:click={() => {newSourceType = 'stream'; showAddForm = true;}}
                    class="add-button"
                >
                    <Globe />
                    Add Stream Source
                </button>
                <button
                    on:click={() => {newSourceType = 'device'; showAddForm = true;}}
                    class="add-button"
                >
                    <MapPin />
                    Add Device Source
                </button>
            </div>
        </div>

        {#if showAddForm}
            <div class="form-container">
                <h3>{newSourceType === 'stream' ? 'Add Stream Source' : 'Add Device Source'}</h3>
                <div class="form-fields">
                    <div class="field">
                        <label for="sourceName">Name</label>
                        <input
                            id="sourceName"
                            type="text"
                            bind:value={newSourceName}
                            placeholder={newSourceType === 'stream' ? 'My Photo Stream' : 'My Device Photos'}
                        >
                    </div>
                    {#if newSourceType === 'stream'}
                        <div class="field">
                            <label for="sourceUrl">URL</label>
                            <input
                                id="sourceUrl"
                                type="url"
                                bind:value={newSourceUrl}
                                placeholder="https://example.com/api"
                            >
                            <p class="help-text">The URL should point to a JSON file with photo metadata</p>
                        </div>
                    {:else if newSourceType === 'device'}
                        <div class="field">
                            <label for="subtype">Device Source Type</label>
                            <select id="subtype" bind:value={newsubtype}>
                                <option value="folder">Custom Folder</option>
                                <option value="gallery">Device Gallery</option>
                            </select>
                        </div>
                        {#if newsubtype === 'folder'}
                            <div class="field">
                                <label for="sourcePath">Folder Path</label>
                                <input
                                    id="sourcePath"
                                    type="text"
                                    bind:value={newSourcePath}
                                    placeholder="/path/to/photos"
                                >
                                <p class="help-text">Path to a folder containing photos with GPS metadata</p>
                            </div>
                        {:else if newsubtype === 'gallery'}
                            <p class="help-text">Accesses all photos indexed by the device's media API</p>
                        {/if}
                    {/if}
                    {#if formError}
                        <p class="error">{formError}</p>
                    {/if}
                    <div class="form-buttons">
                        <button
                            on:click={addCustomSource}
                            class="button primary"
                        >
                            Add
                        </button>
                        <button
                            on:click={() => {showAddForm = false; formError = '';}}
                            class="button secondary"
                        >
                            Cancel
                        </button>
                    </div>
                </div>
            </div>
        {/if}

        <div class="sources-list">
            {#each $customSources as customSource}
                {@const source = $sources.find(s => s.id === customSource.id)}
                {#if source}
                    <div class="source-item">
                        <div class="source-header">
                            <div class="source-info custom">
                                <div class="source-details">
                                    <h3>{customSource.name}</h3>
                                    <p class="url">{customSource.type === 'stream' ? customSource.url : (customSource.subtype === 'folder' ? customSource.path : `Device (${customSource.subtype})`)}</p>
                                    <p class="source-type">{customSource.type === 'stream' ? 'Stream Source' : `Device Source (${customSource.subtype})`}</p>
                                    {#if source.requests.length > 0}
                                        <p class="loading">Loading...</p>
                                    {/if}
                                </div>
                            </div>
                            <div class="source-controls">
                                <label class="toggle">
                                    <input 
                                        type="checkbox" 
                                        checked={source.enabled}
                                        on:change={() => toggleSource(source.id)}
                                    >
                                    <span class="slider"></span>
                                </label>
                                <button
                                    on:click={() => removeCustomSource(customSource.id)}
                                    class="remove-button"
                                    title="Remove source"
                                >
                                    <Trash2 />
                                </button>
                            </div>
                        </div>
                    </div>
                {/if}
            {/each}
            {#if $customSources.length === 0 && !showAddForm}
                <p class="empty-state">No custom sources added yet</p>
            {/if}
        </div>
    </div>
</StandardBody>

<style>




    .section {
        margin-bottom: 32px;
    }

    .section h2 {
        font-size: 1.25rem;
        font-weight: 600;
        color: #333;
        margin: 0 0 16px 0;
    }

    .section-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
    }

    .sources-list {
        display: flex;
        flex-direction: column;
        gap: 16px;
    }

    .source-item {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }

    .source-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
    }

    .source-info {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        flex: 1;
    }

    .source-info.custom {
        gap: 0;
    }

    .source-icon {
        padding: 8px;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .source-details h3 {
        font-weight: 500;
        color: #1a1a1a;
        margin: 0 0 4px 0;
        font-size: 1rem;
    }

    .description {
        color: #666;
        font-size: 0.875rem;
        margin: 0;
        line-height: 1.4;
    }

    .url {
        color: #666;
        font-size: 0.875rem;
        margin: 4px 0 0 0;
        word-break: break-all;
        line-height: 1.4;
    }

    .source-type {
        color: #888;
        font-size: 0.75rem;
        margin: 2px 0 0 0;
        text-transform: uppercase;
        font-weight: 500;
    }

    .loading {
        color: #2563eb;
        font-size: 0.75rem;
        margin: 8px 0 0 0;
    }

    .source-controls {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-left: 16px;
    }

    .toggle {
        position: relative;
        display: inline-block;
        width: 44px;
        height: 24px;
        cursor: pointer;
    }

    .toggle input {
        opacity: 0;
        width: 0;
        height: 0;
    }

    .slider {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background-color: #ccc;
        border-radius: 24px;
        transition: 0.3s;
    }

    .slider:before {
        position: absolute;
        content: "";
        height: 18px;
        width: 18px;
        left: 3px;
        bottom: 3px;
        background-color: white;
        border-radius: 50%;
        transition: 0.3s;
    }

    input:checked + .slider {
        background-color: #2563eb;
    }

    input:checked + .slider:before {
        transform: translateX(20px);
    }

    .add-buttons {
        display: flex;
        gap: 12px;
    }

    .add-button {
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 8px 12px;
        background: #2563eb;
        color: white;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.875rem;
        transition: background-color 0.2s;
    }

    .add-button:hover {
        background: #1d4ed8;
    }


    .remove-button {
        padding: 8px;
        color: #dc2626;
        background: transparent;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        transition: background-color 0.2s;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .remove-button:hover {
        background: #fef2f2;
    }

    .form-container {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }

    .form-container h3 {
        font-weight: 500;
        color: #1a1a1a;
        margin: 0 0 12px 0;
        font-size: 1rem;
    }

    .form-fields {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .field {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }

    .field label {
        font-size: 0.875rem;
        font-weight: 500;
        color: #374151;
    }

    .field input {
        width: 100%;
        padding: 8px 12px;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        font-size: 0.875rem;
        transition: border-color 0.2s;
        background: white;
    }

    .field input:focus {
        outline: none;
        border-color: #2563eb;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
    }

    .help-text {
        font-size: 0.75rem;
        color: #6b7280;
        margin: 0;
    }

    .error {
        font-size: 0.875rem;
        color: #dc2626;
        margin: 0;
    }

    .form-buttons {
        display: flex;
        gap: 8px;
    }

    .button {
        padding: 8px 16px;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.875rem;
        transition: background-color 0.2s;
    }

    .button.primary {
        background: #2563eb;
        color: white;
    }

    .button.primary:hover {
        background: #1d4ed8;
    }

    .button.secondary {
        background: #f3f4f6;
        color: #374151;
    }

    .button.secondary:hover {
        background: #e5e7eb;
    }

    .empty-state {
        color: #6b7280;
        text-align: center;
        padding: 32px 0;
        margin: 0;
    }


    .source-icon :global(svg) {
        width: 20px;
        height: 20px;
    }

    .add-button :global(svg),
    .remove-button :global(svg) {
        width: 16px;
        height: 16px;
    }
</style>
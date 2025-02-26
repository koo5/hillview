<script>
    import { onMount } from 'svelte';
    import PhotoGallery from './Gallery.svelte';
    import Map from './Map.svelte';
    import { Camera, Compass } from 'lucide-svelte';

    import {app, pos, bearing } from "$lib/data.svelte.js";
    import {fetch_photos} from "$lib/sources.js";
    import {dms} from "$lib/utils.js";
    import {goto} from "$app/navigation";

    onMount(async () => {
        await fetch_photos();
    });



</script>

<div class="min-h-screen bg-gray-100">
    <!-- Header -->
    <header class="bg-white shadow-sm">
        <div class="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
            <div class="flex items-center space-x-8">
                <!-- App Title / Icon -->
                <div class="flex items-center">
                    <Camera class="w-8 h-8 text-blue-600 mr-2" />
                    <h1 class="text-2xl font-bold text-gray-900">Photo Mapper</h1>
                </div>

                <!-- Info: Position & Bearing -->
                <div class="flex items-center space-x-4 text-sm text-gray-600">
                    <div class="flex items-center">
                        <span class="font-medium">Position:</span>
                        <span class="ml-2">
              {($pos.center)}
            </span>
                    </div>
                    <div class="flex items-center">
                        <Compass class="w-4 h-4 mr-1" />
                        <span class="font-medium">Viewing:</span>
                        <span class="ml-2">{$bearing.toFixed(1)}°</span>
                    </div>
                </div>
            </div>

            <!-- Upload Button -->
            <button
                    on:click={() => goto('/upload')}
                    class="flex items-center px-3 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700 transition-colors"
            >
                <span>Upload Photos</span>
            </button>
            <button
                    on:click={() => goto('/sources')}
                    class="flex items-center px-3 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700 transition-colors"
                    >
                <span>Sources</span>
                </button>
        </div>
    </header>

    <!-- Main Content -->
    <main class="max-w-7xl mx-auto px-4 py-6">
        {#if $app.error}
            <div class="mb-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
                error: {$app.error}
            </div>
        {/if}

        <!-- Split: PhotoGallery & Map -->
        <div class="grid grid-cols-2 gap-6 h-[600px]">
            <div class="gallery">
                <PhotoGallery />
            </div>
            <div class="bg-white rounded-lg shadow-lg overflow-hidden">
                <Map />
            </div>
        </div>
    </main>

</div>


<div>
    <pre>
        $app: {JSON.stringify($app, null, 2)}
        $pos: {JSON.stringify($pos, null, 2)}
        </pre>
</div>


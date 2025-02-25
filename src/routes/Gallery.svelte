<script>
    import { ChevronDown, ChevronUp, Download, AlertCircle, RefreshCw } from 'lucide-svelte';

    import {photo_in_front, photo_to_left, photo_to_right, photos_in_range} from "$lib/data.svelte.js";

    let show_debug = false;

</script>

<!-- Main layout -->
<div class="h-full flex flex-col">
    <!-- Header -->
    <div class="p-4 bg-gray-50 border-b flex justify-between items-center">
        <div>
            <h2 class="text-lg font-semibold">{photos_in_range.length} photos</h2>
        </div>
        <button
                on:click={() => (show_debug = !show_debug)}
                class="flex items-center px-2 py-1 text-sm bg-gray-200 rounded hover:bg-gray-300 transition-colors"
        >
            {#if show_debug}
                <ChevronDown class="w-4 h-4" />
            {:else}
                <ChevronUp class="w-4 h-4" />
            {/if}
            <span class="ml-1">Debug</span>
        </button>
    </div>

    <!-- Content -->
    <div class="flex flex-1">

        {#if photo_to_left}
            <img src={photo_to_left.url} alt={photo_to_left.file} class="w-1/2" />
        {/if}
        {#if photo_in_front}
            <img src={photo_in_front.url} alt={photo_in_front.file} class="w-1/2" />
        {/if}
        {#if photo_to_right}
            <img src={photo_to_right.url} alt={photo_to_right.file} class="w-1/2" />
        {/if}

        <!-- Debug sidebar -->
        {#if show_debug}
            <div class="w-64 bg-white overflow-y-auto border-l">
                <div class="p-3 bg-gray-50 border-b sticky top-0">
                    <h3 class="font-medium">Debug Information</h3>
                </div>
                <div class="divide-y">
                    {#each photos_in_range as photo (photo.id)}
                        <div>
                            <a href="{photo.url}" target="_blank" class="block p-3 group hover:bg-gray-100">
                                <div class="font-medium mb-1 truncate flex items-center justify-between">
                                    {photo.file}
                                </div>
                            </a>
                            <div class="space-y-1 text-gray-600">
                                <p>Distance: {photo.distance?.toFixed(2)}km</p>
                                <p>Relative: {photo.bearing?.toFixed(1)}°</p>
                                <p>Direction diff: {photo.directionDiff?.toFixed(1)}°</p>
                                <p>Position: {photo.x?.toFixed(1)}%, {photo.y?.toFixed(1)}%</p>
                                <p>Scale: {photo.scale?.toFixed(2)}</p>
                                <p>Z-Index: {photo.z}</p>
                            </div>
                        </div>
                    {/each}
                </div>
            </div>
        {/if}
    </div>
</div>

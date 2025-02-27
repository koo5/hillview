<script>
</script>    <!-- Header -->

{#if $app.error}
    <div class="mb-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
        error: {$app.error}
    </div>
{/if}


<!-- Small help text -->
<div class="absolute bottom-4 right-4 bg-white p-2 rounded shadow" style="z-index: 30000;">
    <p class="text-sm">Use ← → arrow keys or buttons to rotate the view direction.</p>
</div>

<!--width: {width}, height: {height}-->
<!--centerX: {centerX}, centerY: {centerY}-->
<!--arrowX: {arrowX}, arrowY: {arrowY}-->


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

<!-- Debug sidebar -->
{#if show_debug}
    <div class="w-64 bg-white overflow-y-auto border-l">
        <div class="p-3 bg-gray-50 border-b sticky top-0">
            <h3 class="font-medium">Debug Information</h3>
        </div>
        <div class="divide-y">
            {#each $photos_in_range as photo (photo.id)}
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


<!--<div>-->
<!--    <pre>-->
<!--        $app: {JSON.stringify($app, null, 2)}-->
<!--        $pos: {JSON.stringify($pos, null, 2)}-->
<!--        </pre>-->
<!--</div>-->



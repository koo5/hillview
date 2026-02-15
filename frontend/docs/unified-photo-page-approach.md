# Unified Photo Management Page - Minimal Complexity Approach

## Key Insight
Both platforms need to show:
- Photos with metadata (location, bearing, timestamp)
- Upload status (pending, uploading, completed, failed)
- Storage statistics
- Retry capabilities

The differences are mainly in:
- **Data source**: IndexedDB vs file system
- **Image display**: Blob URLs vs file:// URLs
- **Storage metrics**: Browser quota vs device storage

## Proposed Changes to device-photos/+page.svelte

### 1. Import Platform Adapter (5 lines)
```typescript
import { BROWSER } from '$lib/tauri';
import { photoStorage, type BrowserPhoto } from '$lib/browser/photoStorage';
import { uploadManager } from '$lib/browser/uploadManager';
import { fetchPhotoStats, photoStats, getPlatformName } from '$lib/photoStatsAdapter';
```

### 2. Unified Data Fetching (20 lines)
```typescript
async function fetchPhotos(page: number = 1, append: boolean = false) {
    try {
        isLoading = !append;
        isLoadingMore = append;

        let response;
        if (BROWSER) {
            // Browser: Get from IndexedDB
            const allPhotos = await photoStorage.getAll();
            response = {
                photos: allPhotos.map(adaptBrowserPhoto),
                total_count: allPhotos.length,
                page: page,
                has_more: false // Simple for now
            };
        } else {
            // Tauri: Existing invoke
            response = await invoke('plugin:hillview|get_device_photos', {
                page, page_size: pageSize
            });
        }

        // Rest of existing logic...
        photosData = response;
    } catch (err) {
        // existing error handling
    }
}
```

### 3. Simple Photo Adapter (15 lines)
```typescript
function adaptBrowserPhoto(bp: BrowserPhoto): DevicePhoto {
    return {
        ...bp, // Most fields map directly
        file_path: '', // Not applicable
        file_name: `photo_${bp.id.substring(0, 8)}.jpg`,
        file_hash: '',
        file_size: bp.blob.size,
        bearing: bp.location.heading || 0,
        width: 0, // Could extract if needed
        height: 0,
        upload_status: bp.uploaded ? 'completed' : 'pending',
        retry_count: bp.upload_attempts
    };
}
```

### 4. Conditional Image Handling (10 lines)
```typescript
// Add to script section
function getPhotoUrl(photo) {
    if (BROWSER && photo.blob) {
        return URL.createObjectURL(photo.blob);
    }
    return getDevicePhotoUrl(photo.file_path);
}

// In template
<img src={getPhotoUrl(photo)} />
```

### 5. Platform-Aware Stats Component (No changes needed!)
```svelte
<!-- This already works if we use the adapter -->
<DevicePhotoStats onRefresh={() => fetchPhotos(1, false)} />
```

Just update DevicePhotoStats to use `photoStatsAdapter`:
```typescript
// In DevicePhotoStats.svelte
import { photoStats, fetchPhotoStats } from '$lib/photoStatsAdapter';
// Replace $devicePhotoStats with $photoStats
```

### 6. Platform-Specific Features (15 lines)
```svelte
<!-- Page title shows platform -->
<StandardHeaderWithAlert
    title="{getPlatformName()} Photos"
    showMenuButton={true}
    fallbackHref="/photos"
/>

<!-- File path only for Tauri -->
{#if !BROWSER && photo.file_path}
    <div class="photo-path">
        <span class="path-label">Path:</span>
        <span class="path-value">{photo.file_path}</span>
    </div>
{/if}

<!-- Browser storage info -->
{#if BROWSER && $photoStats}
    <div class="storage-info">
        {formatStorageInfo($photoStats)}
    </div>
{/if}

<!-- Retry button works for both -->
{#if BROWSER}
    <button on:click={() => uploadManager.retryFailed()}>
        Retry Upload
    </button>
{:else}
    <RetryUploadsButton {photo} />
{/if}
```

## Total Complexity Added

- **~65 lines of actual code changes**
- **5 conditional blocks** in template
- **1 new adapter file** (photoStatsAdapter.ts) that centralizes platform differences
- **No breaking changes** to existing Tauri functionality

## Benefits

1. **Same UI/UX** - Users get consistent experience
2. **Shared stats logic** - Both platforms show upload progress
3. **Minimal conditionals** - Most logic abstracted to adapters
4. **Progressive enhancement** - Browser gets storage info, device gets file paths
5. **Single source of truth** - One page to maintain

## Testing Strategy

```typescript
// Simple platform mock for testing
function mockPlatform(isBrowser: boolean) {
    globalThis.BROWSER = isBrowser;
    globalThis.TAURI = !isBrowser;
}

// Test both environments
describe('PhotosPage', () => {
    it('works in browser mode', () => {
        mockPlatform(true);
        // test browser features
    });

    it('works in tauri mode', () => {
        mockPlatform(false);
        // test device features
    });
});
```

## Migration Path

1. **Phase 1**: Create photoStatsAdapter.ts ✅
2. **Phase 2**: Update DevicePhotoStats to use adapter (5 min)
3. **Phase 3**: Add browser data fetching to page (10 min)
4. **Phase 4**: Add conditional UI elements (10 min)
5. **Phase 5**: Test both platforms (15 min)

**Total time: ~40 minutes** to have unified page working for both platforms.
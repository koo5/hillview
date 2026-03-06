# Browser-Based Photo Capture System

## Overview

The browser-based photo capture system allows users to take geotagged photos directly from their web browser using WebRTC and store them in IndexedDB for background uploads. This provides a native app-like experience for photo capture without requiring app installation.

## Architecture Components

### 1. Camera Capture (`CameraCapture.svelte`)
- Uses WebRTC `getUserMedia()` API to access device camera
- Renders live camera feed to a `<video>` element
- Captures frames to `<canvas>` for photo extraction
- Handles both front and rear cameras
- Supports orientation detection for proper EXIF values

### 2. Photo Storage (`browserPhotoStorage.ts`)
- **IndexedDB Storage**: Persistent local storage for photos
- **Database Schema**:
  ```typescript
  interface StoredPhoto {
    id: string;
    blob: Blob;  // JPEG image data
    metadata: {
      location: CaptureLocation;
      captured_at: number;
      orientation_code: number; // EXIF orientation (1, 3, 6, 8)
      mode: 'slow' | 'fast';
    };
    status: 'pending' | 'uploading' | 'uploaded' | 'failed';
    retryCount: number;
    addedAt: number;
    priority: number; // 0 for fast mode, 1 for slow
    retryAfter?: number; // For exponential backoff
    serverPhotoId?: string;
  }
  ```
- **No separate queue table** - follows Kotlin pattern with status field
- **Automatic migration** from v1 to v2 schema

### 3. Upload System

#### Secure Upload Flow (`secureUpload.ts`)
1. **Authorization Request** to `/photos/authorize-upload`
   - Includes client public key for signature verification
   - Returns upload JWT and worker URL
2. **Worker Upload** with JWT, client signature, and metadata
   - Client signs upload data with ECDSA key
   - Worker URL obtained from authorization response
3. **Metadata as Parameters** - Since browsers can't write EXIF tags:
   ```typescript
   formData.append('metadata', JSON.stringify({
     latitude, longitude, altitude, bearing,
     captured_at, orientation_code,
     location_source, bearing_source, accuracy
   }));
   ```

#### Service Worker Background Sync
- **Bundle**: Built with Vite into `/static/serviceWorkerBundle.js`
- **Version System**: Auto-generated from content hash (e.g., `2026-02-16-4995ace7`)
- **Background Sync API**: Automatic retry when offline/background
- **Browser Support**:
  - ✅ Full: Chrome, Edge, Opera, Samsung Internet
  - ❌ Limited: Safari, Firefox (uploads only while app open)

#### Token Management (`sharedTokenRefresh.ts`)
- **IndexedDB-based locking** to prevent race conditions
- **60-second timeout** for lock acquisition
- **Shared between** main thread and service worker
- **Automatic refresh** before expiry

### 4. Capture Queue (`captureQueue.ts`)
- **Memory buffer** for rapid capture
- **ImageData storage** before JPEG conversion
- **Processing pipeline**:
  1. Capture to ImageData
  2. Apply rotation if needed
  3. Convert to JPEG Blob
  4. Save to IndexedDB
  5. Trigger background upload

### 5. Location & Bearing
- **GPS from**: Browser Geolocation API or map selection
- **Bearing from**: Device orientation API or manual input
- **Accuracy tracking** for both sources
- **Fallback options** when sensors unavailable

### 6. Client Key Management (`clientCrypto.ts`)
- **ECDSA P-256 key pairs** for upload signing
- **Dual storage support**:
  - localStorage for main thread (browser context)
  - IndexedDB for service workers (background uploads)
  - Automatic mirroring between storage backends
- **Key persistence** across sessions
- **Signature generation** for upload authorization

## Key Features

### Offline Capability
- Photos stored locally in IndexedDB
- Background sync when connection restored
- Exponential backoff for failed uploads
- Persistent storage request to prevent data loss

### Performance Optimizations
- Fast/slow capture modes
- Priority-based upload queue
- Blob cleanup after successful upload (when >50% storage used)
- OffscreenCanvas for image processing (when available)

### Security
- JWT-based upload authorization
- ECDSA client signature validation
- Cryptographic proof of upload intent
- MD5 duplicate detection
- Sanitized filenames
- Worker URL from authorization response (not hardcoded)

## Browser Compatibility

### Required APIs
- WebRTC (getUserMedia)
- IndexedDB
- Service Workers
- Fetch API

### Optional APIs
- Background Sync (for offline upload)
- OffscreenCanvas (performance)
- Persistent Storage (data protection)

## Configuration

### Backend URLs
- Configured in `$lib/config.ts`
- Service worker uses same configuration
- Automatic worker URL resolution

### Build Process
```bash
# Build service worker bundle
bun run build:sw

# Full build (includes SW)
bun run build
```

### Version Management
- Service worker version in build config
- Based on source file content hash
- Visible in browser console logs
- Automatic update via `skipWaiting()`

## Limitations & Considerations

### Browser Limitations
1. **Cannot write EXIF tags** - metadata sent as form parameters
2. **Background sync** not supported on iOS Safari
3. **Storage quotas** vary by browser
4. **Camera access** requires HTTPS (except localhost)

### Performance Considerations
- IndexedDB operations are async but can be slow with large blobs
- Service worker updates require page reload
- Memory usage with multiple ImageData objects

### Security Considerations
- Camera permissions are per-origin
- IndexedDB data is not encrypted
- Service workers require secure contexts

## Development & Debugging

### Console Logs
Look for these prefixes:
- `🢄[BrowserPhotoStorage]` - Storage operations
- `🢄[CaptureQueue]` - Capture pipeline
- `🢄[ServiceWorkerUpload]` - Background uploads
- `[ServiceWorkerBundle]` - Bundle version
- `[NetworkWorker]` - Service worker lifecycle

### Chrome DevTools
1. **Application tab** → IndexedDB → HillviewPhotoDB
2. **Application tab** → Service Workers → network-worker.js
3. **Network tab** → Filter by "upload" for upload requests

### Common Issues

#### "No EXIF data found"
- Browser captures don't have EXIF
- Metadata passed as parameters
- Check worker endpoint accepts metadata

#### Background sync not working
- Check browser support
- Verify service worker registered
- Check Background Sync in DevTools

#### Storage quota exceeded
- Clear old uploaded photos
- Request persistent storage
- Check storage estimate in DevTools

## Testing

### Manual Testing
1. Open browser console
2. Navigate to photo capture page
3. Allow camera permissions
4. Take photo
5. Check IndexedDB for stored photo
6. Check network tab for upload
7. Verify photo in backend

### Automated Testing
- Playwright tests for UI interaction
- Service worker tests via Chrome DevTools Protocol
- IndexedDB mocking for unit tests

## Future Improvements

1. **WebCodecs API** for better compression
2. **Workbox** for service worker management
3. **WebAssembly** for image processing
4. **Push notifications** for upload status
5. **Batch uploads** for efficiency
6. **Progressive JPEG** for preview generation
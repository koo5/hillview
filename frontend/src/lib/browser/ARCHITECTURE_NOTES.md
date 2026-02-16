# Browser Photo Upload Architecture Notes

## Current Implementation

### Token Management
- **SharedTokenRefresh**: Handles token refresh with IndexedDB-based locking
- **Lock mechanism**: 60-second timeout to prevent deadlocks
- **Storage**: Tokens stored in both localStorage and IndexedDB

### Backend Token Semantics (from API server)
- **Access Token**: Short-lived (30 minutes default), JWT with user ID and username
- **Refresh Token**: Long-lived (7 days default), JWT used to get new access tokens
- **Token Rotation**: Each refresh creates NEW tokens (both access AND refresh)
- **Multiple Active Tokens**: YES - tokens are stateless JWTs, not tracked in database
- **Refresh Token Reuse**: NO - old refresh token remains valid until expiry, but best practice is to use the new one
- **Concurrent Refreshes**: Would work (both get new token pairs) but wasteful

### Service Worker
- **network-worker.js**: Handles both tile loading and photo uploads
- **serviceWorkerBundle.js**: Bundled TypeScript modules for service worker use
- **Background Sync API**: Triggered when photos are saved for upload

## Potential Improvements

### 2. Token Refresh Locking Mechanism
**Current Implementation**: 60-second lock timeout with IndexedDB-based mutex

**What it does**:
- Prevents multiple contexts (main thread, service worker) from sending concurrent refresh requests
- If lock holder crashes/hangs, other contexts wait up to 60s before taking over

**Trade-offs**:
- ✅ Prevents duplicate refresh requests that might fail if backend invalidates refresh tokens on first use
- ❌ Can cause 60+ second delays if lock holder crashes
- ❌ Adds complexity for an edge case

**Alternative approaches to consider**:
1. **No locking**: Let both contexts try independently, handle failures gracefully
2. **Shorter timeout**: 5-10 seconds might be enough for HTTP requests
3. **Backend solution**: Configure auth service to accept duplicate refresh attempts within time window

**Current decision**: Keep 60s timeout for now, but this may be overengineered.

### 3. Single Source of Truth for Tokens
**Problem**: Tokens stored in multiple places can get out of sync.

**Solution**: Use IndexedDB as the single source of truth:
- Remove localStorage usage for tokens
- Update webTokenManager to only use IndexedDB via authStorage
- This ensures main thread and service worker always see same data

### 4. Retry Queue Management
**Problem**: Photos that fail 3 times are abandoned.

**Solution**: Implement exponential backoff with persistent retry state:
```typescript
interface PhotoRetryState {
    photoId: string;
    attempts: number;
    nextRetryTime: number;  // Timestamp for next retry
    lastError?: string;
}

// Exponential backoff: 1min, 5min, 15min, 1hr, 6hr, 24hr
const RETRY_DELAYS = [60, 300, 900, 3600, 21600, 86400];

function getNextRetryTime(attempts: number): number {
    const delaySeconds = RETRY_DELAYS[Math.min(attempts, RETRY_DELAYS.length - 1)];
    return Date.now() + (delaySeconds * 1000);
}
```
Also, we should switch to the async upload endpoint.


### 5. Service Worker Update Strategy
**Problem**: Service worker bundle is static and requires rebuild for updates.

**Solution**:
- Consider using Workbox for better service worker management
- Implement versioning and update notifications
- Add ability to force service worker update from UI

### 6. Monitoring and Diagnostics
**Problem**: Hard to debug service worker issues in production.

**Solution**: Add telemetry:
```typescript
interface UploadMetrics {
    totalUploads: number;
    successfulUploads: number;
    failedUploads: number;
    averageUploadTime: number;
    lastSyncTime: number;
    tokenRefreshCount: number;
}

// Store metrics in IndexedDB and expose via UI
```

### 7. Graceful Degradation
**Problem**: Background Sync API not supported on all browsers (e.g., iOS Safari).

**Current Detection**: Already checking `'sync' in ServiceWorkerRegistration.prototype`

**Solution**: Fallback to main thread uploads:
- If Background Sync not supported → immediate upload from main thread
- If service worker crashes → periodic retry from main thread
- Could show user notification about limited offline capability

## Implementation Priority

1. **High Priority**: Single source of truth for tokens (prevents auth issues)
2. **High Priority**: Unified backend URL management (prevents connection failures)
3. **Medium Priority**: Better retry queue with exponential backoff
4. **Low Priority**: Monitoring/diagnostics
5. **Low Priority**: Service worker update strategy

## Testing Considerations

- Test with slow/intermittent connections
- Test token refresh race conditions
- Test service worker updates
- Test fallback scenarios
- Test with large photo batches

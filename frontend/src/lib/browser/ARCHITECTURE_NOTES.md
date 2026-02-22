# Browser Photo Upload Architecture Notes

## Current Implementation

### Token Management
- **authStorage.ts**: Single source of truth in IndexedDB (HillviewAuthDB)
- **webTokenManager.ts**: Main thread token management with local cache
- **Cross-tab reactivity**: BroadcastChannel notifies other tabs on auth changes
- **Optimistic refresh**: No locking - if refresh fails with 401/403, checks if another context refreshed

### Token Data Flow
1. Login/refresh → authStorage.saveTokenData() → IndexedDB → BroadcastChannel → other tabs refresh cache
2. Token access → webTokenManager checks local cache (fast) → refreshes from IndexedDB if stale
3. Service worker → authStorage.getValidToken() → IndexedDB directly (no cache)

### Backend Token Semantics (from API server)
- **Access Token**: Short-lived (30 minutes default), JWT with user ID and username
- **Refresh Token**: Long-lived (7 days default), JWT used to get new access tokens
- **Token Rotation**: Each refresh creates NEW tokens (both access AND refresh)
- **Multiple Active Tokens**: YES - tokens are stateless JWTs, not tracked in database
- **Concurrent Refreshes**: Both get new token pairs - wasteful but works

### Service Worker
- **serviceWorkerSecureUpload.ts**: Uses authStorage.getValidToken() directly
- **serviceWorkerBundle.js**: Bundled TypeScript modules for service worker use
- **Background Sync API**: Triggered when photos are saved for upload

## Potential Improvements

### Retry Queue Management
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
```

### Service Worker Update Strategy
**Problem**: Service worker bundle is static and requires rebuild for updates.

**Solution**:
- Consider using Workbox for better service worker management
- Implement versioning and update notifications
- Add ability to force service worker update from UI

### Monitoring and Diagnostics
**Problem**: Hard to debug service worker issues in production.

**Solution**: Add telemetry stored in IndexedDB and exposed via UI.

### Graceful Degradation
**Problem**: Background Sync API not supported on all browsers (e.g., iOS Safari).

**Current Detection**: Already checking `'sync' in ServiceWorkerRegistration.prototype`

**Solution**: Fallback to main thread uploads when Background Sync not supported.

## Testing Considerations

- Test with slow/intermittent connections
- Test token refresh race conditions (concurrent tabs/service worker)
- Test service worker updates
- Test fallback scenarios
- Test with large photo batches

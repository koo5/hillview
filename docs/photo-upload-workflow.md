# Photo Upload Workflow

This document describes the complete photo upload process in Hillview, covering all components, states, transitions, error handling, and known edge cases.

## System Overview

The photo upload system involves three components:

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Android Client │ ──── │   API Server    │ ──── │  Worker Service │
│    (Kotlin)     │      │   (FastAPI)     │      │   (FastAPI)     │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

**Key Design Principles:**
- **Three-phase secure upload**: Authorization → File Transfer → Processing Result
- **Cryptographic verification**: Client signs uploads, worker signs results
- **Duplicate detection**: MD5 hash checked before upload starts
- **Soft deletes**: Photos are marked deleted, not removed from database

---

## Photo States

### Client-Side States (PhotoEntity.uploadStatus)

| State | Description |
|-------|-------------|
| `pending` | Photo discovered, queued for upload |
| `uploading` | Authorization obtained, file being sent to worker |
| `processing` | File uploaded, waiting for worker to finish |
| `completed` | Successfully processed and stored on server |
| `failed` | Upload or processing failed (will retry with backoff) |

**Additional Client Fields:**
- `serverPhotoId`: Server's UUID (set after authorization)
- `retryCount`: Number of failed attempts
- `lastUploadAttempt`: Timestamp for backoff calculation
- `uploadError`: Human-readable error message
- `fileHash`: MD5 for duplicate detection
- `deleted`: Soft delete flag synced from server

### Server-Side States (Photo.processing_status)

| State | Description |
|-------|-------------|
| `authorized` | Upload authorized, waiting for worker to process |
| `completed` | Successfully processed by worker |
| `error` | Processing failed permanently |

**Additional Server Fields:**
- `deleted`: Soft delete flag (files removed, row kept)
- `processed_by_worker`: Worker identity for audit trail
- `client_signature`: ECDSA signature from client
- `upload_authorized_at`: Unix timestamp for signature verification

---

## Complete Upload Flow

### Phase 1: Photo Discovery (Client)

```
Device Storage ──scan──> PhotoEntity (status=pending)
```

1. Client scans `/storage/emulated/0/Pictures/Hillview/`
2. For each new photo:
   - Calculate MD5 hash
   - Extract GPS coordinates from EXIF (if available)
   - Create PhotoEntity with `status=pending`
   - Skip if duplicate path or hash exists locally

### Phase 2: Request Authorization (Client → API)

```
POST /api/photos/authorize-upload
```

**Request:**
```json
{
  "filename": "IMG_20240115_123456.jpg",
  "file_size": 4500000,
  "content_type": "image/jpeg",
  "file_md5": "a1b2c3d4e5f6...",
  "client_key_id": "key_abc123",
  "latitude": 50.0755,
  "longitude": 14.4378,
  "altitude": 250.0,
  "bearing": 45.0,
  "captured_at": "2024-01-15T12:34:56Z"
}
```

**Response (success):**
```json
{
  "upload_jwt": "eyJhbG...",
  "photo_id": "550e8400-e29b-41d4-a716-446655440000",
  "worker_url": "https://worker.example.com",
  "expires_at": "2024-01-15T13:34:56Z",
  "upload_authorized_at": 1705322096
}
```

**Response (duplicate):**
```json
{
  "duplicate": true,
  "message": "File already exists"
}
```

**State Transitions:**
- Success: `pending` → `uploading`, store `serverPhotoId`
- Duplicate: `pending` → `completed` (no upload needed)
- Failure: `pending` → `failed` (with retry)

### Phase 3: Upload to Worker (Client → Worker)

```
POST {worker_url}/upload_async
Authorization: Bearer {upload_jwt}
Content-Type: multipart/form-data

- file: (binary)
- client_signature: (base64 ECDSA signature)
```

**Client Signature Creation:**
```
message = filename + photo_id + upload_authorized_at
signature = ECDSA_sign(client_private_key, SHA256(message))
```

**Heartbeat Mechanism:**
- Every 30 seconds, client updates `lastUploadAttempt`
- Prevents upload from being considered stale during long transfers

**State Transitions:**
- Success (HTTP 200): `uploading` → `processing`
- Failure: `uploading` → `failed` (with retry)

### Phase 4: Photo Processing (Worker)

```
Worker receives file → Validate → Process → Notify API
```

**Processing Steps:**

1. **Save File**: Validate content type, sanitize filename, save to disk
2. **Extract EXIF**: Using exiftool, extract:
   - GPS coordinates (required)
   - Compass bearing (required) - from GPSImgDirection, GPSTrack, or GPSDestBearing
   - Altitude (optional)
   - Capture timestamp (optional)
3. **Validate**: Ensure GPS and bearing exist and are valid
4. **Anonymize**: Blur detected faces and license plates
5. **Create Variants**: Generate WebP versions at 320, 640, 1024, 2048, 3072, 4096px
6. **Upload Variants**: To CDN or API server storage
7. **Notify API**: Send processing results

**Processing Errors:**

| Error | Retry? | Message |
|-------|--------|---------|
| No EXIF data | No | "No EXIF data found" |
| No GPS coordinates | No | "No GPS data found" |
| Missing compass bearing | No | "Compass direction missing" |
| Invalid bearing | No | "Invalid bearing (must be 0-360)" |
| Insufficient RAM | Yes (15 min) | "Insufficient resources" |
| System I/O error | Yes (5 min) | "System error: {details}" |
| Unexpected error | Yes (10 min) | "Unexpected error: {details}" |

### Phase 5: Processing Result (Worker → API)

```
POST /api/photos/processed
```

**Request:**
```json
{
  "processed_data": {
    "photo_id": "550e8400-...",
    "processing_status": "completed",
    "width": 4032,
    "height": 3024,
    "latitude": 50.0755,
    "longitude": 14.4378,
    "compass_angle": 45.0,
    "altitude": 250.0,
    "exif_data": {...},
    "sizes": {
      "full": {"url": "...", "width": 4032, "height": 3024},
      "320": {"url": "...", "width": 320, "height": 240}
    },
    "detected_objects": {...},
    "client_signature": "base64...",
    "processed_by_worker": "worker-abc_20240115_x9k2m",
    "filename": "IMG_20240115_123456.jpg",
    "captured_at": "2024-01-15T12:34:56Z"
  },
  "worker_signature": "eyJhbG..."
}
```

**Server Verification:**
1. Validate worker signature (JWT)
2. Load client's public key from DB
3. Verify client signature matches expected message
4. Update Photo record with processing results

**Response Codes:**
- `200`: Success, photo updated
- `404`: Photo not found (programming error)
- `410`: Photo was deleted (expected, clean exit)
- `401`: Invalid signatures

### Phase 6: Status Sync (Client → API)

```
POST /api/photos/status
```

**Request:**
```json
{
  "photo_ids": ["550e8400-...", "661f9511-..."]
}
```

**Response:**
```json
{
  "photos": [
    {
      "id": "550e8400-...",
      "processing_status": "completed",
      "error": null,
      "deleted": false
    }
  ]
}
```

**Client Updates:**
- `completed` → local status = `completed`
- `error` → local status = `failed`, increment retryCount
- `deleted=true` → set local `deleted=true`
- `authorized` → keep polling (still processing)

---

## Retry & Recovery Mechanisms

### Exponential Backoff (Client)

Failed uploads retry with increasing delays:

| Attempt | Delay |
|---------|-------|
| 1 | 1 minute |
| 2 | 2 minutes |
| 3 | 4 minutes |
| 4 | 8 minutes |
| 5 | 16 minutes |
| 6 | 32 minutes |
| 7 | 1 hour |
| 8 | 2 hours |
| 9 | 4 hours |
| 10 | 8 hours |
| 11 | 16 hours |
| 12 | ~1.3 days |
| 13 | ~2.6 days |
| 14 | ~5.2 days |
| 15+ | 7 days (max) |

**Bypass:** Manual "retry" button ignores backoff timer.

### Stale Upload Detection (Client)

Query for next upload considers uploads "stale" if:
- Status is `uploading` AND `lastUploadAttempt < uploadingStaleThreshold` (10 minutes)
- Status is `processing` AND `lastUploadAttempt < processingStaleThreshold` (1 hour)

Both thresholds are calculated as `System.currentTimeMillis() - duration` at query time.

Stale uploads are re-queued for retry. For `processing` photos, the server's duplicate handling automatically cleans up the old `authorized` record when re-authorization is requested.

### Worker Keepalive (Worker → API)

Background thread pings API every second when tasks are pending:
```
POST /api/worker_pending_background_tasks_ping
{
  "worker_identity": "worker-abc_20240115_x9k2m",
  "fly_machine_id": "abc123",
  "pending_tasks": 3,
  "task0_id": 1
}
```

---

## State Diagram

```
                                    ┌─────────────────────────────────────┐
                                    │           CLIENT STATES             │
                                    └─────────────────────────────────────┘

     ┌──────────┐   authorize    ┌───────────┐   upload    ┌────────────┐
     │ pending  │ ─────────────> │ uploading │ ──────────> │ processing │
     └──────────┘                └───────────┘             └────────────┘
          │                           │                          │
          │ duplicate                 │ error                    │ poll /status
          │                           │                          │
          │                           v                          v
          │                      ┌────────┐              ┌───────────┐
          └───────────────────>  │ failed │ <─────────── │ completed │
                                 └────────┘              └───────────┘
                                      │                        ^
                                      │ retry (backoff)        │
                                      └────────────────────────┘

                                    ┌─────────────────────────────────────┐
                                    │           SERVER STATES             │
                                    └─────────────────────────────────────┘

                              ┌────────────┐
                              │ authorized │
                              └────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │ worker success│               │ worker error
                    v               │               v
             ┌───────────┐          │         ┌─────────┐
             │ completed │          │         │  error  │
             └───────────┘          │         └─────────┘
                                    │
                                    v
                              ┌───────────┐
                              │  deleted  │ (soft delete, any state)
                              └───────────┘
```

---

## Edge Cases & Potential Issues

### 1. Stuck in "uploading"

**Cause:** Client crashes mid-upload, or network fails after sending file but before receiving response.

**Current Recovery:** Stale upload detection re-queues after timeout.

**Safeguards:**
- HTTP client timeouts (100s connect, 300s read/write) ensure requests can't block forever
- Heartbeat is cancelled in `finally` block on all exit paths
- Maximum heartbeat duration: ~8-9 minutes before timeout
- If app is killed, heartbeat stops immediately and `lastUploadAttempt` becomes stale

### 2. Stuck in "processing"

**Cause:** Worker crashes after receiving file but before calling `/photos/processed`.

**Recovery:** Stale detection + server-side cleanup handles this automatically:
1. After 1 hour, `getNextPhotoForUpload` returns the stale photo
2. Client calls `authorize-upload` with same MD5 hash
3. Server sees existing `authorized` photo → deletes old record → creates fresh authorization
4. Client uploads to worker again
5. Photo gets processed normally

**Safeguards:**
- `processingStaleThreshold` set to 1 hour in `getNextPhotoForUpload` query
- Server's duplicate handling cleans up stale `authorized` records automatically
- No manual intervention required

### 3. Signature Verification Failure

**Note:** This scenario is not currently possible. Keys are created with `is_active=True` and there's no mechanism to deactivate or rotate them. The `is_active` check in signature verification is defensive coding for potential future key management features.

**If key management is added in the future:**
- Recovery would work via stale detection - after 1 hour, re-upload with fresh authorization using current active key
- The server's duplicate handling would clean up the old `authorized` record

### 4. Duplicate Race Condition

**Cause:** Two devices upload same photo simultaneously.

**Behavior:**
- First: Gets `photo_id`, proceeds normally
- Second: Gets `duplicate=true`, transitions to `completed` immediately

**Risk:** Second client has no `serverPhotoId` stored. Status sync won't include this photo.

### 5. Photo Deleted During Processing

**Cause:** User deletes photo on server while worker is processing.

**Handling:**
- Worker receives `410 Gone` when calling `/photos/processed` or `/photos/upload-file`
- Worker raises `PhotoDeletedException`, returns success with "deleted" message
- Client receives `deleted=true` in status sync, sets local `deleted=true`

**Current Behavior:** Clean handling, no stuck states.

### 6. Maximum Retry Exhaustion

**Cause:** Photo fails consistently for 7+ days.

**Result:** Photo stuck in `failed` state with max backoff (7 days between retries).

**Gap:** No automatic cleanup or user notification for permanently failed uploads.

### 7. Full State Sync Missing

**Current Limitation:** Client only syncs status for photos in `processing` state.

**Missing Capabilities:**
- Discover photos deleted on server while client was offline
- Reconcile photos that exist on server but not in local DB
- Handle photos uploaded from different device

**Workaround:** None. A local rescan only discovers new files on the device filesystem - it doesn't fetch state from the server. Full reconciliation would require a new `/api/photos/sync` endpoint that returns all of the user's photos with their states.

---

## Security Considerations

### Client Signature Purpose

The client signature proves that:
1. The upload was initiated by the registered client device
2. The specific file was authorized for the specific photo_id
3. The authorization happened at the claimed timestamp

This prevents:
- Compromised workers from uploading arbitrary files
- Replay attacks reusing old authorization tokens
- File substitution attacks

### Worker Signature Purpose

The worker signature proves that:
1. Processing results came from a trusted worker
2. The results weren't tampered with in transit

### Audit Trail

Each processed photo stores:
- `client_signature`: Proof of client authorization
- `client_public_key_id`: Which device authorized it
- `processed_by_worker`: Which worker processed it
- `upload_authorized_at`: When authorization was granted
- `processed_at`: When processing completed

---

## API Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/photos/authorize-upload` | POST | Request upload authorization |
| `/api/photos/status` | POST | Batch check processing status |
| `/api/photos/upload-file` | POST | Worker uploads file variants |
| `/api/photos/processed` | POST | Worker reports processing results |
| `/api/photos/{id}` | DELETE | Soft delete a photo |
| `{worker}/upload` | POST | Sync file upload to worker |
| `{worker}/upload_async` | POST | Async file upload to worker |

---

## Configuration

### Environment Variables

**API Server:**
- `WORKER_URL`: Default worker URL for assignment
- `UPLOAD_DIR`: Where to store uploaded files

**Worker:**
- `API_URL`: API server URL for callbacks
- `PARALLEL_PROCESSING_CONCURRENCY`: Max concurrent processing tasks (default: 3)
- `KEEP_PICS_IN_WORKER`: If true, keep files on worker (for development)
- `USE_CDN`: If true, upload variants to S3-compatible CDN

**Client:**
- `auto_upload_enabled`: User preference to enable/disable auto-upload

---

## Future Improvements

1. **Full State Sync**: Implement complete photo list sync from server to client
2. **Failed Upload Cleanup**: Notify users of permanently failed uploads
3. **Upload Resume**: Support resumable uploads for large files on poor connections
4. **Multi-Device Sync**: Sync photos across devices logged into same account

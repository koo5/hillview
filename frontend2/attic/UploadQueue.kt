package cz.hillview.upload

import cz.hillview.auth.NotLoggedInException
import cz.hillview.auth.SessionExpiredException
import cz.hillview.auth.TransientBackendException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.Serializable

enum class UploadState { Pending, Done, Duplicate, FailedPermanent }

@Serializable
data class PendingUpload(
    val id: String,
    val filePath: String,
    val filename: String,
    val fileMd5: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val altitude: Double? = null,
    val bearing: Double? = null,
    val capturedAtIso: String? = null,
    val state: UploadState = UploadState.Pending,
    val attempts: Int = 0,
    val lastError: String? = null,
    val photoId: String? = null,
)

/** Durable queue storage; platform-backed, in-memory in tests. */
interface QueueStore {
    suspend fun load(): List<PendingUpload>
    suspend fun save(entries: List<PendingUpload>)
}

class InMemoryQueueStore(initial: List<PendingUpload> = emptyList()) : QueueStore {
    private var entries = initial
    override suspend fun load(): List<PendingUpload> = entries
    override suspend fun save(entries: List<PendingUpload>) { this.entries = entries }
}

data class QueueStats(
    val pending: Int = 0,
    val done: Int = 0,
    val duplicate: Int = 0,
    val failed: Int = 0,
    val draining: Boolean = false,
    val lastError: String? = null,
)

/**
 * Offline-first upload queue: entries survive process death; a drain pass
 * walks Pending entries sequentially. Failure semantics ported from the old
 * app's chaos/coalescing specs:
 *
 *  - retryable trouble (5xx/network) counts the attempt, keeps the entry
 *    Pending, and moves on — the next drain retries it;
 *  - permanent rejection (4xx) parks the entry as FailedPermanent;
 *  - a saturated worker (WorkerBusy) aborts the whole pass — retrying
 *    photo-by-photo just transmits bodies at a queue that rejects them;
 *  - session loss (not logged in / expired) aborts the pass with entries
 *    intact — auto-upload-on-login re-drains;
 *  - md5 dedup answers from authorize mark Duplicate (a success for sync).
 *
 * Orchestration (WorkManager windows, wifi-only, foreground promotion) sits
 * ABOVE this class on Android and is not ported yet.
 */
class UploadQueue(
    private val store: QueueStore,
    private val api: PhotoUploadApi,
    private val signer: UploadSigner,
    private val readFile: (String) -> ByteArray,
    // Backend vocabulary (user_routes.ALLOWED_LICENSES): 'ccbysa4+osm' | 'full1'.
    private val license: String? = "ccbysa4+osm",
) {
    private val _stats = MutableStateFlow(QueueStats())
    val stats: StateFlow<QueueStats> = _stats.asStateFlow()

    private val drainMutex = Mutex()
    private var keyRegistered = false

    suspend fun enqueue(upload: PendingUpload) {
        val entries = store.load() + upload
        store.save(entries)
        publishStats(entries)
    }

    suspend fun entries(): List<PendingUpload> = store.load()

    /** One sequential pass over Pending entries. Safe to call repeatedly. */
    suspend fun drain() {
        drainMutex.withLock {
            var entries = store.load()
            publishStats(entries, draining = true)
            var lastError: String? = null
            try {
                if (!keyRegistered) {
                    api.registerClientKey(signer)
                    keyRegistered = true
                }
                for (entry in entries.filter { it.state == UploadState.Pending }) {
                    try {
                        val updated = uploadOne(entry)
                        entries = entries.replace(updated)
                        store.save(entries)
                    } catch (e: WorkerBusyException) {
                        lastError = e.message
                        entries = entries.replace(
                            entry.copy(attempts = entry.attempts + 1, lastError = e.message)
                        )
                        store.save(entries)
                        break // abort the pass
                    } catch (e: UploadRetryableException) {
                        lastError = e.message
                        entries = entries.replace(
                            entry.copy(attempts = entry.attempts + 1, lastError = e.message)
                        )
                        store.save(entries)
                    } catch (e: UploadPermanentException) {
                        lastError = e.message
                        entries = entries.replace(
                            entry.copy(
                                state = UploadState.FailedPermanent,
                                attempts = entry.attempts + 1,
                                lastError = e.message,
                            )
                        )
                        store.save(entries)
                    }
                }
            } catch (e: NotLoggedInException) {
                lastError = "not logged in"
            } catch (e: SessionExpiredException) {
                lastError = "session expired"
            } catch (e: TransientBackendException) {
                lastError = e.message
            } catch (e: UploadRetryableException) {
                lastError = e.message
            } finally {
                publishStats(store.load(), draining = false, lastError = lastError)
            }
        }
    }

    private suspend fun uploadOne(entry: PendingUpload): PendingUpload {
        val bytes = try {
            readFile(entry.filePath)
        } catch (e: Exception) {
            throw UploadPermanentException("file unreadable: ${e.message}")
        }
        val md5 = entry.fileMd5 ?: md5Hex(bytes)

        val auth = api.authorize(
            UploadAuthorizationRequest(
                filename = entry.filename,
                fileSize = bytes.size.toLong(),
                contentType = "image/jpeg",
                fileMd5 = md5,
                clientKeyId = signer.keyId,
                license = license,
                latitude = entry.latitude,
                longitude = entry.longitude,
                altitude = entry.altitude,
                bearing = entry.bearing,
                capturedAt = entry.capturedAtIso,
            )
        )

        if (auth.duplicate) {
            return entry.copy(
                state = UploadState.Duplicate,
                fileMd5 = md5,
                photoId = auth.existingPhotoId,
                lastError = null,
            )
        }
        val jwt = auth.uploadJwt
            ?: throw UploadRetryableException("authorize response missing upload_jwt")
        val photoId = auth.photoId
            ?: throw UploadRetryableException("authorize response missing photo_id")
        val workerUrl = auth.workerUrl
            ?: throw UploadRetryableException("authorize response missing worker_url")
        val authorizedAt = auth.uploadAuthorizedAt
            ?: throw UploadRetryableException("authorize response missing upload_authorized_at")

        val signature = signer.signUpload(entry.filename, photoId, authorizedAt)
        api.uploadToWorker(workerUrl, jwt, entry.filename, bytes, signature)

        return entry.copy(
            state = UploadState.Done,
            fileMd5 = md5,
            photoId = photoId,
            lastError = null,
        )
    }

    private fun List<PendingUpload>.replace(updated: PendingUpload): List<PendingUpload> =
        map { if (it.id == updated.id) updated else it }

    private fun publishStats(
        entries: List<PendingUpload>,
        draining: Boolean = false,
        lastError: String? = null,
    ) {
        _stats.value = QueueStats(
            pending = entries.count { it.state == UploadState.Pending },
            done = entries.count { it.state == UploadState.Done },
            duplicate = entries.count { it.state == UploadState.Duplicate },
            failed = entries.count { it.state == UploadState.FailedPermanent },
            draining = draining,
            lastError = lastError,
        )
    }
}

/** MD5 hex of the file bytes — cross-platform dedup key (matches old clients). */
expect fun md5Hex(bytes: ByteArray): String

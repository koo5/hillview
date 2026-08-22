package cz.hillview.upload

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Protocol DTOs — see docs/frontend2-rewrite-plan.md (P2) and the old app's
// uploadProtocol.ts / ClientCryptoManager.kt, which this ports.

@Serializable
data class UploadAuthorizationRequest(
    val filename: String,
    @SerialName("file_size") val fileSize: Long,
    @SerialName("content_type") val contentType: String,
    @SerialName("file_md5") val fileMd5: String,
    @SerialName("client_key_id") val clientKeyId: String,
    @SerialName("is_public") val isPublic: Boolean = true,
    val license: String? = null,
    val description: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val altitude: Double? = null,
    val bearing: Double? = null,
    @SerialName("captured_at") val capturedAt: String? = null,
)

@Serializable
data class UploadAuthorizationResponse(
    @SerialName("upload_jwt") val uploadJwt: String? = null,
    @SerialName("photo_id") val photoId: String? = null,
    @SerialName("worker_url") val workerUrl: String? = null,
    @SerialName("upload_authorized_at") val uploadAuthorizedAt: Long? = null,
    // DuplicateFileResponse arrives on the same endpoint.
    val duplicate: Boolean = false,
    @SerialName("existing_photo_id") val existingPhotoId: String? = null,
    val message: String? = null,
)

@Serializable
data class ClientPublicKeyData(
    @SerialName("public_key_pem") val publicKeyPem: String,
    @SerialName("key_id") val keyId: String,
    @SerialName("created_at") val createdAt: String,
)

/** Client/user problem — do not retry (4xx, duplicates surface separately). */
class UploadPermanentException(message: String) : Exception(message)

/** Server/network trouble — retry later with backoff. */
class UploadRetryableException(message: String, cause: Throwable? = null) : Exception(message, cause)

/** The worker fleet is saturated — abort the whole drain pass. */
class WorkerBusyException(message: String) : Exception(message)

/** Signs upload authorizations with the registered client key. */
interface UploadSigner {
    val keyId: String
    val publicKeyPem: String
    val createdAtIso: String

    /** SHA256withECDSA over the exact payload string, base64. */
    fun sign(payload: String): String

    /**
     * Signs the upload authorization. Implementations backed by
     * higher-level signers (shared-kt ClientCryptoManager) override this
     * directly instead of [sign].
     */
    fun signUpload(filename: String, photoId: String, authorizedAt: Long): String =
        sign(uploadSignaturePayload(filename, photoId, authorizedAt))
}

/**
 * The exact bytes the old clients sign: a JSON array of
 * [filename, photo_id, upload_authorized_at] with no whitespace.
 */
fun uploadSignaturePayload(filename: String, photoId: String, authorizedAt: Long): String =
    "[${jsonString(filename)},${jsonString(photoId)},$authorizedAt]"

private fun jsonString(value: String): String =
    "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

// Moved here verbatim from UploadQueue.kt when the commonMain queue was
// retired (2026-08-05) in favor of the shared-kt stack on Android — these
// stayed because they are the UploadPipeline contract (PendingUpload/
// QueueStats) and the cross-platform dedup key (md5Hex).
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
    /** Capture instant from the sensor snapshot — authoritative, unlike a file mtime. */
    val capturedAtMs: Long? = null,
    // Stamp provenance, destined for the photos-table columns (v15) that the
    // upload metadata blob is built from — the fast-write path's only record
    // of these (the file carries no EXIF there).
    val bearingSource: String? = null,
    /** Camera elevation at the shutter, degrees; null when unrecorded. */
    val pitchDeg: Double? = null,
    val locationSource: String? = null,
    val locationAgeMs: Long? = null,
    val exposureJson: String? = null,
    /**
     * The licence in force AT CAPTURE. Snapshotted rather than read at
     * upload time: a licence is a statement about this photo, made when it
     * was taken, so changing the setting later must not relicense a queue.
     */
    val license: String? = null,
    val state: UploadState = UploadState.Pending,
    val attempts: Int = 0,
    val lastError: String? = null,
    val photoId: String? = null,
)

data class QueueStats(
    val pending: Int = 0,
    val done: Int = 0,
    val duplicate: Int = 0,
    val failed: Int = 0,
    val draining: Boolean = false,
    /** Stamp refinements in flight (the corner indicator's ⟳). */
    val refining: Int = 0,
    val lastError: String? = null,
)

/** MD5 hex of the file bytes — cross-platform dedup key (matches old clients). */
expect fun md5Hex(bytes: ByteArray): String

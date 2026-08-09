package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.ColumnInfo
import androidx.room.Index

@Entity(
    tableName = "photos",
    indices = [
        Index(value = ["createdAt"], name = "idx_photos_created_at"),
        Index(value = ["uploadStatus", "createdAt"], name = "idx_photos_upload_status_created_at"),
        Index(value = ["latitude", "longitude"], name = "idx_photos_location"),
        Index(value = ["fileHash"], name = "idx_photos_file_hash"),
        Index(value = ["path"], name = "idx_photos_path")
    ]
)
data class PhotoEntity(
    @PrimaryKey
    val id: String,
    val filename: String,
    val path: String,
    val latitude: Double,
    val longitude: Double,
    val altitude: Double = 0.0,
    val bearing: Double = 0.0,
    val capturedAt: Long,
    val accuracy: Double,
    val width: Int,
    val height: Int,
    val fileSize: Long,
    val createdAt: Long,

    // Upload tracking fields
    val uploadStatus: String = "pending", // pending, uploading, processing, completed, failed
    val uploadedAt: Long = 0L,
    val retryCount: Int = 0,
    val lastUploadAttempt: Long = 0L,
    val uploadError: String = "",
    val fileHash: String = "",
    val serverPhotoId: String? = null,  // Server's photo ID (UUID) for status queries

    // Soft delete flag - synced from server
    val deleted: Boolean = false,

    // Version for re-upload support (e.g., changing anonymization settings)
    // Bumped when user edits photo settings and wants to re-upload
    val version: Int = 1,

    // Anonymization override as JSON string:
    // - null: auto-detect faces/plates and blur them (default)
    // - "[]": skip anonymization entirely
    // - "[{\"x\":10,\"y\":20,\"width\":100,\"height\":50}]": manual blur rectangles
    val anonymizationOverride: String? = null,

    // Stamp provenance (v15). The table is the canonical stamp: the upload
    // sends these in the worker's `metadata` form field, which WINS over
    // whatever EXIF the file carries — so the file needs no EXIF rewrite for
    // a hillview upload to be complete (the fast-write default), and a later
    // table-side refinement of the row uploads refined values with no file
    // rewrite. Null on rows from before v15 or from writers that don't know
    // them; the worker then falls back to the file's EXIF, as it always has.
    val bearingSource: String? = null,
    /** "gps" or "manual" (map-positioned) — same vocabulary as the EXIF provenance. */
    val locationSource: String? = null,
    /** Age of the GPS fix at the shutter, ms. */
    val locationAgeMs: Long? = null,
    /** The exposure-rule story as a JSON object (see exposureProvenanceJson). */
    val exposureJson: String? = null,

    // The refiner's upload gate (v16): the drain skips this row until the
    // deadline passes — set at ingest for refinement-eligible photos, cleared
    // early by the refiner (success or defeat). A timestamp, not a status,
    // so a crash mid-refine cannot strand the row: time alone re-arms it.
    val uploadHoldUntil: Long = 0,

    // When the stamp refiner (v16) replaced the at-the-time values with
    // interpolated ones — location interpolated across the bracketing fixes,
    // compass bearing recomputed as a CENTERED window over the ~10 Hz
    // samples (zero phase lag, unlike the live causal value), car-mode
    // bearing interpolated across the bracketing Kalman rows. Null = never
    // refined: not eligible (manual position), no bracketing data in time,
    // or the upload grabbed the row first — all of which deliberately keep
    // the at-the-time stamp. Rides into the upload metadata as "refined".
    val stampRefinedAt: Long? = null
)

enum class UploadStatus {
    PENDING,
    UPLOADING,
    COMPLETED,
    FAILED
}

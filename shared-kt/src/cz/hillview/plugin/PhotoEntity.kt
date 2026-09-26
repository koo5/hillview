package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.ColumnInfo
import androidx.room.Index

/**
 * [PhotoEntity.uploadHoldReasons] bits — one per enricher that finishes AFTER the
 * row exists. A row is uploadable once none remain set, or once
 * [PhotoEntity.uploadHoldUntil] expires, which is crash recovery only.
 */
/** The stamp refiner is still interpolating this row's position and bearing. */
const val UPLOAD_HOLD_REFINER = 1

/** The deferred IMU window around this exposure has not landed yet. */
const val UPLOAD_HOLD_IMU_WINDOW = 2

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
    /**
     * Nullable (v22) — and null MEANS "this photo records no position": the
     * one case a capture has nothing to stamp, a blank first run before any
     * fix or any pan (docs/one-state.md, "The position side"). Before v22
     * that case could not reach this table at all (the shutter refused the
     * press), and a file imported with no GPS EXIF was written at (0.0, 0.0)
     * — Null Island — which the v22 migration carries across as null. The
     * upload omits an absent position and the server keeps the photo without
     * a geometry; the device-photo loader skips it (nothing to draw); the
     * refiner may later give it one from the tracking tables.
     */
    val latitude: Double?,
    val longitude: Double?,
    /**
     * Metres above the WGS84 ellipsoid — what Android's Location reports (v21).
     *
     * Nullable on purpose, like [pitch] and unlike [bearing], which keeps 0.0
     * as its unset value. It used to be a non-null Double defaulting to 0.0,
     * with "> 0" as the absent test everywhere it was read, and that test is
     * wrong twice over: it collapses a genuine sea-level fix into "unknown",
     * and it throws away every NEGATIVE altitude — which an ellipsoid height
     * legitimately is across whole regions where the geoid sits below the
     * ellipsoid (southern India reaches about -100 m), so a photo taken well
     * above sea level there reported a negative height and lost it. Nothing
     * caught it because in the fast-write path there is no file EXIF for the
     * worker to fall back to: the altitude was simply gone.
     */
    val altitude: Double? = null,
    val bearing: Double = 0.0,
    val capturedAt: Long,
    /**
     * The receiver's horizontal accuracy radius at the stamped fix, metres.
     *
     * Non-null, with **0.0 as the absent sentinel** — a receiver never reports
     * a radius of zero, so unlike [altitude] the sentinel costs no real
     * measurement and the column has not needed widening. Read it through
     * [accuracyMOrNull] rather than testing the number at each call site:
     * "is there an accuracy" is one question with one answer, and it is asked
     * by the upload metadata, the photos-table dump, and (on the far side of
     * the wire) the API's public response.
     */
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
    /** "gps" or "map" (the map centre) — same vocabulary as the EXIF provenance; null when the photo records no position. */
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

    /**
     * Which enrichers have not finished with this row yet, as a bitmask (v27) —
     * see [UPLOAD_HOLD_REFINER] and [UPLOAD_HOLD_IMU_WINDOW].
     *
     * The hold has more than one holder, and that cannot be expressed as a
     * deadline. Two enrichers finish at different times and neither may free the
     * row while the other is still filling it; encoding that in
     * [uploadHoldUntil] alone means each one releasing to the OTHER's deadline,
     * which silently does nothing when the two deadlines are equal — and in
     * practice they were, so every photo waited out the full hold. A UploadHoldTest
     * case caught exactly that.
     *
     * So the deadline is now only CRASH RECOVERY: a row whose enricher died is
     * freed when it expires. The normal path is each holder clearing its own bit,
     * and the row is uploadable once no bits remain.
     */
    val uploadHoldReasons: Int = 0,

    // When the stamp refiner (v16) replaced the at-the-time values with
    // interpolated ones — location interpolated across the bracketing fixes,
    // compass bearing recomputed as a CENTERED window over the ~10 Hz
    // samples (zero phase lag, unlike the live causal value), car-mode
    // bearing interpolated across the bracketing Kalman rows. Null = never
    // refined: not eligible (manual position), no bracketing data in time,
    // or the upload grabbed the row first — all of which deliberately keep
    // the at-the-time stamp. Rides into the upload metadata as "refined".
    val stampRefinedAt: Long? = null,

    /**
     * The licence THIS photo is offered under (v17), snapshotted from the
     * global setting at capture.
     *
     * A licence is a statement about a particular photo, made when it was
     * taken — not a property of the app's current configuration. Reading the
     * global setting at UPLOAD time meant a photo shot under one licence and
     * uploaded after the user changed the setting went out under the new
     * one, silently, which is the wrong answer and an unpleasant one to
     * discover later.
     *
     * Null on rows captured before this existed; the upload falls back to
     * the global setting for those, so they stay uploadable.
     */
    val license: String? = null,

    /**
     * Camera elevation at the shutter, degrees, positive up (v19). Bearing
     * says which way the camera faced; this says how far it was tilted, and
     * the viewer pane needs both to offer "the photo above this one".
     *
     * Nullable on purpose, unlike `bearing` which uses 0.0 for unset: the
     * viewer's rule is strictly-higher / strictly-lower, so "level" and
     * "not recorded" must not collapse into each other.
     */
    val pitch: Double? = null,

    /**
     * The position stream the photo did NOT record (v20), as the JSON the
     * upload metadata sends under `alt_location` — the original's field,
     * which the backend synthesizes into the UserComment provenance. Kept
     * as JSON rather than five columns because it is opaque to this table:
     * nothing here reads it, it only travels.
     */
    val altLocationJson: String? = null,

    /**
     * What the DEVICE was measuring at the shutter (v24), as the JSON the
     * upload metadata sends under `attitude` — pitch and roll, the raw and
     * corrected compass headings, the fusion that produced them, the
     * quantized device pose and the landscape-workaround flag.
     *
     * The ELECTED answer is [bearing] and [pitch]; this is the measurement
     * beside it, which a manual claim or a car course cannot own. Roll had
     * no column anywhere in the stack before this, so it never left the
     * device, though the sensor service has always computed it.
     *
     * SO PITCH APPEARS TWICE ON PURPOSE, and the two are different claims:
     * [pitch] is what the photo is STAMPED as, and travels as the upload's
     * top-level `pitch` into `photos.pitch`; `attitude.pitch_deg` here is
     * what the SENSOR read at that instant. They agree whenever nothing
     * overrode the stamp, and when something did, only the second one is
     * still a measurement. Same relation as [bearing] to
     * `attitude.heading_true_deg`. See docs/recon-capture-metadata.md,
     * "Pitch has three homes".
     *
     * JSON rather than six columns for the same reason as [altLocationJson]:
     * it is opaque to this table, nothing here reads it, it only travels —
     * and the set of things worth recording about a pose will grow.
     */
    val attitudeJson: String? = null,

    /**
     * The RAW inertial window this photo owns (v26), columnar and
     * delta-encoded — see `imuSamplesPayloadJson`.
     *
     * The one thing here that is BULK rather than provenance: a few thousand
     * samples, tens of kilobytes, against a handful of numbers for every other
     * JSON column on this row. It is held here anyway, rather than read from
     * `imu_samples` at upload time, because that table is cleared five minutes
     * back on every dump while an upload can be retried hours later on a phone
     * that had no network. A window that existed at the shutter and is gone by
     * the time the photo sends is the drop-site pattern this whole body of work
     * was about closing.
     *
     * It carries only the samples in [ImuWindow.storedFromMs]..window-end — what
     * this photo OWNS. Consecutive photos in an interval run therefore tile the
     * session instead of each repeating the same six seconds.
     *
     * Deliberately NOT folded into the UserComment: it travels as its own
     * top-level `imu_samples` metadata field and lands in the storage pool as a
     * gzipped file, because `exif_data` is read wholesale on every photo detail
     * request. docs/recon-capture-metadata.md, Phase 5.
     */
    val imuSamplesJson: String? = null,

    /**
     * What the RECEIVER said about its own fix at the shutter (v25) — the
     * error bars and the motion, as the upload metadata's `fix` object. NOT
     * the position, which is already four columns here.
     */
    val fixJson: String? = null,

    /**
     * The camera's own calibration and settings at the shutter (v25) —
     * intrinsics, distortion, focus, zoom, as the upload metadata's `lens`
     * object. The difference between a reconstruction that SOLVES for
     * intrinsics and one that is told them.
     */
    val lensJson: String? = null,

    /**
     * What the phone's INERTIAL sensors read at the shutter (v25, renamed in
     * v28) — gravity, linear acceleration, and the summary of the IMU window
     * around the exposure, as the upload metadata's `inertial` object.
     *
     * It was `motion`, and that name was wrong about its own contents: the
     * flagship field is GRAVITY, which a still phone reports at full strength
     * and a moving one does not change. An object called "motion" whose main
     * value is largest at zero motion misleads every reader once.
     *
     * `inertial` covers all three honestly — gravity, linear acceleration and
     * the window's angular rates are inertial measurements — and matches the
     * vocabulary already in use here (`imu_window`, `ImuRing`, IMU = inertial
     * measurement unit). Renamed before anything shipped; see
     * docs/recon-capture-metadata.md for why the pose/inertial SPLIT stayed.
     */
    val inertialJson: String? = null
)

/**
 * The accuracy radius this row records, or null where it records none.
 *
 * The one place that knows what absent looks like in [PhotoEntity.accuracy].
 * Callers ask for the value, not for the encoding, so a row with no accuracy
 * omits the field rather than publishing a radius of nothing — which would
 * read as a perfect fix, the opposite of the truth.
 */
val PhotoEntity.accuracyMOrNull: Double? get() = accuracy.takeIf { it > 0.0 }

enum class UploadStatus {
    PENDING,
    UPLOADING,
    COMPLETED,
    FAILED
}

package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.PrimaryKey

/**
 * The RAW inertial window a photo owns, columnar and delta-encoded — see
 * `imuSamplesPayloadJson`. Its own table since v32 (2026-11-06); before that it was
 * the `photos.imuSamplesJson` column.
 *
 * WHY A TABLE AND NOT A COLUMN: it is the one BULK value a photo carries — a few
 * thousand samples, tens of kilobytes, against a handful of numbers in every other
 * column — and as a column it rode along with every `SELECT * FROM photos`. The
 * upload drain counted its candidates that way, and a 5385-photo queue took the
 * heap from 10 MB to the 256 MB limit in twenty seconds: OutOfMemoryError at every
 * app start. Narrowing that one query fixed the crash; this makes the whole class
 * of it impossible, since no query on `photos` can reach these bytes any more.
 *
 * WHY IT IS KEPT AFTER UPLOAD rather than dropped once the server reports the
 * photo completed: an edit (an anonymization override) sets the row back to
 * pending and re-uploads it, and the backend assigns `imu_samples_url` from each
 * processing run (photo_routes.py, "a reprocess that produced none must CLEAR a
 * stale URL"). A window deleted here would delete the server's copy at the next
 * edit. When it may be deleted is a decision this table leaves open.
 *
 * WHY IT IS HELD ON THE PHONE AT ALL, and not re-read from `imu_samples` at send
 * time: that table is cleared five minutes back on every dump, while an upload
 * can be retried hours later on a phone that had no network.
 *
 * It carries only the samples this capture CLAIMED (`imu_claims`), so consecutive
 * photos in an interval run tile the session instead of each repeating the same
 * six seconds. It travels as the top-level `imu_samples` upload metadata field —
 * deliberately NOT in the UserComment. docs/recon-capture-metadata.md, Phase 5.
 *
 * The cascade goes with the photo: a physically deleted row takes its window.
 */
@Entity(
    tableName = "photo_imu_samples",
    foreignKeys = [
        ForeignKey(
            entity = PhotoEntity::class,
            parentColumns = ["id"],
            childColumns = ["photoId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
)
data class PhotoImuSamplesEntity(
    @PrimaryKey val photoId: String,
    /** The `imu_samples` payload, as JSON text. */
    val samplesJson: String,
)

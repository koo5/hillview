package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index

@Entity(
    tableName = "bearings",
    // (timestamp, sourceId), not timestamp alone. Every stream writes into one
    // epoch-ms space — the sensor stack at ~10 Hz off currentTimeMillis, the
    // Kalman heading off the fix's location.time, manual writes off the
    // caller's clock — so a same-ms sample from another source used to REPLACE
    // its neighbour, silently, with the survivor decided by whichever IO
    // coroutine happened to land last.
    primaryKeys = ["timestamp", "sourceId"],
    foreignKeys = [
        ForeignKey(
            entity = SourceEntity::class,
            parentColumns = ["id"],
            childColumns = ["sourceId"]
        ),
        ForeignKey(
            entity = SourceEntity::class,
            parentColumns = ["id"],
            childColumns = ["electedSourceId"]
        )
    ],
    indices = [Index(value = ["sourceId"]), Index(value = ["electedSourceId"])]
)
data class BearingEntity(
    val timestamp: Long,
    val trueHeading: Float,
    val magneticHeading: Float? = null,
    val accuracyLevel: Int? = null, // Android SensorManager constants: -1=unknown, 0=unreliable, 1=low, 2=medium, 3=high
    val sourceId: Int, // Foreign key to sources table
    // How this sample was produced *within* its source: the fusion algorithm
    // for "android", the gesture for "manual". Held apart from the source name
    // so the source stays a small, stable, elect-able vocabulary.
    val detail: String? = null,
    // Which source was the primary (elected) one at this instant — the same
    // value on every row of that instant, whichever stream wrote them, so a
    // row stays self-describing under truncation and across CSV files.
    // Null until the election plumbing lands.
    val electedSourceId: Int? = null,
    val pitch: Float? = null,
    val roll: Float? = null,
    /**
     * What the sensor that produced this sample said about ITSELF
     * (`SensorEvent.accuracy`), 0..3; null when nothing rated it.
     *
     * [accuracyLevel] above is the bare MAGNETOMETER's latched calibration,
     * which the default fusion (TYPE_ROTATION_VECTOR) depends on only
     * indirectly — and which rates the heading, not the pitch and roll that
     * come from gravity and the gyro. This is the emitting sensor's own
     * per-sample rating. Both are kept because they disagree, and which one
     * is low says whether the magnetic field or the fusion was the trouble.
     *
     * A COLUMN and not a JSON blob, unlike `photos.attitudeJson`: this table
     * takes a row at sensor rate (5-20 Hz), where a JSON cell would repeat
     * its key names on every row and force a parse per row on the CSV that
     * `pics` reads column-wise. The photos blob is one row per photo and
     * open-ended provenance; a sensor sample is a fixed shape of scalars,
     * which is what columns are for.
     *
     * Null for hand-set bearings (no sensor produced them) and for the
     * Madgwick and complementary filters, which compose several raw sensors
     * and have no single rating to pass on.
     */
    val fusedSensorAccuracy: Int? = null
)

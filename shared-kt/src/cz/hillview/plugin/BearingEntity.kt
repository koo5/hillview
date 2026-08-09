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
    val roll: Float? = null
)

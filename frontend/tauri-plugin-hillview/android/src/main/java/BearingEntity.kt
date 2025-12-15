package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "bearings",
    foreignKeys = [
        ForeignKey(
            entity = SourceEntity::class,
            parentColumns = ["id"],
            childColumns = ["sourceId"]
        )
    ],
    indices = [Index(value = ["sourceId"])]
)
data class BearingEntity(
    @PrimaryKey
    val timestamp: Long,
    val trueHeading: Float,
    val magneticHeading: Float? = null,
    val headingAccuracy: Float? = null, // Calculated accuracy in degrees (for future use)
    val accuracyLevel: Int? = null, // Android SensorManager constants: -1=unknown, 0=unreliable, 1=low, 2=medium, 3=high
    val sourceId: Int, // Foreign key to sources table
    val pitch: Float? = null,
    val roll: Float? = null
)
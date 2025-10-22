package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "bearings")
data class BearingEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val timestamp: Long,
    val magneticHeading: Float,
    val trueHeading: Float,
    val headingAccuracy: Float, // Calculated accuracy in degrees (for future use)
    val accuracyLevel: Int, // Android SensorManager constants: -1=unknown, 0=unreliable, 1=low, 2=medium, 3=high
    val source: String, // Sensor source identifier
    val pitch: Float,
    val roll: Float
)
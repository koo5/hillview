package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "locations",
    foreignKeys = [
        ForeignKey(
            entity = SourceEntity::class,
            parentColumns = ["id"],
            childColumns = ["sourceId"]
        )
    ],
    indices = [Index(value = ["sourceId"])]
)
data class LocationEntity(
    @PrimaryKey
    val timestamp: Long,
    val latitude: Double,
    val longitude: Double,
    val sourceId: Int, // Foreign key to sources table
    val altitude: Double? = null,
    val accuracy: Float? = null, // Horizontal accuracy in meters
    val verticalAccuracy: Float? = null, // Vertical accuracy in meters
    val speed: Float? = null, // Speed in meters/second
    val bearing: Float? = null // Bearing/heading from GPS in degrees
)
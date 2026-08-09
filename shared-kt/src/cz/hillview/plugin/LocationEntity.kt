package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index

@Entity(
    tableName = "locations",
    // See BearingEntity for why the key is composite: the fix stream (keyed on
    // location.time) and the manual/map stream (keyed on the caller's clock)
    // share one epoch-ms space, and a collision used to REPLACE silently.
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
data class LocationEntity(
    val timestamp: Long,
    val latitude: Double,
    val longitude: Double,
    val sourceId: Int, // Foreign key to sources table
    // How this fix was produced within its source — the Android location
    // provider ("fused"/"gps"/"network") for "android", the gesture for
    // "manual". See BearingEntity.detail.
    val detail: String? = null,
    // Which source was primary at this instant. See BearingEntity.electedSourceId.
    val electedSourceId: Int? = null,
    val altitude: Double? = null,
    val accuracy: Float? = null, // Horizontal accuracy in meters
    val verticalAccuracy: Float? = null, // Vertical accuracy in meters
    val speed: Float? = null, // Speed in meters/second
    val bearing: Float? = null // Bearing/heading from GPS in degrees
)

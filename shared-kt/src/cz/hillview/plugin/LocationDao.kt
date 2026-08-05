package cz.hillview.plugin

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface LocationDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun insertLocation(location: LocationEntity)

    // Latest location at or before a timestamp, used to pair a location with a
    // photo (e.g. externally-captured ones). Background-tracking rows are excluded
    // by default: they're recorded while the user has panned away, so they must
    // not win this lookup — the manual map-pan location should.
    @Query("""
        SELECT * FROM locations
        WHERE timestamp <= :timestamp
        AND sourceId NOT IN (SELECT id FROM sources WHERE name LIKE '%background%')
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    fun getLocationNearTimestamp(timestamp: Long): LocationEntity?

    @Query("DELETE FROM locations WHERE timestamp < :timestamp")
    fun clearLocationsOlderThan(timestamp: Long)

    @Query("DELETE FROM locations")
    fun clearAllLocations()

    @Query("SELECT * FROM locations ORDER BY timestamp ASC")
    fun getAllLocations(): List<LocationEntity>


}
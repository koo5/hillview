package cz.hillview.plugin

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface LocationDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun insertLocation(location: LocationEntity)

    @Query("""
        SELECT * FROM locations
        WHERE timestamp <= :timestamp
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
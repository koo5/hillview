package cz.hillview.plugin

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface BearingDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun insertBearing(bearing: BearingEntity)

    @Query("""
        SELECT * FROM bearings
        WHERE timestamp <= :timestamp
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    fun getBearingNearTimestamp(timestamp: Long): BearingEntity?

    @Query("DELETE FROM bearings WHERE timestamp < :timestamp")
    fun clearBearingsOlderThan(timestamp: Long)

    @Query("DELETE FROM bearings")
    fun clearAllBearings()

    @Query("SELECT * FROM bearings ORDER BY timestamp ASC")
    fun getAllBearings(): List<BearingEntity>


}

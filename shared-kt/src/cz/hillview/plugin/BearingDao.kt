package cz.hillview.plugin

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface BearingDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun insertBearing(bearing: BearingEntity)

    // See LocationDao.getLocationNearTimestamp for the reasoning behind
    // `sourceId = electedSourceId`. It also closes the source-blindness this
    // query used to have: a gps-kalman (car mode) bearing could win on recency
    // while the user was walking, because nothing said which stream was chosen.
    @Query("""
        SELECT * FROM bearings
        WHERE timestamp <= :timestamp
        AND (electedSourceId IS NULL OR sourceId = electedSourceId)
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    fun getBearingNearTimestamp(timestamp: Long): BearingEntity?

    @Query("DELETE FROM bearings WHERE timestamp < :timestamp")
    fun clearBearingsOlderThan(timestamp: Long)

    @Query("DELETE FROM bearings")
    fun clearAllBearings()

    // sourceId breaks the tie: a timestamp is no longer unique, so without it
    // the dump order among same-instant rows would be SQLite's choice and a
    // re-export could reshuffle them.
    @Query("SELECT * FROM bearings ORDER BY timestamp ASC, sourceId ASC")
    fun getAllBearings(): List<BearingEntity>


}

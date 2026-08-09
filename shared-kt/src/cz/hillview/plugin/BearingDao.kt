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

    // The stamp refiner's reads (StampRefiner): per-source, deliberately NOT
    // election-filtered — the refiner already knows which stream stamped the
    // photo and asks for that stream by name.
    @Query("""
        SELECT * FROM bearings
        WHERE sourceId = :sourceId AND timestamp BETWEEN :from AND :to
        ORDER BY timestamp ASC
    """)
    fun getBearingsInWindow(from: Long, to: Long, sourceId: Int): List<BearingEntity>

    @Query("""
        SELECT * FROM bearings
        WHERE sourceId = :sourceId AND timestamp <= :timestamp
        ORDER BY timestamp DESC LIMIT 1
    """)
    fun getBearingAtOrBefore(timestamp: Long, sourceId: Int): BearingEntity?

    @Query("""
        SELECT * FROM bearings
        WHERE sourceId = :sourceId AND timestamp > :timestamp
        ORDER BY timestamp ASC LIMIT 1
    """)
    fun getBearingAfter(timestamp: Long, sourceId: Int): BearingEntity?

    // The external-camera screen's live tally.
    @Query("SELECT COUNT(*) FROM bearings")
    fun countBearings(): Int

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

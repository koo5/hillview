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
    // photo (e.g. externally-captured ones). `sourceId = electedSourceId` is the
    // whole filter: it keeps only rows written BY the source that was primary at
    // the moment they were written, which is precisely "what the app was using".
    // A fix recorded while the user had panned away has sourceId=android against
    // an election of manual, so it drops out on its own — no name mangling, and
    // none of the write-ordering choreography that the old '%background%'
    // exclusion needed to stay correct.
    //
    // The NULL arm keeps rows written before any election was pushed eligible,
    // so an app that has not elected yet behaves as it did before, rather than
    // finding nothing at all.
    @Query("""
        SELECT * FROM locations
        WHERE timestamp <= :timestamp
        AND (electedSourceId IS NULL OR sourceId = electedSourceId)
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    fun getLocationNearTimestamp(timestamp: Long): LocationEntity?

    // The stamp refiner's bracket reads — per-source by design, see
    // BearingDao.getBearingsInWindow.
    @Query("""
        SELECT * FROM locations
        WHERE sourceId = :sourceId AND timestamp <= :timestamp
        ORDER BY timestamp DESC LIMIT 1
    """)
    fun getLocationAtOrBefore(timestamp: Long, sourceId: Int): LocationEntity?

    @Query("""
        SELECT * FROM locations
        WHERE sourceId = :sourceId AND timestamp > :timestamp
        ORDER BY timestamp ASC LIMIT 1
    """)
    fun getLocationAfter(timestamp: Long, sourceId: Int): LocationEntity?

    // The external-camera screen's live tally.
    @Query("SELECT COUNT(*) FROM locations")
    fun countLocations(): Int

    @Query("DELETE FROM locations WHERE timestamp < :timestamp")
    fun clearLocationsOlderThan(timestamp: Long)

    @Query("DELETE FROM locations")
    fun clearAllLocations()

    // See BearingDao.getAllBearings — sourceId keeps the dump order stable now
    // that a timestamp can carry more than one row.
    @Query("SELECT * FROM locations ORDER BY timestamp ASC, sourceId ASC")
    fun getAllLocations(): List<LocationEntity>


}
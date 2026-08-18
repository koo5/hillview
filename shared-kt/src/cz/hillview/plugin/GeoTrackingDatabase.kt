package cz.hillview.plugin

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

/**
 * The sensor record: bearings, locations, and the source lookup they key on.
 *
 * Its own file, deliberately. These tables and `photos` have opposite natures
 * and had been sharing one SQLite file, which meant sharing one write lock:
 *
 *  - `photos` is DURABLE and low-rate. Rows are written once per capture and
 *    then carry the upload state machine, so a blocked write there is a lost
 *    capture or a stalled queue.
 *  - these are EPHEMERAL and written at SENSOR rate — several rows a second
 *    while recording — then exported to CSV and bulk-deleted every five
 *    minutes (GeoTrackingManager.dumpAndClear).
 *
 * One lock between them means a bulk delete of a few thousand sensor rows can
 * stall a photo insert, and that is not hypothetical: the start-time dump and
 * the start-time upload reconcile collided often enough to throw SQLITE_BUSY.
 * A busy timeout would have made the loser wait instead of fail, which is
 * paying for the contention rather than removing it. Two files means two write
 * locks: the sensor stream and the capture path simply cannot block each other
 * any more.
 *
 * Splitting is cheap precisely because the group is closed — bearings and
 * locations have foreign keys to sources and to nothing else, and `photos`
 * records its provenance as plain TEXT source names, not ids.
 */
@Database(
    entities = [BearingEntity::class, LocationEntity::class, SourceEntity::class],
    version = 1,
    // Exported per app into shared-kt/schemas/{frontend2,tauri}/, same as
    // PhotoDatabase — and with the same warning: the export is wired through a
    // processor argument Gradle does not track as an output, so a regenerated
    // schema JSON must be COMMITTED with the change that caused it.
    exportSchema = true
)
abstract class GeoTrackingDatabase : RoomDatabase() {

    abstract fun bearingDao(): BearingDao
    abstract fun locationDao(): LocationDao
    abstract fun sourceDao(): SourceDao

    companion object {
        @Volatile
        private var INSTANCE: GeoTrackingDatabase? = null

        fun getDatabase(context: Context): GeoTrackingDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    GeoTrackingDatabase::class.java,
                    "hillview_geo_tracking_database"
                )
                    // No migrations, and none coming: version 1 starts empty
                    // because the data is disposable by design. The tables it
                    // replaces held at most one session's tail — they are
                    // cleared to now-5min on every dump — so the split costs
                    // that tail once, and nothing after.
                    .build()
                INSTANCE = instance
                instance
            }
        }
    }
}

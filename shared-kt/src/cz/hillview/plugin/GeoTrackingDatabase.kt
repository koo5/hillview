package cz.hillview.plugin

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

/**
 * The schema version, named so its migration test targets the CURRENT one rather
 * than a literal. `PhotoDatabase`'s equivalent literal had gone stale by five
 * versions while its "whole chain" test kept passing — see [PHOTO_DB_VERSION].
 */
const val GEO_DB_VERSION = 4

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
    entities = [
        BearingEntity::class, LocationEntity::class, SourceEntity::class,
        ImuSampleEntity::class, ImuClaimEntity::class,
    ],
    version = GEO_DB_VERSION,
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
    abstract fun imuDao(): ImuDao
    abstract fun imuClaimDao(): ImuClaimDao

    companion object {
        @Volatile
        private var INSTANCE: GeoTrackingDatabase? = null

        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                // What the emitting sensor said about itself, per sample
                // (BearingEntity.fusedSensorAccuracy) — beside accuracyLevel, which
                // is the bare magnetometer's latched calibration. Null on
                // existing rows: they were written before it was kept.
                db.execSQL("ALTER TABLE bearings ADD COLUMN fusedSensorAccuracy INTEGER")
            }
        }

        private val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                // The IMU window around a shutter (ImuSampleEntity) — written
                // per CAPTURE, never continuously. No foreign key to sources:
                // these are raw hardware, not an elect-able stream, and nothing
                // arbitrates between two accelerometers.
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS imu_samples (
                        timestamp INTEGER NOT NULL,
                        kind TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        x REAL NOT NULL,
                        y REAL NOT NULL,
                        z REAL NOT NULL,
                        elapsedNanos INTEGER NOT NULL,
                        PRIMARY KEY(timestamp, kind, sequence)
                    )
                    """,
                )
                db.execSQL(
                    "CREATE INDEX IF NOT EXISTS index_imu_samples_timestamp ON imu_samples(timestamp)",
                )
            }
        }

        private val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                // Which capture owns which samples (ImuClaimEntity). One row per
                // PHOTO, not per sample: attribution has to be data, and a
                // 6-byte owner column on every sample row would cost ~33 KB per
                // photo here and tens of megabytes an hour in the CSV dump for
                // the same answer.
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS imu_claims (
                        capturedAtMs INTEGER NOT NULL,
                        fromMs INTEGER NOT NULL,
                        toMs INTEGER NOT NULL,
                        sampleCount INTEGER NOT NULL,
                        PRIMARY KEY(capturedAtMs)
                    )
                    """,
                )
            }
        }

        internal val MIGRATIONS = arrayOf(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)

        fun getDatabase(context: Context): GeoTrackingDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    GeoTrackingDatabase::class.java,
                    "hillview_geo_tracking_database"
                )
                    // Version 1 started empty because the data is disposable
                    // by design: the tables it replaced held at most one
                    // session's tail — they are cleared to now-5min on every
                    // dump — so the split cost that tail once, and nothing
                    // after.
                    //
                    // "No migrations, and none coming" stood here until
                    // 2026-09-26. It was a statement about what the SPLIT
                    // cost, not a prohibition, and the first added column made
                    // the difference plain: a real ALTER TABLE is one line and
                    // keeps the session in progress, where a destructive
                    // fallback would throw away the tail a dump has not
                    // reached yet. Disposable data makes migrations CHEAP, not
                    // unnecessary — the thing that makes them frightening,
                    // losing what the user cannot regenerate, is what is
                    // missing here.
                    .addMigrations(*MIGRATIONS)
                    .build()
                INSTANCE = instance
                instance
            }
        }
    }
}

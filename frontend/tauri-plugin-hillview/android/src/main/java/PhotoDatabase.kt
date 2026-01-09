package cz.hillview.plugin

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
@Database(
    entities = [PhotoEntity::class, BearingEntity::class, LocationEntity::class, SourceEntity::class],
    version = 10,
    exportSchema = false
)
abstract class PhotoDatabase : RoomDatabase() {

    abstract fun photoDao(): SimplePhotoDao
    abstract fun bearingDao(): BearingDao
    abstract fun locationDao(): LocationDao
    abstract fun sourceDao(): SourceDao

    companion object {
        @Volatile
        private var INSTANCE: PhotoDatabase? = null

        private val MIGRATION_6_7 = object : Migration(6, 7) {
            override fun migrate(database: SupportSQLiteDatabase) {
                // Rename timestamp column to capturedAt
                database.execSQL("ALTER TABLE photos RENAME COLUMN timestamp TO capturedAt")
            }
        }

        private val MIGRATION_7_8 = object : Migration(7, 8) {
            override fun migrate(database: SupportSQLiteDatabase) {
                // Create initial bearings and locations tables without normalized sources
                database.execSQL("""
                    CREATE TABLE IF NOT EXISTS bearings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        trueHeading REAL NOT NULL,
                        magneticHeading REAL,
                        headingAccuracy REAL,
                        accuracyLevel INTEGER,
                        source TEXT NOT NULL,
                        pitch REAL,
                        roll REAL
                    )
                """)

                database.execSQL("""
                    CREATE TABLE IF NOT EXISTS locations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        latitude REAL NOT NULL,
                        longitude REAL NOT NULL,
                        source TEXT NOT NULL,
                        altitude REAL,
                        accuracy REAL,
                        verticalAccuracy REAL,
                        speed REAL,
                        bearing REAL
                    )
                """)
            }
        }

        private val MIGRATION_8_9 = object : Migration(8, 9) {
            override fun migrate(database: SupportSQLiteDatabase) {
                // Create sources table
                database.execSQL("""
                    CREATE TABLE IF NOT EXISTS sources (
                        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                        name TEXT NOT NULL
                    )
                """)
                database.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS index_sources_name ON sources (name)")

                // Drop old tables and create new ones with normalized schema
                database.execSQL("DROP TABLE IF EXISTS bearings")
                database.execSQL("DROP TABLE IF EXISTS locations")

                database.execSQL("""
                    CREATE TABLE bearings (
                        timestamp INTEGER PRIMARY KEY NOT NULL,
                        trueHeading REAL NOT NULL,
                        magneticHeading REAL,
                        headingAccuracy REAL,
                        accuracyLevel INTEGER,
                        sourceId INTEGER NOT NULL,
                        pitch REAL,
                        roll REAL,
                        FOREIGN KEY (sourceId) REFERENCES sources (id)
                    )
                """)
                database.execSQL("CREATE INDEX IF NOT EXISTS index_bearings_sourceId ON bearings (sourceId)")

                database.execSQL("""
                    CREATE TABLE locations (
                        timestamp INTEGER PRIMARY KEY NOT NULL,
                        latitude REAL NOT NULL,
                        longitude REAL NOT NULL,
                        sourceId INTEGER NOT NULL,
                        altitude REAL,
                        accuracy REAL,
                        verticalAccuracy REAL,
                        speed REAL,
                        bearing REAL,
                        FOREIGN KEY (sourceId) REFERENCES sources (id)
                    )
                """)
                database.execSQL("CREATE INDEX IF NOT EXISTS index_locations_sourceId ON locations (sourceId)")
            }
        }

		private val MIGRATION_9_10 = object : Migration(9, 10) {
			override fun migrate(database: SupportSQLiteDatabase) {
				database.execSQL("ALTER TABLE bearings DROP COLUMN headingAccuracy")
			}
		}

        fun getDatabase(context: Context): PhotoDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    PhotoDatabase::class.java,
                    "hillview_photos_database"
                )
                    .addMigrations(MIGRATION_6_7, MIGRATION_7_8, MIGRATION_8_9, MIGRATION_9_10)
                    .build()
                INSTANCE = instance
                instance
            }
        }
    }
}

package cz.hillview.plugin

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
@Database(
    entities = [PhotoEntity::class, BearingEntity::class, LocationEntity::class, SourceEntity::class, EditEntity::class],
    version = 13,
    exportSchema = false
)
abstract class PhotoDatabase : RoomDatabase() {

    abstract fun photoDao(): SimplePhotoDao
    abstract fun bearingDao(): BearingDao
    abstract fun locationDao(): LocationDao
    abstract fun sourceDao(): SourceDao
    abstract fun editDao(): EditDao

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
				// DROP COLUMN not supported on SQLite < 3.35.0 (Android < API 34)
				// Recreate the table without headingAccuracy
				database.execSQL("""
					CREATE TABLE bearings_new (
						timestamp INTEGER PRIMARY KEY NOT NULL,
						trueHeading REAL NOT NULL,
						magneticHeading REAL,
						accuracyLevel INTEGER,
						sourceId INTEGER NOT NULL,
						pitch REAL,
						roll REAL,
						FOREIGN KEY (sourceId) REFERENCES sources (id)
					)
				""")
				database.execSQL("""
					INSERT INTO bearings_new (timestamp, trueHeading, magneticHeading, accuracyLevel, sourceId, pitch, roll)
					SELECT timestamp, trueHeading, magneticHeading, accuracyLevel, sourceId, pitch, roll FROM bearings
				""")
				database.execSQL("DROP TABLE bearings")
				database.execSQL("ALTER TABLE bearings_new RENAME TO bearings")
				database.execSQL("CREATE INDEX IF NOT EXISTS index_bearings_sourceId ON bearings (sourceId)")
			}
		}

		private val MIGRATION_10_11 = object : Migration(10, 11) {
			override fun migrate(database: SupportSQLiteDatabase) {
				database.execSQL("ALTER TABLE photos ADD COLUMN serverPhotoId TEXT")
			}
		}

		private val MIGRATION_11_12 = object : Migration(11, 12) {
			override fun migrate(database: SupportSQLiteDatabase) {
				// Add deleted column to photos table
				database.execSQL("ALTER TABLE photos ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")

				// Create edits table for pending photo edit actions
				database.execSQL("""
					CREATE TABLE IF NOT EXISTS edits (
						id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
						photoId TEXT NOT NULL,
						actionJson TEXT NOT NULL,
						createdAt INTEGER NOT NULL,
						processed INTEGER NOT NULL DEFAULT 0,
						processedAt INTEGER NOT NULL DEFAULT 0,
						FOREIGN KEY (photoId) REFERENCES photos (id) ON DELETE CASCADE
					)
				""")
				database.execSQL("CREATE INDEX IF NOT EXISTS idx_edits_photo_id ON edits (photoId)")
				database.execSQL("CREATE INDEX IF NOT EXISTS idx_edits_created_at ON edits (createdAt)")
			}
		}

		private val MIGRATION_12_13 = object : Migration(12, 13) {
			override fun migrate(database: SupportSQLiteDatabase) {
				// Add version column for re-upload support (e.g., changing anonymization settings)
				database.execSQL("ALTER TABLE photos ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
				// Add anonymization override column (null = auto-detect, "[]" = skip, "[{...}]" = manual)
				database.execSQL("ALTER TABLE photos ADD COLUMN anonymizationOverride TEXT")
			}
		}

        fun getDatabase(context: Context): PhotoDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    PhotoDatabase::class.java,
                    "hillview_photos_database"
                )
                    .addMigrations(MIGRATION_6_7, MIGRATION_7_8, MIGRATION_8_9, MIGRATION_9_10, MIGRATION_10_11, MIGRATION_11_12, MIGRATION_12_13)
                    .build()
                INSTANCE = instance
                instance
            }
        }
    }
}

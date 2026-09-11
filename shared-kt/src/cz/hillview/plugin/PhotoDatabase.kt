package cz.hillview.plugin

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
@Database(
    // The sensor tables (bearings/locations/sources) moved OUT to
    // GeoTrackingDatabase in v18 — see that file for why. What is left here is
    // durable and low-rate: a capture and the edits that belong to it.
    entities = [PhotoEntity::class, EditEntity::class],
    version = 20,
    // Schemas are exported per app (they compile these entities with different
    // Room versions) into shared-kt/schemas/{frontend2,tauri}/ — see
    // docs/geo-election-test-todo.md item 6. Both agree on the identityHash;
    // the files differ only in how verbosely each Room version writes them.
    //
    // If you change an entity here, COMMIT THE REGENERATED JSON with it: the
    // export is wired through a processor argument in each app's build file,
    // which Gradle does not track as an output, so nothing enforces this and a
    // stale schema file is silently possible. Both build files carry the long
    // version of this warning.
    exportSchema = true
)
abstract class PhotoDatabase : RoomDatabase() {

    abstract fun photoDao(): SimplePhotoDao
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

		private val MIGRATION_13_14 = object : Migration(13, 14) {
			override fun migrate(database: SupportSQLiteDatabase) {
				// bearings and locations are ephemeral by construction —
				// dumpAndClear keeps a five-minute window — so there is nothing
				// here worth carrying across. Drop and recreate the way
				// MIGRATION_8_9 did, not the copy-rename dance a durable table
				// would need (SQLite cannot ALTER a primary key either way).
				//
				// sources goes with them: its vocabulary is replaced wholesale
				// by the normalization pass that follows ("android
				// UPRIGHT_ROTATION_VECTOR (EMA smoothed)" -> "android", the
				// location provider -> "android", arrow_drag/url/featured ->
				// "manual"), so the old names would only linger as dead rows
				// holding ids nothing writes again. Children first, so the drop
				// leaves no dangling reference.
				database.execSQL("DROP TABLE IF EXISTS bearings")
				database.execSQL("DROP TABLE IF EXISTS locations")
				database.execSQL("DROP TABLE IF EXISTS sources")

				database.execSQL("""
					CREATE TABLE IF NOT EXISTS sources (
						id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
						name TEXT NOT NULL
					)
				""")
				database.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS index_sources_name ON sources (name)")

				// PRIMARY KEY (timestamp, sourceId): one row per source per
				// millisecond, instead of one row per millisecond overall.
				// detail and electedSourceId land now so the later passes that
				// fill them need no second migration; both stay NULL until then.
				database.execSQL("""
					CREATE TABLE bearings (
						timestamp INTEGER NOT NULL,
						trueHeading REAL NOT NULL,
						magneticHeading REAL,
						accuracyLevel INTEGER,
						sourceId INTEGER NOT NULL,
						detail TEXT,
						electedSourceId INTEGER,
						pitch REAL,
						roll REAL,
						PRIMARY KEY (timestamp, sourceId),
						FOREIGN KEY (sourceId) REFERENCES sources (id),
						FOREIGN KEY (electedSourceId) REFERENCES sources (id)
					)
				""")
				database.execSQL("CREATE INDEX IF NOT EXISTS index_bearings_sourceId ON bearings (sourceId)")
				database.execSQL("CREATE INDEX IF NOT EXISTS index_bearings_electedSourceId ON bearings (electedSourceId)")

				database.execSQL("""
					CREATE TABLE locations (
						timestamp INTEGER NOT NULL,
						latitude REAL NOT NULL,
						longitude REAL NOT NULL,
						sourceId INTEGER NOT NULL,
						detail TEXT,
						electedSourceId INTEGER,
						altitude REAL,
						accuracy REAL,
						verticalAccuracy REAL,
						speed REAL,
						bearing REAL,
						PRIMARY KEY (timestamp, sourceId),
						FOREIGN KEY (sourceId) REFERENCES sources (id),
						FOREIGN KEY (electedSourceId) REFERENCES sources (id)
					)
				""")
				database.execSQL("CREATE INDEX IF NOT EXISTS index_locations_sourceId ON locations (sourceId)")
				database.execSQL("CREATE INDEX IF NOT EXISTS index_locations_electedSourceId ON locations (electedSourceId)")
			}
		}

		private val MIGRATION_14_15 = object : Migration(14, 15) {
			override fun migrate(database: SupportSQLiteDatabase) {
				// photos is DURABLE (unlike the tracking tables), so this is
				// additive: the stamp-provenance columns the fast-write
				// upload path sends in the worker `metadata` field. Old rows
				// stay null and the worker falls back to their files' EXIF.
				database.execSQL("ALTER TABLE photos ADD COLUMN bearingSource TEXT")
				database.execSQL("ALTER TABLE photos ADD COLUMN locationSource TEXT")
				database.execSQL("ALTER TABLE photos ADD COLUMN locationAgeMs INTEGER")
				database.execSQL("ALTER TABLE photos ADD COLUMN exposureJson TEXT")
			}
		}

		private val MIGRATION_15_16 = object : Migration(15, 16) {
			override fun migrate(database: SupportSQLiteDatabase) {
				// The stamp refiner's marker and its upload gate (see
				// PhotoEntity.stampRefinedAt / uploadHoldUntil).
				database.execSQL("ALTER TABLE photos ADD COLUMN stampRefinedAt INTEGER")
				database.execSQL("ALTER TABLE photos ADD COLUMN uploadHoldUntil INTEGER NOT NULL DEFAULT 0")
			}
		}

		private val MIGRATION_16_17 = object : Migration(16, 17) {
			override fun migrate(database: SupportSQLiteDatabase) {
				// Per-photo licence (see PhotoEntity.license). Null on every
				// existing row, which is what keeps them uploadable: the
				// upload falls back to the global setting for those.
				database.execSQL("ALTER TABLE photos ADD COLUMN license TEXT")
			}
		}

		private val MIGRATION_17_18 = object : Migration(17, 18) {
			override fun migrate(database: SupportSQLiteDatabase) {
				// The sensor tables now live in their own file
				// (GeoTrackingDatabase) so that a bulk delete of sensor rows
				// can no longer stall a photo write. Dropped rather than
				// copied: this data is disposable by design — exported to CSV
				// and cleared to now-5min every five minutes — so what is lost
				// is at most one session's tail, once.
				//
				// Children before parent: bearings and locations carry foreign
				// keys into sources.
				database.execSQL("DROP TABLE IF EXISTS bearings")
				database.execSQL("DROP TABLE IF EXISTS locations")
				database.execSQL("DROP TABLE IF EXISTS sources")
			}
		}

		private val MIGRATION_18_19 = object : Migration(18, 19) {
			override fun migrate(database: SupportSQLiteDatabase) {
				// Camera elevation at the shutter (see PhotoEntity.pitch).
				// Null on every existing row, which is what the viewer wants:
				// "not recorded" must stay distinct from "level".
				database.execSQL("ALTER TABLE photos ADD COLUMN pitch REAL")
			}
		}

		private val MIGRATION_19_20 = object : Migration(19, 20) {
			override fun migrate(database: SupportSQLiteDatabase) {
				// The alternative position stream (PhotoEntity.altLocationJson).
				// Null on existing rows: they were taken before it was kept.
				database.execSQL("ALTER TABLE photos ADD COLUMN altLocationJson TEXT")
			}
		}

        fun getDatabase(context: Context): PhotoDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    PhotoDatabase::class.java,
                    "hillview_photos_database"
                )
                    .addMigrations(MIGRATION_6_7, MIGRATION_7_8, MIGRATION_8_9, MIGRATION_9_10, MIGRATION_10_11, MIGRATION_11_12, MIGRATION_12_13, MIGRATION_13_14, MIGRATION_14_15, MIGRATION_15_16, MIGRATION_16_17, MIGRATION_17_18, MIGRATION_18_19, MIGRATION_19_20)
                    .build()
                INSTANCE = instance
                instance
            }
        }
    }
}

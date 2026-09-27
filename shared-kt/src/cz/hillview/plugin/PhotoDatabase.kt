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
    entities = [PhotoEntity::class, EditEntity::class, PhotoOutboxEntity::class],
    version = PHOTO_DB_VERSION,
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
    abstract fun outboxDao(): PhotoOutboxDao

    companion object {
        @Volatile
        private var INSTANCE: PhotoDatabase? = null

        private val MIGRATION_6_7 = object : Migration(6, 7) {
            override fun migrate(db: SupportSQLiteDatabase) {
                // Rename timestamp column to capturedAt
                db.execSQL("ALTER TABLE photos RENAME COLUMN timestamp TO capturedAt")
            }
        }

        private val MIGRATION_7_8 = object : Migration(7, 8) {
            override fun migrate(db: SupportSQLiteDatabase) {
                // Create initial bearings and locations tables without normalized sources
                db.execSQL("""
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

                db.execSQL("""
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
            override fun migrate(db: SupportSQLiteDatabase) {
                // Create sources table
                db.execSQL("""
                    CREATE TABLE IF NOT EXISTS sources (
                        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                        name TEXT NOT NULL
                    )
                """)
                db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS index_sources_name ON sources (name)")

                // Drop old tables and create new ones with normalized schema
                db.execSQL("DROP TABLE IF EXISTS bearings")
                db.execSQL("DROP TABLE IF EXISTS locations")

                db.execSQL("""
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
                db.execSQL("CREATE INDEX IF NOT EXISTS index_bearings_sourceId ON bearings (sourceId)")

                db.execSQL("""
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
                db.execSQL("CREATE INDEX IF NOT EXISTS index_locations_sourceId ON locations (sourceId)")
            }
        }

		private val MIGRATION_9_10 = object : Migration(9, 10) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// DROP COLUMN not supported on SQLite < 3.35.0 (Android < API 34)
				// Recreate the table without headingAccuracy
				db.execSQL("""
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
				db.execSQL("""
					INSERT INTO bearings_new (timestamp, trueHeading, magneticHeading, accuracyLevel, sourceId, pitch, roll)
					SELECT timestamp, trueHeading, magneticHeading, accuracyLevel, sourceId, pitch, roll FROM bearings
				""")
				db.execSQL("DROP TABLE bearings")
				db.execSQL("ALTER TABLE bearings_new RENAME TO bearings")
				db.execSQL("CREATE INDEX IF NOT EXISTS index_bearings_sourceId ON bearings (sourceId)")
			}
		}

		private val MIGRATION_10_11 = object : Migration(10, 11) {
			override fun migrate(db: SupportSQLiteDatabase) {
				db.execSQL("ALTER TABLE photos ADD COLUMN serverPhotoId TEXT")
			}
		}

		private val MIGRATION_11_12 = object : Migration(11, 12) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// Add deleted column to photos table
				db.execSQL("ALTER TABLE photos ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")

				// Create edits table for pending photo edit actions
				db.execSQL("""
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
				db.execSQL("CREATE INDEX IF NOT EXISTS idx_edits_photo_id ON edits (photoId)")
				db.execSQL("CREATE INDEX IF NOT EXISTS idx_edits_created_at ON edits (createdAt)")
			}
		}

		private val MIGRATION_12_13 = object : Migration(12, 13) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// Add version column for re-upload support (e.g., changing anonymization settings)
				db.execSQL("ALTER TABLE photos ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
				// Add anonymization override column (null = auto-detect, "[]" = skip, "[{...}]" = manual)
				db.execSQL("ALTER TABLE photos ADD COLUMN anonymizationOverride TEXT")
			}
		}

		private val MIGRATION_13_14 = object : Migration(13, 14) {
			override fun migrate(db: SupportSQLiteDatabase) {
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
				db.execSQL("DROP TABLE IF EXISTS bearings")
				db.execSQL("DROP TABLE IF EXISTS locations")
				db.execSQL("DROP TABLE IF EXISTS sources")

				db.execSQL("""
					CREATE TABLE IF NOT EXISTS sources (
						id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
						name TEXT NOT NULL
					)
				""")
				db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS index_sources_name ON sources (name)")

				// PRIMARY KEY (timestamp, sourceId): one row per source per
				// millisecond, instead of one row per millisecond overall.
				// detail and electedSourceId land now so the later passes that
				// fill them need no second migration; both stay NULL until then.
				db.execSQL("""
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
				db.execSQL("CREATE INDEX IF NOT EXISTS index_bearings_sourceId ON bearings (sourceId)")
				db.execSQL("CREATE INDEX IF NOT EXISTS index_bearings_electedSourceId ON bearings (electedSourceId)")

				db.execSQL("""
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
				db.execSQL("CREATE INDEX IF NOT EXISTS index_locations_sourceId ON locations (sourceId)")
				db.execSQL("CREATE INDEX IF NOT EXISTS index_locations_electedSourceId ON locations (electedSourceId)")
			}
		}

		private val MIGRATION_14_15 = object : Migration(14, 15) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// photos is DURABLE (unlike the tracking tables), so this is
				// additive: the stamp-provenance columns the fast-write
				// upload path sends in the worker `metadata` field. Old rows
				// stay null and the worker falls back to their files' EXIF.
				db.execSQL("ALTER TABLE photos ADD COLUMN bearingSource TEXT")
				db.execSQL("ALTER TABLE photos ADD COLUMN locationSource TEXT")
				db.execSQL("ALTER TABLE photos ADD COLUMN locationAgeMs INTEGER")
				db.execSQL("ALTER TABLE photos ADD COLUMN exposureJson TEXT")
			}
		}

		private val MIGRATION_15_16 = object : Migration(15, 16) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// The stamp refiner's marker and its upload gate (see
				// PhotoEntity.stampRefinedAt / uploadHoldUntil).
				db.execSQL("ALTER TABLE photos ADD COLUMN stampRefinedAt INTEGER")
				db.execSQL("ALTER TABLE photos ADD COLUMN uploadHoldUntil INTEGER NOT NULL DEFAULT 0")
			}
		}

		private val MIGRATION_16_17 = object : Migration(16, 17) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// Per-photo licence (see PhotoEntity.license). Null on every
				// existing row, which is what keeps them uploadable: the
				// upload falls back to the global setting for those.
				db.execSQL("ALTER TABLE photos ADD COLUMN license TEXT")
			}
		}

		private val MIGRATION_17_18 = object : Migration(17, 18) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// The sensor tables now live in their own file
				// (GeoTrackingDatabase) so that a bulk delete of sensor rows
				// can no longer stall a photo write. Dropped rather than
				// copied: this data is disposable by design — exported to CSV
				// and cleared to now-5min every five minutes — so what is lost
				// is at most one session's tail, once.
				//
				// Children before parent: bearings and locations carry foreign
				// keys into sources.
				db.execSQL("DROP TABLE IF EXISTS bearings")
				db.execSQL("DROP TABLE IF EXISTS locations")
				db.execSQL("DROP TABLE IF EXISTS sources")
			}
		}

		private val MIGRATION_18_19 = object : Migration(18, 19) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// Camera elevation at the shutter (see PhotoEntity.pitch).
				// Null on every existing row, which is what the viewer wants:
				// "not recorded" must stay distinct from "level".
				db.execSQL("ALTER TABLE photos ADD COLUMN pitch REAL")
			}
		}

		private val MIGRATION_19_20 = object : Migration(19, 20) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// The alternative position stream (PhotoEntity.altLocationJson).
				// Null on existing rows: they were taken before it was kept.
				db.execSQL("ALTER TABLE photos ADD COLUMN altLocationJson TEXT")
			}
		}

		private val MIGRATION_20_21 = object : Migration(20, 21) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// altitude becomes NULLABLE (see PhotoEntity.altitude). Every
				// other photos migration has been an ALTER TABLE ADD COLUMN;
				// this one cannot be, because SQLite has no way to drop a NOT
				// NULL constraint in place — the column has to be rebuilt, the
				// same copy-and-rename MIGRATION_9_10 did for bearings.
				//
				// NULLIF(altitude, 0.0) is what makes this a no-op for
				// existing rows rather than a change of meaning: 0.0 WAS the
				// absent sentinel, tested as "> 0" by both readers, so a
				// stored 0.0 has never once been sent to the server. Carrying
				// it across as a real 0.0 would start claiming sea level for
				// every row that simply never had a fix.
				//
				// The drop is safe for `edits`, which references photos(id) ON
				// DELETE CASCADE: Room touches PRAGMA foreign_keys only in the
				// generated onOpen (which runs after migrations) and in
				// clearAllTables, so enforcement is at SQLite's per-connection
				// default of OFF here and the implicit DELETE FROM fires no
				// cascade. Were that ever to change, the rename below would
				// fail on the dangling reference and the whole migration would
				// roll back — loudly, not silently.
				db.execSQL("""
					CREATE TABLE photos_new (
						id TEXT NOT NULL,
						filename TEXT NOT NULL,
						path TEXT NOT NULL,
						latitude REAL NOT NULL,
						longitude REAL NOT NULL,
						altitude REAL,
						bearing REAL NOT NULL,
						capturedAt INTEGER NOT NULL,
						accuracy REAL NOT NULL,
						width INTEGER NOT NULL,
						height INTEGER NOT NULL,
						fileSize INTEGER NOT NULL,
						createdAt INTEGER NOT NULL,
						uploadStatus TEXT NOT NULL,
						uploadedAt INTEGER NOT NULL,
						retryCount INTEGER NOT NULL,
						lastUploadAttempt INTEGER NOT NULL,
						uploadError TEXT NOT NULL,
						fileHash TEXT NOT NULL,
						serverPhotoId TEXT,
						deleted INTEGER NOT NULL,
						version INTEGER NOT NULL,
						anonymizationOverride TEXT,
						bearingSource TEXT,
						locationSource TEXT,
						locationAgeMs INTEGER,
						exposureJson TEXT,
						uploadHoldUntil INTEGER NOT NULL,
						stampRefinedAt INTEGER,
						license TEXT,
						pitch REAL,
						altLocationJson TEXT,
						PRIMARY KEY(id)
					)
				""")
				db.execSQL("""
					INSERT INTO photos_new (
						id, filename, path, latitude, longitude, altitude, bearing,
						capturedAt, accuracy, width, height, fileSize, createdAt,
						uploadStatus, uploadedAt, retryCount, lastUploadAttempt,
						uploadError, fileHash, serverPhotoId, deleted, version,
						anonymizationOverride, bearingSource, locationSource,
						locationAgeMs, exposureJson, uploadHoldUntil, stampRefinedAt,
						license, pitch, altLocationJson
					)
					SELECT
						id, filename, path, latitude, longitude, NULLIF(altitude, 0.0), bearing,
						capturedAt, accuracy, width, height, fileSize, createdAt,
						uploadStatus, uploadedAt, retryCount, lastUploadAttempt,
						uploadError, fileHash, serverPhotoId, deleted, version,
						anonymizationOverride, bearingSource, locationSource,
						locationAgeMs, exposureJson, uploadHoldUntil, stampRefinedAt,
						license, pitch, altLocationJson
					FROM photos
				""")
				db.execSQL("DROP TABLE photos")
				db.execSQL("ALTER TABLE photos_new RENAME TO photos")

				// The indices go with the old table; recreate all five exactly
				// as PhotoEntity declares them, or Room's identity check fails
				// on the next open.
				db.execSQL("CREATE INDEX IF NOT EXISTS idx_photos_created_at ON photos (createdAt)")
				db.execSQL("CREATE INDEX IF NOT EXISTS idx_photos_upload_status_created_at ON photos (uploadStatus, createdAt)")
				db.execSQL("CREATE INDEX IF NOT EXISTS idx_photos_location ON photos (latitude, longitude)")
				db.execSQL("CREATE INDEX IF NOT EXISTS idx_photos_file_hash ON photos (fileHash)")
				db.execSQL("CREATE INDEX IF NOT EXISTS idx_photos_path ON photos (path)")
			}
		}

		private val MIGRATION_21_22 = object : Migration(21, 22) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// latitude and longitude become NULLABLE (see PhotoEntity),
				// the same rebuild MIGRATION_20_21 did for altitude — SQLite
				// cannot drop a NOT NULL in place. Same foreign-key reasoning
				// as there: enforcement is off during migrations, so dropping
				// the parent does not cascade `edits`.
				//
				// The (0.0, 0.0) PAIR is carried across as null. It was never
				// a place: the shutter gate kept a capture from ever having
				// no position, and the only writer of (0, 0) was the EXIF
				// import path defaulting a file with no GPS tags. A single
				// zero coordinate with a real other one is left alone — the
				// equator and the meridian are real, Null Island is not.
				db.execSQL("""
					CREATE TABLE photos_new (
						id TEXT NOT NULL,
						filename TEXT NOT NULL,
						path TEXT NOT NULL,
						latitude REAL,
						longitude REAL,
						altitude REAL,
						bearing REAL NOT NULL,
						capturedAt INTEGER NOT NULL,
						accuracy REAL NOT NULL,
						width INTEGER NOT NULL,
						height INTEGER NOT NULL,
						fileSize INTEGER NOT NULL,
						createdAt INTEGER NOT NULL,
						uploadStatus TEXT NOT NULL,
						uploadedAt INTEGER NOT NULL,
						retryCount INTEGER NOT NULL,
						lastUploadAttempt INTEGER NOT NULL,
						uploadError TEXT NOT NULL,
						fileHash TEXT NOT NULL,
						serverPhotoId TEXT,
						deleted INTEGER NOT NULL,
						version INTEGER NOT NULL,
						anonymizationOverride TEXT,
						bearingSource TEXT,
						locationSource TEXT,
						locationAgeMs INTEGER,
						exposureJson TEXT,
						uploadHoldUntil INTEGER NOT NULL,
						stampRefinedAt INTEGER,
						license TEXT,
						pitch REAL,
						altLocationJson TEXT,
						PRIMARY KEY(id)
					)
				""")
				db.execSQL("""
					INSERT INTO photos_new (
						id, filename, path, latitude, longitude, altitude, bearing,
						capturedAt, accuracy, width, height, fileSize, createdAt,
						uploadStatus, uploadedAt, retryCount, lastUploadAttempt,
						uploadError, fileHash, serverPhotoId, deleted, version,
						anonymizationOverride, bearingSource, locationSource,
						locationAgeMs, exposureJson, uploadHoldUntil, stampRefinedAt,
						license, pitch, altLocationJson
					)
					SELECT
						id, filename, path,
						CASE WHEN latitude = 0.0 AND longitude = 0.0 THEN NULL ELSE latitude END,
						CASE WHEN latitude = 0.0 AND longitude = 0.0 THEN NULL ELSE longitude END,
						altitude, bearing,
						capturedAt, accuracy, width, height, fileSize, createdAt,
						uploadStatus, uploadedAt, retryCount, lastUploadAttempt,
						uploadError, fileHash, serverPhotoId, deleted, version,
						anonymizationOverride, bearingSource, locationSource,
						locationAgeMs, exposureJson, uploadHoldUntil, stampRefinedAt,
						license, pitch, altLocationJson
					FROM photos
				""")
				db.execSQL("DROP TABLE photos")
				db.execSQL("ALTER TABLE photos_new RENAME TO photos")
				db.execSQL("CREATE INDEX IF NOT EXISTS idx_photos_created_at ON photos (createdAt)")
				db.execSQL("CREATE INDEX IF NOT EXISTS idx_photos_upload_status_created_at ON photos (uploadStatus, createdAt)")
				db.execSQL("CREATE INDEX IF NOT EXISTS idx_photos_location ON photos (latitude, longitude)")
				db.execSQL("CREATE INDEX IF NOT EXISTS idx_photos_file_hash ON photos (fileHash)")
				db.execSQL("CREATE INDEX IF NOT EXISTS idx_photos_path ON photos (path)")
			}
		}

		/**
		 * photo_outbox (v23) — what this client wants the SERVER to know and
		 * has not managed to tell it: a rating, and a wanted deletion, with
		 * room for the tagging, description and voice-note kinds to come. See
		 * PhotoOutboxEntity for why a row is a state rather than a message.
		 *
		 * A pure addition. No existing table is touched, so there is nothing
		 * to carry across and nothing already there to get wrong.
		 */
		private val MIGRATION_22_23 = object : Migration(22, 23) {
			override fun migrate(db: SupportSQLiteDatabase) {
				db.execSQL("""
					CREATE TABLE IF NOT EXISTS photo_outbox (
						userId TEXT NOT NULL,
						photoId TEXT NOT NULL,
						kind TEXT NOT NULL,
						itemId TEXT NOT NULL,
						valueJson TEXT,
						revision INTEGER NOT NULL,
						syncedRevision INTEGER NOT NULL,
						changedAt INTEGER NOT NULL,
						attempts INTEGER NOT NULL,
						lastAttemptAt INTEGER NOT NULL,
						lastError TEXT NOT NULL,
						PRIMARY KEY(userId, photoId, kind, itemId),
						FOREIGN KEY(photoId) REFERENCES photos(id) ON UPDATE NO ACTION ON DELETE CASCADE
					)
				""")
				db.execSQL(
					"CREATE INDEX IF NOT EXISTS idx_outbox_photo_id ON photo_outbox(photoId)"
				)
				db.execSQL(
					"CREATE INDEX IF NOT EXISTS idx_outbox_user_changed ON photo_outbox(userId, changedAt)"
				)
			}
		}

		private val MIGRATION_23_24 = object : Migration(23, 24) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// What the DEVICE measured at the shutter, as opposed to what
				// the photo is stamped as facing (PhotoEntity.attitudeJson):
				// roll — which had never left the phone at all — beside the
				// raw and corrected headings, the fusion that produced them,
				// the quantized device pose and the landscape-workaround flag.
				// Null on existing rows: they were taken before it was kept.
				db.execSQL("ALTER TABLE photos ADD COLUMN attitudeJson TEXT")
			}
		}

		private val MIGRATION_24_25 = object : Migration(24, 25) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// The rest of what the phone knows at the shutter and had been
				// throwing away — see docs/recon-capture-metadata.md. Three
				// columns in ONE migration rather than three versions: they are
				// one change with one reason, and a reviewer reading the history
				// should see it that way.
				//
				// Null on existing rows: taken before any of it was kept.
				db.execSQL("ALTER TABLE photos ADD COLUMN fixJson TEXT")
				db.execSQL("ALTER TABLE photos ADD COLUMN lensJson TEXT")
				// `motionJson`, its name AT THE TIME. A migration is history and
				// must not be rewritten: a blanket motionJson -> inertialJson
				// rename swept this line up, and then v28's RENAME COLUMN failed
				// on every FRESH install ("no such column: motionJson") while
				// still working on a device that had the original v25. The
				// emulator's whole-chain test caught it; the hand-written 27->28
				// check did not, because it only ever started at 27.
				db.execSQL("ALTER TABLE photos ADD COLUMN motionJson TEXT")
			}
		}

		private val MIGRATION_25_26 = object : Migration(25, 26) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// The raw IMU window, as the payload that travels with the photo
				// (docs/recon-capture-metadata.md, Phase 5). One column, and the
				// only BULK one on this table — tens of kilobytes rather than a
				// handful of numbers. See PhotoEntity.imuSamplesJson for why it
				// is held here instead of re-read from imu_samples at send time.
				//
				// Null on existing rows: their windows were never kept.
				db.execSQL("ALTER TABLE photos ADD COLUMN imuSamplesJson TEXT")
			}
		}

		private val MIGRATION_26_27 = object : Migration(26, 27) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// Which enrichers still hold this row's upload (PhotoEntity
				// .uploadHoldReasons). The hold had one deadline and two holders,
				// so whichever finished first freed the row out from under the
				// other — and encoding two holders in one deadline does not work
				// when their deadlines coincide, which is the normal case.
				//
				// 0 on existing rows: nothing is mid-enrichment across an upgrade,
				// and StartupReconciler clears stale holds at launch anyway.
				db.execSQL(
					"ALTER TABLE photos ADD COLUMN uploadHoldReasons INTEGER NOT NULL DEFAULT 0",
				)
			}
		}

		private val MIGRATION_27_28 = object : Migration(27, 28) {
			override fun migrate(db: SupportSQLiteDatabase) {
				// `motion` -> `inertial`, renamed before anything deployed. The
				// object's flagship field is GRAVITY, which is at full strength when
				// there is no motion at all, so the old name said the opposite of
				// what the value means. See PhotoEntity.inertialJson.
				db.execSQL("ALTER TABLE photos RENAME COLUMN motionJson TO inertialJson")
			}
		}

		/**
		 * Every migration, in one list, so the runtime builder and
		 * PhotoDatabaseMigrationTest cannot disagree about which ones exist.
		 */
		internal val MIGRATIONS = arrayOf(
			MIGRATION_6_7, MIGRATION_7_8, MIGRATION_8_9, MIGRATION_9_10,
			MIGRATION_10_11, MIGRATION_11_12, MIGRATION_12_13, MIGRATION_13_14,
			MIGRATION_14_15, MIGRATION_15_16, MIGRATION_16_17, MIGRATION_17_18,
			MIGRATION_18_19, MIGRATION_19_20, MIGRATION_20_21, MIGRATION_21_22,
			MIGRATION_22_23, MIGRATION_23_24, MIGRATION_24_25,
			MIGRATION_25_26, MIGRATION_26_27, MIGRATION_27_28,
		)

        fun getDatabase(context: Context): PhotoDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    PhotoDatabase::class.java,
                    "hillview_photos_database"
                )
                    .addMigrations(*MIGRATIONS)
                    .build()
                INSTANCE = instance
                instance
            }
        }
    }
}/**
 * The schema version, as a named constant so the MIGRATION TEST can assert it
 * reaches the current one instead of a literal that silently falls behind.
 *
 * It had fallen behind: `theWholeChainRunsAndMatchesTheEntities` validated
 * 14 -> 23 and kept passing while the database went to 28, so five migrations
 * (attitudeJson, the fix/lens/inertial trio, imuSamplesJson, uploadHoldReasons,
 * the inertial rename) were never once validated against the entities. A hardcoded
 * target in a test whose job is to catch drift is the one place drift hides.
 */
const val PHOTO_DB_VERSION = 28



package cz.hillview.plugin

import androidx.room.testing.MigrationTestHelper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The migrations run against the REAL exported schemas, on a real SQLite.
 *
 * `runMigrationsAndValidate` is the part that cannot be eyeballed: it applies
 * the migration to a database created at the older version and then compares
 * the result, column by column and index by index, with the schema Room
 * generated from the entities. A migration that drifts from `PhotoEntity` —
 * a forgotten index, a column left NOT NULL — fails here rather than on a
 * user's phone at the next open.
 *
 * The schema JSONs reach the test through the `androidx.room` Gradle plugin,
 * which stages `shared-kt/schemas/frontend2/` into this variant's assets.
 */
@RunWith(AndroidJUnit4::class)
class PhotoDatabaseMigrationTest {

    @get:Rule
    val helper = MigrationTestHelper(
        InstrumentationRegistry.getInstrumentation(),
        PhotoDatabase::class.java,
    )

    /** A v20 row, with altitude as the last positional column that matters here. */
    private fun insertV20Photo(db: androidx.sqlite.db.SupportSQLiteDatabase, id: String, altitude: Double) {
        db.execSQL(
            """
            INSERT INTO photos (
                id, filename, path, latitude, longitude, altitude, bearing,
                capturedAt, accuracy, width, height, fileSize, createdAt,
                uploadStatus, uploadedAt, retryCount, lastUploadAttempt,
                uploadError, fileHash, deleted, version, uploadHoldUntil
            ) VALUES (?, ?, ?, 50.1, 14.4, ?, 137.5, 1, 4.2, 4, 4, 16, 1,
                      'pending', 0, 0, 0, '', 'hash-$id', 0, 1, 0)
            """.trimIndent(),
            arrayOf<Any>(id, "$id.jpg", "/tmp/$id.jpg", altitude),
        )
    }

    /**
     * The whole point of MIGRATION_20_21: 0.0 was the absent sentinel and has
     * never been sent to the server, so it must arrive as NULL — while a real
     * measurement, negative included, must arrive unchanged.
     */
    @Test
    fun theAltitudeSentinelBecomesNullAndRealMeasurementsSurvive() {
        helper.createDatabase(DB, 20).use { db ->
            insertV20Photo(db, "absent", 0.0)
            insertV20Photo(db, "above", 231.5)
            insertV20Photo(db, "below", -61.4)
        }

        val db = helper.runMigrationsAndValidate(DB, 21, true, *PhotoDatabase.MIGRATIONS)

        db.query("SELECT id, altitude FROM photos ORDER BY id").use { c ->
            val seen = mutableMapOf<String, Double?>()
            while (c.moveToNext()) {
                seen[c.getString(0)] = if (c.isNull(1)) null else c.getDouble(1)
            }
            assertEquals(3, seen.size)
            assertNull(seen["absent"], "the 0.0 sentinel must not become a real sea-level claim")
            assertEquals(231.5, seen["above"]!!, 0.0001)
            assertEquals(-61.4, seen["below"]!!, 0.0001)
        }
    }

    /** The rebuild drops and recreates photos; `edits` must not go with it. */
    @Test
    fun theRebuildDoesNotCascadeAwayPendingEdits() {
        helper.createDatabase(DB, 20).use { db ->
            insertV20Photo(db, "p1", 100.0)
            db.execSQL(
                "INSERT INTO edits (photoId, actionJson, createdAt, processed, processedAt) " +
                    "VALUES ('p1', '{\"action\":\"set_anonymization_override\"}', 1, 0, 0)",
            )
        }

        val db = helper.runMigrationsAndValidate(DB, 21, true, *PhotoDatabase.MIGRATIONS)

        db.query("SELECT photoId FROM edits").use { c ->
            assertTrue(c.moveToNext(), "the edit was cascade-deleted by the photos rebuild")
            assertEquals("p1", c.getString(0))
        }
    }

    /** Every step from the oldest schema Room still has, in one go. */
    @Test
    fun theWholeChainRunsAndMatchesTheEntities() {
        helper.createDatabase(DB, 14).close()
        helper.runMigrationsAndValidate(DB, 21, true, *PhotoDatabase.MIGRATIONS)
    }

    private companion object {
        const val DB = "migration-test.db"
    }
}

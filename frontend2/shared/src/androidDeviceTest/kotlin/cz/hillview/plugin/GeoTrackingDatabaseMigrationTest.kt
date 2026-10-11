package cz.hillview.plugin

import androidx.room.testing.MigrationTestHelper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.test.assertEquals

/**
 * The sensor database's migrations, against the real exported schemas on real
 * SQLite — the check `PhotoDatabase` has had and this one had not.
 *
 * It went to v4 (fusedSensorAccuracy, `imu_samples`, `imu_claims`) with nothing
 * validating any of it on a device; the versions were only ever compared against
 * the exported JSON by a hand-written script, which cannot see what SQLite
 * actually does with an `ALTER`. That gap is how a rewritten migration shipped in
 * the photo database undetected until an emulator ran the chain.
 */
@RunWith(AndroidJUnit4::class)
class GeoTrackingDatabaseMigrationTest {

    @get:Rule
    val helper = MigrationTestHelper(
        InstrumentationRegistry.getInstrumentation(),
        GeoTrackingDatabase::class.java,
    )

    private val DB = "geo-migration-test.db"

    /**
     * v1 to current, validated field by field and index by index against the
     * entities. Targets [GEO_DB_VERSION], never a literal.
     */
    @Test
    fun theWholeChainRunsAndMatchesTheEntities() {
        helper.createDatabase(DB, 1).close()
        helper.runMigrationsAndValidate(DB, GEO_DB_VERSION, true, *GeoTrackingDatabase.MIGRATIONS)
    }

    /**
     * A bearing written before `fusedSensorAccuracy` existed survives the
     * migration with the column NULL — not 0, which would claim the emitting
     * sensor had reported "unreliable" when in fact nothing asked it.
     */
    @Test
    fun anOldBearingSurvivesWithANullAccuracy() {
        helper.createDatabase(DB, 1).use { db ->
            db.execSQL(
                "INSERT INTO sources (id, name) VALUES (1, 'test-source')",
            )
            // Columns as v1 actually declared them, read out of
            // schemas/.../GeoTrackingDatabase/1.json rather than remembered:
            // the heading is `trueHeading`, and there is no `elected` yet.
            db.execSQL(
                "INSERT INTO bearings (timestamp, trueHeading, magneticHeading, " +
                    "accuracyLevel, sourceId, detail, electedSourceId, pitch, roll) " +
                    "VALUES (1700000000000, 137.5, NULL, 3, 1, NULL, 1, NULL, NULL)",
            )
        }
        val db = helper.runMigrationsAndValidate(
            DB, GEO_DB_VERSION, true, *GeoTrackingDatabase.MIGRATIONS,
        )
        db.query("SELECT trueHeading, fusedSensorAccuracy FROM bearings").use { c ->
            assertEquals(1, c.count)
            c.moveToFirst()
            assertEquals(137.5, c.getDouble(0), 1e-6)
            assertEquals(true, c.isNull(1), "fusedSensorAccuracy should be NULL, not 0")
        }
    }

    /** The two tables added later exist and are empty, not missing. */
    @Test
    fun theSampleAndClaimTablesArriveEmpty() {
        helper.createDatabase(DB, 1).close()
        val db = helper.runMigrationsAndValidate(
            DB, GEO_DB_VERSION, true, *GeoTrackingDatabase.MIGRATIONS,
        )
        for (table in listOf("imu_samples", "imu_claims")) {
            db.query("SELECT COUNT(*) FROM $table").use { c ->
                c.moveToFirst()
                assertEquals(0, c.getInt(0), "$table should exist and be empty")
            }
        }
    }
}

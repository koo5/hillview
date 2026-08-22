package cz.hillview.plugin

import androidx.room.Room
import androidx.test.platform.app.InstrumentationRegistry
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import org.junit.After
import org.junit.Before
import org.junit.Test

/**
 * What the tracking tables themselves promise — on a device because the
 * promise is Room's, and Room only exists there.
 *
 * The subject is the v14 shape (see docs/geo-election-test-todo.md item 1):
 * `(timestamp, sourceId)` as the primary key, and the `electedSourceId`
 * filter the two lookup queries do. An in-memory database, so the app's own
 * rows are never touched — this is about the schema, not about a session.
 */
class GeoTrackingTablesTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    private lateinit var db: GeoTrackingDatabase
    private var android = 0
    private var manual = 0
    private var kalman = 0

    @Before
    fun openDatabase() {
        db = Room.inMemoryDatabaseBuilder(context, GeoTrackingDatabase::class.java).build()
        // The whole elect-able vocabulary, which is the point of it being
        // this short — see the v13→v14 migration note in PhotoDatabase.
        android = db.sourceDao().getOrCreateSourceId("android")
        manual = db.sourceDao().getOrCreateSourceId("manual")
        kalman = db.sourceDao().getOrCreateSourceId("gps-kalman")
    }

    @After
    fun closeDatabase() {
        db.close()
    }

    private fun bearing(timestamp: Long, sourceId: Int, heading: Float, elected: Int? = null) =
        BearingEntity(
            timestamp = timestamp,
            trueHeading = heading,
            sourceId = sourceId,
            electedSourceId = elected,
        )

    private fun location(timestamp: Long, sourceId: Int, latitude: Double, elected: Int? = null) =
        LocationEntity(
            timestamp = timestamp,
            latitude = latitude,
            longitude = 14.0,
            sourceId = sourceId,
            electedSourceId = elected,
        )

    /**
     * The core of the rework. Every stream writes into one epoch-ms space —
     * the sensor stack off currentTimeMillis, the Kalman heading off the
     * fix's location.time, manual writes off the caller's clock — and on a
     * timestamp-only key a same-ms neighbour REPLACED the row already there,
     * with the survivor decided by whichever IO coroutine landed last.
     */
    @Test
    fun twoSourcesMayShareAMillisecond() {
        db.bearingDao().insertBearing(bearing(1_000, android, 10f))
        db.bearingDao().insertBearing(bearing(1_000, kalman, 200f))

        val rows = db.bearingDao().getAllBearings()
        assertEquals(2, rows.size, "a same-millisecond sample from another source must not replace its neighbour")
        assertEquals(listOf(10f, 200f), rows.map { it.trueHeading }.sorted())

        db.locationDao().insertLocation(location(1_000, android, 50.1))
        db.locationDao().insertLocation(location(1_000, manual, 50.9))
        assertEquals(2, db.locationDao().getAllLocations().size)
    }

    /**
     * The narrowing is deliberate and stops there: one source still cannot
     * hold two rows for one millisecond, and the later write wins.
     */
    @Test
    fun oneSourceAtOneMillisecondStillCollapses() {
        db.bearingDao().insertBearing(bearing(1_000, android, 10f))
        db.bearingDao().insertBearing(bearing(1_000, android, 20f))

        val rows = db.bearingDao().getAllBearings()
        assertEquals(1, rows.size, "REPLACE still applies within a source")
        assertEquals(20f, rows.single().trueHeading, "the later sample is the surviving one")

        db.locationDao().insertLocation(location(1_000, manual, 50.1))
        db.locationDao().insertLocation(location(1_000, manual, 50.9))
        assertEquals(50.9, db.locationDao().getAllLocations().single().latitude, 1e-9)
    }

    /** A timestamp is no longer unique, so the dump order has to break the tie. */
    @Test
    fun theDumpOrderIsStableAcrossSourcesAtOneInstant() {
        listOf(kalman, android, manual).forEach { source ->
            db.bearingDao().insertBearing(bearing(1_000, source, 1f))
            db.locationDao().insertLocation(location(1_000, source, 50.0))
        }

        assertEquals(
            db.bearingDao().getAllBearings().map { it.sourceId },
            db.bearingDao().getAllBearings().map { it.sourceId }.sorted(),
        )
        assertEquals(
            db.locationDao().getAllLocations().map { it.sourceId },
            db.locationDao().getAllLocations().map { it.sourceId }.sorted(),
        )
    }

    /**
     * The lookup a photo runs to find where it was taken. `sourceId =
     * electedSourceId` keeps only rows written BY the source that was primary
     * when they were written — a fix recorded while the user had panned away
     * is an `android` row against an election of `manual`, so it drops out on
     * its own, with no name mangling and no write-ordering choreography.
     */
    @Test
    fun theLookupKeepsOnlyWhatTheAppWasActuallyUsing() {
        // The user claimed the map position at t=1000; a fix landed at t=1500
        // while the claim stood, and is NOT what the app was using.
        db.locationDao().insertLocation(location(1_000, manual, 50.9, elected = manual))
        db.locationDao().insertLocation(location(1_500, android, 50.1, elected = manual))

        val found = db.locationDao().getLocationNearTimestamp(2_000)
        assertNotNull(found)
        assertEquals(manual, found.sourceId, "the elected source answers, not merely the most recent row")
        assertEquals(50.9, found.latitude, 1e-9)
    }

    /**
     * The same filter on the bearing side, where the source-blindness had
     * teeth of its own: a gps-kalman (car mode) heading could win on recency
     * while the user was walking, because nothing said which stream was
     * chosen.
     */
    @Test
    fun aCarHeadingCannotWinOnRecencyWhileWalking() {
        db.bearingDao().insertBearing(bearing(1_000, android, 10f, elected = android))
        db.bearingDao().insertBearing(bearing(1_500, kalman, 200f, elected = android))

        val found = db.bearingDao().getBearingNearTimestamp(2_000)
        assertNotNull(found)
        assertEquals(10f, found.trueHeading, "an unelected stream must not answer for the elected one")
    }

    /**
     * Dumps written before the election plumbing landed carry no election at
     * all. Those rows stay eligible — an app that has not elected yet behaves
     * as it did before, rather than finding nothing at all.
     */
    @Test
    fun rowsWithoutAnElectionStayEligible() {
        db.locationDao().insertLocation(location(1_000, android, 50.1))
        db.bearingDao().insertBearing(bearing(1_000, android, 10f))

        assertNotNull(db.locationDao().getLocationNearTimestamp(2_000))
        assertNotNull(db.bearingDao().getBearingNearTimestamp(2_000))
    }

    /** The five-minute truncation dumpAndClear runs, unchanged by the new key. */
    @Test
    fun clearingByAgeTakesEverySourceWithIt() {
        listOf(android, manual, kalman).forEach { source ->
            db.bearingDao().insertBearing(bearing(1_000, source, 1f))
            db.bearingDao().insertBearing(bearing(9_000, source, 2f))
            db.locationDao().insertLocation(location(1_000, source, 50.0))
            db.locationDao().insertLocation(location(9_000, source, 51.0))
        }

        db.bearingDao().clearBearingsOlderThan(5_000)
        db.locationDao().clearLocationsOlderThan(5_000)

        assertEquals(3, db.bearingDao().getAllBearings().size)
        assertEquals(3, db.locationDao().getAllLocations().size)
        assertTrue(db.bearingDao().getAllBearings().all { it.timestamp == 9_000L })
        assertTrue(db.locationDao().getAllLocations().all { it.timestamp == 9_000L })
    }
}

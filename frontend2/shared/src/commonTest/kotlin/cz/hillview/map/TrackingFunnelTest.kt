package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The write funnel: state + election + table row in ONE call, which is what
 * keeps a user-set value from meaning one thing in the state and another in
 * the tracking table. Kotlin twin of `frontend/src/lib/mapState.test.ts` —
 * change one, change both (and `is_sensor_bearing_source` in Rust).
 */
class TrackingFunnelTest {

    private class RecordingSink : TrackingSink {
        val bearingElections = mutableListOf<String>()
        val locationElections = mutableListOf<String>()
        val bearingRows = mutableListOf<Triple<Double, String, String>>()
        val locationRows = mutableListOf<Triple<Double, Double, String>>()

        override fun electBearingSource(source: String) { bearingElections += source }
        override fun electLocationSource(source: String) { locationElections += source }
        override fun writeBearingRow(
            bearing: Double, source: String, detail: String, accuracyLevel: Int?, now: Long,
        ) { bearingRows += Triple(bearing, source, detail) }
        override fun writeLocationRow(
            latitude: Double, longitude: Double, source: String, detail: String, now: Long,
        ) { locationRows += Triple(latitude, longitude, source) }
    }

    // --- the vocabulary (ports of toTableSource / kotlinOwnsSource) ---

    @Test
    fun theCompassCollapsesToAndroidKeepingItsFineNameAsDetail() {
        val t = toTableSource("android-compass-true")
        assertEquals("android", t.source)
        assertEquals("android-compass-true", t.detail, "the fine name is provenance, not identity")
    }

    @Test
    fun carModeIsItsOwnElectableSource() {
        assertEquals("gps-kalman", toTableSource("gps-kalman").source)
    }

    @Test
    fun everyUserSetSourceCollapsesToManual() {
        // These are the app's own fine sources; all of them are the user
        // placing a bearing, so all of them elect as `manual`.
        for (s in listOf("map", "arrow_drag", "url", "featured", "photo_navigation")) {
            assertEquals("manual", toTableSource(s).source, s)
            assertEquals(s, toTableSource(s).detail, s)
        }
    }

    @Test
    fun theEngineOwnsItsOwnStreamsAndNothingElse() {
        assertTrue(engineOwnsSource("android"))
        assertTrue(engineOwnsSource("android-compass-true"))
        assertTrue(engineOwnsSource("gps-kalman"))
        assertTrue(!engineOwnsSource("map"))
        assertTrue(!engineOwnsSource("arrow_drag"))
        // Prefix, not substring: a future name merely MENTIONING a sensor
        // must not be swept in (the Rust twin had exactly this bug).
        assertTrue(!engineOwnsSource("manual-rotation-handle"))
    }

    // --- the funnel itself ---

    @Test
    fun aUserSetBearingIsWrittenAsARowInTheSameCall() {
        val sink = RecordingSink()
        val state = MapStateHolder(sink = sink)

        state.updateBearing(90.0, source = "arrow_drag", now = 1)

        assertEquals(90.0, state.bearing.value.bearing, 0.001)
        assertEquals(listOf("manual"), sink.bearingElections)
        assertEquals(1, sink.bearingRows.size, "the row is a side effect of the state write")
        assertEquals("manual" to "arrow_drag", sink.bearingRows[0].second to sink.bearingRows[0].third)
    }

    @Test
    fun anEngineOwnedBearingElectsButIsNotEchoed() {
        // The engine already wrote this sample at sensor rate, against its
        // own timestamp; echoing would file a second row for one sample.
        val sink = RecordingSink()
        val state = MapStateHolder(sink = sink)

        state.updateBearing(12.0, source = "android-compass-true", now = 1)

        assertEquals(listOf("android"), sink.bearingElections)
        assertTrue(sink.bearingRows.isEmpty(), "no echo of a stream the engine records")
    }

    @Test
    fun theElectionIsPushedOnChangeOnly() {
        // updateBearing runs at sensor rate; the election does not.
        val sink = RecordingSink()
        val state = MapStateHolder(sink = sink)

        state.updateBearing(10.0, source = "android-compass-true", now = 1)
        state.updateBearing(11.0, source = "android-compass-true", now = 2)
        state.updateBearing(12.0, source = "map", now = 3)
        state.updateBearing(13.0, source = "arrow_drag", now = 4)

        assertEquals(listOf("android", "manual"), sink.bearingElections)
    }

    @Test
    fun aPanWritesItsOwnPositionRowAndElectsManual() {
        // "A manual pan IS the act of electing the map position, so the row
        // carries the election with it" — it cannot be stamped with the era
        // it is ending.
        val sink = RecordingSink()
        val state = MapStateHolder(sink = sink)

        state.updateSpatial(latitude = 50.1, longitude = 14.4, source = "map", now = 1)

        assertEquals(listOf("manual"), sink.locationElections)
        assertEquals(1, sink.locationRows.size)
        assertEquals(50.1, sink.locationRows[0].first, 0.0001)
        assertEquals("manual", sink.locationRows[0].third)
    }

    @Test
    fun aFixMovingTheMapIsNotEchoedBecauseTheEngineRecordedIt() {
        val sink = RecordingSink()
        val state = MapStateHolder(sink = sink)

        state.updateSpatial(latitude = 50.1, longitude = 14.4, source = "gps", now = 1)

        assertEquals(listOf("android"), sink.locationElections)
        assertTrue(sink.locationRows.isEmpty(), "the fix stream is the engine's to record")
    }

    @Test
    fun aDedupedSpatialUpdateWritesNothingAtAll() {
        // The ping-pong break must not leak rows: same values twice is one row.
        val sink = RecordingSink()
        val state = MapStateHolder(sink = sink)

        state.updateSpatial(latitude = 50.1, longitude = 14.4, source = "map", now = 1)
        state.updateSpatial(latitude = 50.1, longitude = 14.4, source = "map", now = 2)

        assertEquals(1, sink.locationRows.size)
    }
}

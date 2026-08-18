package cz.hillview

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import cz.hillview.map.LocationTracking
import cz.hillview.map.MapSession
import cz.hillview.map.MapStateHolder
import cz.hillview.plugin.GeoTrackingDatabase
import kotlin.math.abs
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.GlobalContext

/**
 * The election, end to end: what the user elected has to be what the photo is
 * stamped with AND what the tracking tables say was primary at that instant.
 *
 * The claims are in docs/frontend2-status.md (items 0d/0e) and
 * docs/tauri-capture-ui-contract.md; the test debt they left is
 * docs/geo-election-test-todo.md items 3, 4 and 7. The Tauri app has the
 * equivalent as an appium spec (background-location-tracking.test.ts) — this
 * side's publisher is a different implementation and had nothing.
 */
@RunWith(AndroidJUnit4::class)
class GeoElectionBehaviourTest {

    @get:Rule(order = 0)
    val permissions: GrantPermissionRule = GrantPermissionRule.grant(
        android.Manifest.permission.ACCESS_FINE_LOCATION,
        android.Manifest.permission.ACCESS_COARSE_LOCATION,
        android.Manifest.permission.CAMERA,
    )

    @get:Rule(order = 1)
    val compose = createAndroidComposeRule<MainActivity>()

    private val gps = MockGps()

    private val session: MapSession get() = GlobalContext.get().get()
    private val mapState: MapStateHolder get() = GlobalContext.get().get()

    /** The vocabulary a source name may take — small and EXACT, by design. */
    private val vocabulary = setOf("android", "manual", "gps-kalman")

    @Before
    fun maskTheRealGps() {
        // No fix arrives until this test says so — the gate, and everything
        // downstream of it, is otherwise at the emulator's mercy.
        gps.install()
    }

    @After
    fun withdrawEverythingThisTestElected() {
        gps.remove()
        // Both routes are session-long; leaving one standing would arrange
        // the next test class behind its back.
        session.setMapPositionWithoutFix(false)
        session.setLocationTracking(LocationTracking.Off)
    }

    /**
     * Move the map, the way a pan does: through the live holder both panes
     * read. osmdroid echoes its own quantized centre back, so the wait is on
     * "close enough", and every later assertion reads the holder rather than
     * assuming the number went in untouched.
     */
    private fun panTo(latitude: Double, longitude: Double) {
        compose.runOnUiThread {
            mapState.updateSpatial(
                latitude = latitude,
                longitude = longitude,
                now = System.currentTimeMillis(),
            )
        }
        compose.waitUntil(10_000) {
            abs(mapState.spatial.value.latitude - latitude) < 1e-3 &&
                abs(mapState.spatial.value.longitude - longitude) < 1e-3
        }
        compose.waitForIdle()
    }

    /** The coordinates the capture pane prints on the hatch's own button. */
    private fun hatchLabelPosition(): Pair<Double, Double>? {
        val node = compose.onAllNodesWithTag("capture-manual-location")
            .fetchSemanticsNodes().firstOrNull() ?: return null
        val text = node.config.getOrNull(SemanticsProperties.Text)
            ?.joinToString(" ") { it.text } ?: return null
        val match = Regex("""\(([-\d.]+), ([-\d.]+)\)""").find(text) ?: return null
        return match.groupValues[1].toDouble() to match.groupValues[2].toDouble()
    }

    /**
     * Item 0e, fixed 2026-08-08 and unguarded until now: the stamp position
     * was read ONCE at the electing moment, so claiming at A, panning to B and
     * shooting stamped A — while the tracking table, which does follow pans,
     * recorded B. The photo and the log disagreed about where the user said
     * they were.
     */
    @Test
    fun aClaimStampsWhereTheMapIsNowNotWhereItWasClaimed() {
        session.claimManualPosition()
        compose.openCaptureAndAwaitCamera()

        val claimedAt = mapState.spatial.value
        panTo(claimedAt.latitude + 0.05, claimedAt.longitude + 0.05)
        val atShutter = mapState.spatial.value

        val photo = compose.captureOnePhoto()
        compose.dismissAutoUploadPromptIfShown()

        assertEquals(atShutter.latitude, photo.latitude, 1e-3)
        assertEquals(atShutter.longitude, photo.longitude, 1e-3)
        // Belt and braces: the failure mode is stamping the OLD centre, and
        // 0.05° is far enough that the tolerance above cannot hide it.
        assertTrue(
            "the stamp followed the claim's original position, not the map",
            abs(photo.latitude - claimedAt.latitude) > 0.01,
        )
    }

    /**
     * Item 7 / 0d: the no-fix hatch sets the same flag the pill does, so the
     * position it captures at must follow the map exactly the same way — and
     * the button says which position that is, so the label has to move too.
     */
    @Test
    fun theNoFixHatchFollowsTheMapAsWell() {
        compose.openCaptureAndAwaitCamera()
        // A fix injected by another test lingers in the fused cache; the gate
        // shuts again on its own once it ages past FIX_FRESH_MS, and the
        // offer is only made while it is shut.
        compose.waitUntil(30_000) {
            compose.onAllNodesWithTag("capture-use-map-position")
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.liftGateToMapPosition()

        val before = mapState.spatial.value
        panTo(before.latitude + 0.05, before.longitude + 0.05)
        val atShutter = mapState.spatial.value

        compose.waitUntil(10_000) {
            hatchLabelPosition()?.let { abs(it.first - atShutter.latitude) < 1e-3 } == true
        }
        val labelled = hatchLabelPosition()!!
        assertEquals(atShutter.longitude, labelled.second, 1e-3)

        val photo = compose.captureOnePhoto()
        compose.dismissAutoUploadPromptIfShown()
        assertEquals(atShutter.latitude, photo.latitude, 1e-3)
        assertEquals(atShutter.longitude, photo.longitude, 1e-3)
    }

    /**
     * Item 4: the election has to reach the CSVs, not just the capture. A
     * `manual` row at the map centre (electing a source with no rows in it
     * would name a stream nobody can look at afterwards), and — the part that
     * makes post-hoc re-election possible — the fixes taken MEANWHILE, which
     * are honest `android` rows carrying an election of `manual`.
     */
    @Test
    fun theElectionReachesTheTables() {
        session.claimManualPosition()
        compose.openCaptureAndAwaitCamera()
        val claimedAt = System.currentTimeMillis()

        val start = mapState.spatial.value
        panTo(start.latitude + 0.05, start.longitude + 0.05)
        val centre = mapState.spatial.value

        // A fix, deliberately somewhere else: it is not what the app is
        // using, and the row has to be able to say so for itself.
        gps.inject(centre.latitude - 0.2, centre.longitude - 0.2)

        val db = GeoTrackingDatabase.getDatabase(Behaviour.context)
        compose.waitUntil(30_000) {
            val androidId = db.sourceDao().getSourceIdByName("android")
            androidId != null && db.locationDao().getAllLocations()
                .any { it.sourceId == androidId && it.timestamp >= claimedAt }
        }

        val previous = Behaviour.newestGeoDump("locations")?.name
        cz.hillview.settings.exportGeoTrackingNow()
        compose.waitUntil(20_000) {
            Behaviour.newestGeoDump("locations")?.name?.takeIf { it != previous } != null
        }
        // writeText is not atomic — let the export finish before parsing.
        android.os.SystemClock.sleep(500)
        val rows = Behaviour.geoDumpRows(Behaviour.newestGeoDump("locations")!!)
        assertTrue("the export is empty", rows.isNotEmpty())

        val sources = rows.mapNotNull { it["source"] }.toSet()
        assertTrue(
            "source is an exact, elect-able vocabulary now — got $sources",
            sources.all { it in vocabulary },
        )

        val atCentre = rows.filter {
            it["source"] == "manual" &&
                abs((it["latitude"] ?: "0").toDouble() - centre.latitude) < 1e-3
        }
        assertTrue("the elected map position was never written as a row", atCentre.isNotEmpty())
        assertEquals("map", atCentre.last()["detail"])
        assertEquals("manual", atCentre.last()["elected"])

        val fixes = rows.filter {
            it["source"] == "android" && (it["timestamp"] ?: "0").toLong() >= claimedAt
        }
        assertTrue("no fix was recorded while the claim stood", fixes.isNotEmpty())
        assertTrue(
            "a fix taken while the map position was elected must record THAT — " +
                "without it the row cannot be dropped from the lookup, or re-elected later",
            fixes.all { it["elected"] == "manual" },
        )

        // The bearing side of the same dump: the fusion mode used to be part
        // of the source name ("android UPRIGHT_ROTATION_VECTOR (EMA
        // smoothed)"), which is exactly what the detail column took over.
        val bearings = Behaviour.newestGeoDump("orientations")
            ?.let { Behaviour.geoDumpRows(it) } ?: emptyList()
        if (bearings.isNotEmpty()) {
            val bearingSources = bearings.mapNotNull { it["source"] }.toSet()
            assertTrue(
                "bearing sources must be elect-able names too — got $bearingSources",
                bearingSources.all { it in vocabulary },
            )
            assertTrue(
                "the fusion mode belongs in detail, not in the source name",
                bearings.any { !it["detail"].isNullOrEmpty() },
            )
        }
    }
}

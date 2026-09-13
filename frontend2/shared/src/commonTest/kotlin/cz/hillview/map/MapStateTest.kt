package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The map state rules, ported from the Tauri app's mapState.ts and pinned
 * here because they are subtle and load-bearing — see
 * docs/tauri-map-ui-contract.md. Several of these encode behaviour that
 * looks like a bug until you know why it is there.
 */
class MapStateTest {

    /**
     * A hand-set bearing is reached for when the sensors are of no use, so
     * nothing measured may travel with it — not the pitch, not the magnetic
     * heading, not the accuracy of a reading that is no longer describing
     * anything. Sources write what they measure and null for the rest.
     */
    @Test
    fun aHandSetBearingCarriesNoMeasurements() {
        val map = MapStateHolder()
        map.updateBearing(
            bearing = 90.0,
            source = "android-compass-true",
            accuracyLevel = 3,
            magneticDeg = 88.0,
            pitch = 12.0,
            now = 1_000L,
        )

        // The arrow drag: an outright hand-set value.
        map.updateBearing(bearing = 200.0, source = "arrow_drag", now = 2_000L)
        assertNull(map.bearing.value.pitch)
        assertNull(map.bearing.value.magneticDeg)

        // Car mode's mount offset: a hand-applied TURN, which used to keep
        // the previous writer's measurements under its own source name.
        map.updateBearing(
            bearing = 90.0,
            source = "android-compass-true",
            accuracyLevel = 3,
            magneticDeg = 88.0,
            pitch = 12.0,
            now = 3_000L,
        )
        map.updateBearingByDiff(15.0, source = "gps-kalman", now = 4_000L)
        assertEquals(105.0, map.bearing.value.bearing)
        assertNull(map.bearing.value.pitch)
        assertNull(map.bearing.value.magneticDeg)
        // Accuracy is the exception, and deliberately: the original carries
        // it across a diff (mapState.ts:513), so bearingByDiffPreserves-
        // SourcePhotoAndAccuracy still holds. Faithfulness beats tidiness.
        assertEquals(3, map.bearing.value.accuracyLevel)
    }

    @Test
    fun spatialUpdatesDedupIgnoringTheTimestamp() {
        val state = MapStateHolder()
        assertTrue(state.updateSpatial(latitude = 50.0, longitude = 14.0, now = 1_000))
        val first = state.spatial.value
        assertEquals(1_000, first.ts)

        // Same values again: this is the terminal break of the
        // map -> store -> map loop, so it must NOT write, and must not
        // advance the timestamp either.
        assertFalse(state.updateSpatial(latitude = 50.0, longitude = 14.0, now = 2_000))
        assertEquals(first, state.spatial.value)
    }

    @Test
    fun spatialWritesWhenAnythingButTheTimestampChanges() {
        val state = MapStateHolder()
        state.updateSpatial(latitude = 50.0, longitude = 14.0, now = 1_000)
        assertTrue(state.updateSpatial(latitude = 50.0, longitude = 14.0, zoom = 12.0, now = 2_000))
        assertEquals(12.0, state.spatial.value.zoom)
        assertEquals(2_000, state.spatial.value.ts)
    }

    @Test
    fun spatialCanUpdateWithoutClaimingUserIntent() {
        // ts marks *intentional* navigation; a blank first run leaves it
        // null so automatic navigation may still steer.
        val state = MapStateHolder()
        assertNull(state.spatial.value.ts)
        state.updateSpatial(latitude = 51.0, setTimestamp = false, now = 5_000)
        assertNull(state.spatial.value.ts)
    }

    @Test
    fun bearingNeverDedups() {
        // Unlike spatial state: every call notifies, because consumers
        // (marker recolouring) depend on the tick.
        val state = MapStateHolder()
        state.updateBearing(90.0, now = 1_000)
        state.updateBearing(90.0, now = 2_000)
        assertEquals(2_000, state.bearing.value.ts)
    }

    @Test
    fun bearingClearsPhotoAndAccuracyWhenNotGiven() {
        // This is how a compass tick drops a photo selection — surprising,
        // but the original relies on it.
        val state = MapStateHolder()
        state.updateBearing(10.0, source = "marker_click", photoUid = "abc", accuracyLevel = 3, now = 1)
        assertEquals("abc", state.bearing.value.photoUid)

        state.updateBearing(20.0, source = "android-compass-true", now = 2)
        assertNull(state.bearing.value.photoUid)
        assertNull(state.bearing.value.accuracyLevel)
    }

    @Test
    fun bearingByDiffPreservesSourcePhotoAndAccuracy() {
        val state = MapStateHolder()
        state.updateBearing(10.0, source = "marker_click", photoUid = "abc", accuracyLevel = 2, now = 1)

        state.updateBearingByDiff(15.0, now = 2)

        val bearing = state.bearing.value
        assertEquals(25.0, bearing.bearing)
        assertEquals("marker_click", bearing.source)
        assertEquals("abc", bearing.photoUid)
        assertEquals(2, bearing.accuracyLevel)
    }

    @Test
    fun bearingByDiffWrapsAroundNorth() {
        val state = MapStateHolder()
        state.updateBearing(350.0, now = 1)
        state.updateBearingByDiff(20.0, now = 2)
        assertEquals(10.0, state.bearing.value.bearing)

        state.updateBearingByDiff(-20.0, now = 3)
        assertEquals(350.0, state.bearing.value.bearing)
    }

    @Test
    fun rotatingTheMapIsASpatialChangeAndDedupsLikeOne() {
        // A two-finger turn has to reach the store, or the map snaps back
        // north-up the next time anything else updates.
        val state = MapStateHolder()
        assertEquals(0.0, state.spatial.value.orientation)
        assertTrue(state.updateSpatial(orientation = 42.0, now = 1_000))
        assertEquals(42.0, state.spatial.value.orientation)
        assertFalse(state.updateSpatial(orientation = 42.0, now = 2_000))
    }

    @Test
    fun rotatingDoesNotDisturbTheBearing() {
        // Which way the map is held and which way the user looks are
        // different questions; the arrow answers the second one.
        val state = MapStateHolder()
        state.updateBearing(141.0, source = "arrow_drag", now = 1)
        state.updateSpatial(orientation = 90.0, now = 2)
        assertEquals(141.0, state.bearing.value.bearing)
        assertEquals("arrow_drag", state.bearing.value.source)
    }

    @Test
    fun defaultsMatchThePersistedTauriState() {
        // The Svelte store's defaults, which users see on a fresh install.
        val state = MapStateHolder()
        assertEquals(141.0, state.bearing.value.bearing)
        assertEquals(10.0, state.spatial.value.zoom)
        assertEquals(0.0, state.spatial.value.orientation)
        assertEquals(1000.0, state.spatial.value.range)
        assertNotNull(state.spatial.value.source)
    }
}

class BearingMathTest {

    @Test
    fun normalizeHandlesNegativeAndOverflow() {
        assertEquals(350.0, normalizeBearing(-10.0))
        assertEquals(10.0, normalizeBearing(370.0))
        assertEquals(0.0, normalizeBearing(360.0))
    }

    @Test
    fun angularDistanceTakesTheShortWayRoundNorth() {
        assertEquals(20.0, angularDistance(350.0, 10.0))
        assertEquals(-20.0, angularDistance(10.0, 350.0))
        assertEquals(180.0, angularDistance(0.0, 180.0))
        assertEquals(0.0, angularDistance(42.0, 42.0))
    }

    @Test
    fun absBearingDiffIsSymmetricAndWraps() {
        assertEquals(20.0, absBearingDiff(350.0, 10.0))
        assertEquals(20.0, absBearingDiff(10.0, 350.0))
        assertEquals(180.0, absBearingDiff(0.0, 180.0))
        assertEquals(0.0, absBearingDiff(90.0, 90.0))
    }
}

/** The bucket table in docs/tauri-map-ui-contract.md, used as the oracle. */
class BearingAgreementAlphaTest {

    @Test
    fun alignedPhotosAreFullyOpaque() {
        assertEquals(1f, bearingAgreementAlpha(0.0))
        assertEquals(1f, bearingAgreementAlpha(14.0))
    }

    @Test
    fun alphaFallsInTheOriginalsBuckets() {
        // step 1 still yields 1/1; the ramp only starts biting at step 2.
        assertEquals(1f, bearingAgreementAlpha(30.0))
        assertEquals(0.5f, bearingAgreementAlpha(57.0))
        assertEquals(1f / 3f, bearingAgreementAlpha(85.0))
        assertEquals(0.25f, bearingAgreementAlpha(114.0))
    }

    @Test
    fun oppositeFacingPhotosAreFaintestButStillVisible() {
        val alpha = bearingAgreementAlpha(180.0)
        assertTrue(alpha > 0f, "a photo facing away must not vanish entirely")
        assertTrue(alpha <= 1f / 5f, "but it must be clearly fainter than an aligned one")
    }
}

class MarkerClusteringTest {

    private data class P(val id: String, val x: Float, val y: Float)

    private fun cluster(items: List<P>, radius: Float) =
        clusterByProximity(items, radius, { it.x }, { it.y })

    @Test
    fun photosFromOneViewpointBecomeOneGroup() {
        val photos = listOf(
            P("a", 100f, 100f),
            P("b", 103f, 98f),
            P("c", 99f, 104f),
        )
        val groups = cluster(photos, radius = 20f)
        assertEquals(1, groups.size)
        assertEquals(3, groups.first().size)
    }

    @Test
    fun photosFurtherApartThanTheThresholdStaySeparate() {
        val photos = listOf(P("a", 0f, 0f), P("b", 50f, 0f))
        assertEquals(2, cluster(photos, radius = 20f).size)
    }

    @Test
    fun theThresholdIsInclusive() {
        val photos = listOf(P("a", 0f, 0f), P("b", 20f, 0f))
        assertEquals(1, cluster(photos, radius = 20f).size)
    }

    @Test
    fun groupsDoNotChainAlongALineOfMarkers() {
        // Each is within 20 of its neighbour but the line spans 40, so a
        // transitive closure would swallow the lot. Seed-based grouping
        // keeps a distant marker out.
        val photos = listOf(P("a", 0f, 0f), P("b", 15f, 0f), P("c", 40f, 0f))
        val groups = cluster(photos, radius = 20f)
        assertEquals(2, groups.size)
        assertEquals(listOf("a", "b"), groups[0].map { it.id })
        assertEquals(listOf("c"), groups[1].map { it.id })
    }

    @Test
    fun everyPhotoEndsUpInExactlyOneGroup() {
        val photos = (0 until 25).map { P("p$it", (it % 5) * 8f, (it / 5) * 8f) }
        val groups = cluster(photos, radius = 12f)
        assertEquals(photos.size, groups.sumOf { it.size })
        assertEquals(photos.map { it.id }.toSet(), groups.flatten().map { it.id }.toSet())
    }

    @Test
    fun emptyInputIsHandled() {
        assertEquals(0, cluster(emptyList(), radius = 20f).size)
    }
}

/**
 * Persistence, because "the bearing must be byte-identical after the app is
 * backgrounded" is an assertion in the Appium suite and the port failed it —
 * the state lived in `remember` and died with the composition.
 */
class MapStatePersistenceTest {

    @Test
    fun aRestoredBearingComesBackExactly() {
        val store = InMemoryMapStateStore()
        val before = MapStateHolder()
        before.updateBearing(137.5, source = "arrow_drag", now = 1_000)
        store.save(before.spatial.value, before.bearing.value)

        val (spatial, bearing) = store.load()!!
        val after = MapStateHolder(spatial, bearing)

        assertEquals(137.5, after.bearing.value.bearing)
        assertEquals("arrow_drag", after.bearing.value.source)
    }

    @Test
    fun aRestoredPositionCountsAsPriorIntent() {
        // ts is what stops automatic navigation from steering later, so it
        // has to survive too — otherwise a restored session looks like a
        // blank first run.
        val store = InMemoryMapStateStore()
        val before = MapStateHolder()
        before.updateSpatial(latitude = 50.115, longitude = 14.501, now = 9_000)
        store.save(before.spatial.value, before.bearing.value)

        val restored = MapStateHolder(store.load()!!.first, store.load()!!.second)

        assertEquals(9_000, restored.spatial.value.ts)
        assertEquals(50.115, restored.spatial.value.latitude)
    }

    /**
     * Range is a read-back of what the 70 dp circle means on the ground —
     * a measurement, not the user placing themselves. It must change the
     * value the viewer's ring culls against and NOTHING else: no election,
     * no tracking row, no intentional-move timestamp.
     */
    @Test
    fun theRangeReadBackElectsNothingAndWritesNoRow() {
        val rows = mutableListOf<String>()
        val sink = object : TrackingSink {
            override fun writeLocationRow(latitude: Double, longitude: Double, source: String, detail: String, now: Long) { rows += "loc" }
            override fun writeBearingRow(bearing: Double, source: String, detail: String, accuracyLevel: Int?, now: Long) { rows += "bear" }
            override fun electBearingSource(source: String) { rows += "electB" }
            override fun electLocationSource(source: String) { rows += "electL" }
        }
        val holder = MapStateHolder(sink = sink)
        val tsBefore = holder.spatial.value.ts

        holder.updateRange(240.0)

        assertEquals(240.0, holder.spatial.value.range)
        assertEquals(tsBefore, holder.spatial.value.ts, "a measurement is not an intentional move")
        assertEquals(emptyList(), rows, "a measurement elects nothing and records nothing")

        // Unchanged and nonsense values are dropped rather than notified.
        holder.updateRange(240.0)
        holder.updateRange(-5.0)
        assertEquals(240.0, holder.spatial.value.range)
    }

    @Test
    fun anEmptyStoreLeavesTheDefaults() {
        val store = InMemoryMapStateStore()
        assertNull(store.load())
        val fresh = MapStateHolder()
        assertEquals(141.0, fresh.bearing.value.bearing)
        assertNull(fresh.spatial.value.ts)
    }
}
/**
 * Tapping a marker. The port shipped with the hit list never populated, so
 * taps silently did nothing on a device while every other test passed —
 * hence these, which pin the choice rule rather than the plumbing.
 */
class MarkerAtTapTest {

    private data class M(val id: String, val x: Float, val y: Float, val bearing: Double? = null)

    private fun tap(markers: List<M>, x: Float, y: Float, radius: Float = 24f, view: Double = 90.0) =
        markerAtTap(markers, x, y, radius, view, { it.x }, { it.y }, { it.id }, { it.bearing })

    @Test
    fun tapsPickTheNearestMarkerInReach() {
        val markers = listOf(M("far", 100f, 100f), M("near", 12f, 0f))
        assertEquals("near", tap(markers, 0f, 0f)?.id)
    }

    @Test
    fun tapsOnEmptyMapSelectNothing() {
        assertNull(tap(listOf(M("a", 500f, 500f)), 0f, 0f))
        assertNull(tap(emptyList(), 0f, 0f))
    }

    @Test
    fun theRadiusIsInclusive() {
        assertEquals("edge", tap(listOf(M("edge", 24f, 0f)), 0f, 0f)?.id)
        assertNull(tap(listOf(M("just-out", 24.5f, 0f)), 0f, 0f))
    }

    @Test
    fun tappingARoseYieldsThePhotoFacingWhereWeLook() {
        // A rose draws every member at one point, so distance cannot decide
        // and the view bearing has to.
        val rose = listOf(
            M("behind", 50f, 50f, bearing = 270.0),
            M("ahead", 50f, 50f, bearing = 95.0),
            M("sideways", 50f, 50f, bearing = 180.0),
        )
        assertEquals("ahead", tap(rose, 50f, 50f, view = 90.0)?.id)
        assertEquals("behind", tap(rose, 50f, 50f, view = 265.0)?.id)
    }

    @Test
    fun aStackedPhotoWithNoBearingLosesToOneThatHasIt() {
        val rose = listOf(M("unknown", 0f, 0f, bearing = null), M("known", 0f, 0f, bearing = 300.0))
        assertEquals("known", tap(rose, 0f, 0f, view = 90.0)?.id)
    }

    @Test
    fun aFullyTiedRoseStillPicksTheSamePhotoEveryTime() {
        val rose = listOf(M("b", 0f, 0f, bearing = 90.0), M("a", 0f, 0f, bearing = 90.0))
        assertEquals("a", tap(rose, 0f, 0f)?.id)
        assertEquals("a", tap(rose.reversed(), 0f, 0f)?.id)
    }
}

/**
 * The manual-position claim (user-raised, refined): panning is
 * exploration; only the accepted claim changes what captures record, and
 * it survives exactly the transitions a deliberate choice should.
 */
class MapSessionTest {

    @Test
    fun claimingParksTrackingAndSurvivesEnteringCapture() {
        val session = MapSession()
        session.setLocationTracking(LocationTracking.Active)
        session.claimManualPosition()
        assertEquals(LocationTracking.Background, session.locationTracking.value)
        assertTrue(session.manualPositionClaimed.value)

        // The clean-ACTIVE re-arm kills stale background flags; a gated
        // claim cannot be stale, so it must survive.
        session.onEnterRecording()
        assertEquals(LocationTracking.Background, session.locationTracking.value)
        assertTrue(session.manualPositionClaimed.value)
    }

    @Test
    fun goingActiveWithdrawsTheClaim() {
        val session = MapSession()
        session.claimManualPosition()
        session.setLocationTracking(LocationTracking.Active)
        assertFalse(session.manualPositionClaimed.value)
    }

    @Test
    fun turningTrackingOffWithdrawsTheClaimToo() {
        val session = MapSession()
        session.claimManualPosition()
        session.setLocationTracking(LocationTracking.Off)
        assertFalse(session.manualPositionClaimed.value)
    }

    @Test
    fun eitherRouteElectsTheMapPosition() {
        val session = MapSession()
        assertFalse(session.manualPositionElected.value)

        session.claimManualPosition()
        assertTrue(session.manualPositionElected.value)
        session.setLocationTracking(LocationTracking.Active)
        assertFalse(session.manualPositionElected.value)
        // (The no-fix hatch used to reach the same election without the
        // gate; it is gone — with no fix the map centre is recorded with no
        // election needed. See theFixRecordIsKeptWhateverTheMapDoes.)
    }

    /**
     * The fix has its own record (docs/one-state.md, "The position side"):
     * a fix arriving while the map is parked elsewhere is kept, and a pan
     * does not erase it. Before this the two overwrote one spatial state and
     * the capture pane kept a private copy to compensate.
     */
    @Test
    fun theFixRecordIsKeptWhateverTheMapDoes() {
        val state = MapStateHolder()
        assertEquals(null, state.lastFix.value)
        val fix = FixState(50.0, 14.0, atMs = 1_000L, elapsedRealtimeNanos = 1_000_000_000L)
        state.updateFix(fix)
        assertEquals(fix, state.lastFix.value)
        // A pan moves the map and leaves the fix where it was.
        state.updateSpatial(latitude = 51.0, longitude = 15.0, source = "map", now = 2_000L)
        assertEquals(fix, state.lastFix.value)
        assertEquals(51.0, state.spatial.value.latitude)
        // And the record is not the map: following writes both, but through
        // two funnels, so a fix-moved map still has a fix to show for it.
        val later = fix.copy(latitude = 50.5, atMs = 3_000L, elapsedRealtimeNanos = 3_000_000_000L)
        state.updateFix(later)
        assertEquals(later, state.lastFix.value)
        assertEquals(51.0, state.spatial.value.latitude)
    }

    @Test
    fun enteringCaptureWithoutAClaimStillArmsCleanActive() {
        // The stuck-half-blue regression stays guarded for everyone who
        // did not deliberately claim a position.
        val session = MapSession()
        session.setLocationTracking(LocationTracking.Background)
        session.onEnterRecording()
        assertEquals(LocationTracking.Active, session.locationTracking.value)
    }
}

/**
 * The north badge's one question, asked once. The badge appears on this and
 * shows this, so a map that is visibly turned can never fail to say by how
 * much (user: "map rotation keeps fooling me").
 */
class OffNorthTest {

    @Test
    fun northIsZeroFromEitherSide() {
        assertEquals(0.0, offNorthDeg(0.0))
        assertEquals(0.0, offNorthDeg(360.0))
        assertEquals(0.0, offNorthDeg(-720.0))
    }

    @Test
    fun aSmallTurnEitherWayIsASmallNumber() {
        // 350 and 10 are both ten degrees off; the badge must treat them the
        // same, which an unsigned 0..360 answer cannot.
        assertEquals(10.0, offNorthDeg(10.0))
        assertEquals(-10.0, offNorthDeg(350.0))
        assertEquals(-10.0, offNorthDeg(-10.0))
    }

    @Test
    fun theAnswerStaysInsideHalfATurn() {
        for (degrees in -1080..1080 step 7) {
            val off = offNorthDeg(degrees.toDouble())
            assertTrue(off > -180.0 && off <= 180.0, "$degrees gave $off")
        }
    }

    @Test
    fun theOppositeDirectionIsTheEdgeCase() {
        assertEquals(180.0, offNorthDeg(180.0))
        assertEquals(180.0, offNorthDeg(-180.0))
    }
}

/**
 * What the location button says, and the divergence that made it lie.
 *
 * The original castles the two position streams on the pan itself, so
 * "parked" and "the fix is demoted" are one event there. Here the castle
 * waits for the claim, which puts a whole state between them — and the
 * button, carrying the original's rule, went half-lit on the pan and
 * announced a demotion that had not happened (user, 2026-09-11).
 */
class FixRoleTest {

    @Test
    fun followingMeansTheFixIsWhatAPhotoRecords() {
        assertEquals(
            FixRole.Primary,
            fixRole(LocationTracking.Active, mapPositionElected = false),
        )
    }

    /**
     * The case that was wrong: panned away, prompt up, nothing claimed. The
     * map is parked, but a photo still records the FIX — so the button must
     * not say the fix has been demoted.
     */
    @Test
    fun exploringDoesNotDemoteTheFix() {
        assertEquals(
            FixRole.Primary,
            fixRole(LocationTracking.Background, mapPositionElected = false),
        )
    }

    @Test
    fun anAcceptedClaimIsWhatDemotesIt() {
        assertEquals(
            FixRole.Alternate,
            fixRole(LocationTracking.Background, mapPositionElected = true),
        )
    }

    /** No fixes at all outranks any election: there is nothing to elect. */
    @Test
    fun offIsOffWhicheverPositionIsElected() {
        assertEquals(FixRole.Off, fixRole(LocationTracking.Off, mapPositionElected = false))
        assertEquals(FixRole.Off, fixRole(LocationTracking.Off, mapPositionElected = true))
    }
}

package cz.hillview.capture

import cz.hillview.map.DeviceMotionSample
import cz.hillview.map.FixState
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The `fix`, `lens` and `motion` provenance objects — their wire shape, which
 * is a contract with the worker (each must be DECLARED in `BrowserMetadata` or
 * pydantic drops it silently) and with the API's typed projection, which
 * enumerates every inner key.
 *
 * `attitude` has its own file; the freshness rule they all share is tested
 * there. See docs/recon-capture-metadata.md.
 */
class ProvenanceObjectsTest {

    private val shutterAt = 1_700_000_000_000L

    private fun snap(
        fix: FixState? = null,
        lens: LensStamp? = null,
        motion: DeviceMotionSample? = null,
        imuWindow: ImuWindow? = null,
        locationSource: String? = "gps",
    ) = SensorSnapshot(
        capturedAtMs = shutterAt,
        fix = fix,
        lens = lens,
        motion = motion,
        imuWindow = imuWindow,
        locationSource = locationSource,
    )

    private fun fix() = FixState(
        latitude = 50.1, longitude = 14.4, altitude = 300.0, accuracyM = 4.2f,
        atMs = shutterAt, elapsedRealtimeNanos = 1L,
        altitudeAccuracyM = 8.5f, speedMps = 1.4f, speedAccuracyMps = 0.3f,
        courseDeg = 212.5f, courseAccuracyDeg = 15f, provider = "fused",
    )

    // --- fix: the error bars, and NEVER the position ---

    // --- capture_timing: what `captured_at` actually means ---

    /**
     * The one field that must never be absent. A timing object that omits
     * `captured_at_source` would leave exactly the ambiguity it exists to remove —
     * a reader could not tell whether `captured_at` is the press or the exposure.
     */
    @Test
    fun theTimingObjectAlwaysSaysWhatCapturedAtIs() {
        val json = captureTimingJson(
            snap().copy(captureTiming = CaptureTiming(capturedAtSource = "press")),
        )
        assertEquals("""{"captured_at_source":"press"}""", json)
    }

    @Test
    fun theTimingObjectCarriesBothIntervals() {
        val json = captureTimingJson(
            snap().copy(
                captureTiming = CaptureTiming(
                    capturedAtSource = "press",
                    pressToExposureMs = 376,
                    exposureToJpegMs = 342,
                    stillMode = "latency",
                ),
            ),
        )!!
        assertTrue("\"press_to_exposure_ms\":376" in json, json)
        assertTrue("\"exposure_to_jpeg_ms\":342" in json, json)
        assertTrue("\"still_mode\":\"latency\"" in json, json)
    }

    /**
     * A capture whose `onCaptureStarted` never fired knows neither interval. It must
     * still say what `captured_at` is rather than vanishing — "we do not know how far
     * the exposure was" and "we do not know what this timestamp means" are different
     * statements, and only the first one is true there.
     */
    @Test
    fun aCaptureWithNoExposureCallbackStillDeclaresItsSource() {
        val json = captureTimingJson(
            snap().copy(captureTiming = CaptureTiming(capturedAtSource = "press", stillMode = "quality")),
        )!!
        assertTrue("\"captured_at_source\":\"press\"" in json, json)
        assertFalse("press_to_exposure_ms" in json, json)
        assertFalse("exposure_to_jpeg_ms" in json, json)
    }

    /**
     * The exposure fields appear only when the capture actually MEASURED the exposure.
     * A reader must be able to tell "we know when this frame was exposed" from "we are
     * reporting the press and saying so", and `exposure_source` is that distinction.
     */
    @Test
    fun theExposureIsReportedOnlyWhenItWasMeasured() {
        val measured = captureTimingJson(
            snap().copy(
                captureTiming = CaptureTiming(
                    capturedAtSource = "press",
                    exposureElapsedNs = 387_671_398_000_000L,
                    exposureWallMs = 1_790_547_858_357L,
                    exposureSource = "sensor_timestamp",
                ),
            ),
        )!!
        assertTrue("\"exposure_elapsed_ns\":387671398000000" in measured, measured)
        assertTrue("\"exposure_wall_ms\":1790547858357" in measured, measured)
        assertTrue("\"exposure_source\":\"sensor_timestamp\"" in measured, measured)

        // The ordinary path: press only, and no exposure claimed anywhere.
        val unmeasured = captureTimingJson(
            snap().copy(
                captureTiming = CaptureTiming(capturedAtSource = "press", pressToExposureMs = 376),
            ),
        )!!
        assertFalse("exposure_elapsed_ns" in unmeasured, unmeasured)
        assertFalse("exposure_wall_ms" in unmeasured, unmeasured)
        assertFalse("exposure_source" in unmeasured, unmeasured)
    }

    /**
     * The reference instant every `age_ms` is measured against. Without it, looking the
     * attitude up AT the exposure and leaving the age measured from the press would
     * produce a NEGATIVE age — the sample being later than the button — which is how a
     * reader would discover the inconsistency instead of being told.
     */
    @Test
    fun agesAreMeasuredAgainstWhicheverInstantThePoseDescribes() {
        val exposureWall = shutterAt + 312
        val atExposure = snap().copy(
            captureTiming = CaptureTiming(
                capturedAtSource = "press",
                exposureWallMs = exposureWall,
                exposureSource = "sensor_timestamp",
                poseReferencedTo = "exposure",
            ),
        )
        assertEquals(exposureWall, atExposure.poseReferenceMs())

        // Exposure known but no sample near it: the pose is still the press-time one, so
        // the ages must stay measured from the press.
        val declined = snap().copy(
            captureTiming = CaptureTiming(
                capturedAtSource = "press",
                exposureWallMs = exposureWall,
                exposureSource = "sensor_timestamp",
                poseReferencedTo = "press",
            ),
        )
        assertEquals(shutterAt, declined.poseReferenceMs())

        // The ordinary path knows no exposure at all.
        assertEquals(shutterAt, snap().poseReferenceMs())
    }

    /**
     * The whole point, end to end through the serializer: a reading taken 6 ms AFTER the
     * exposure reports −6, not the 318 ms it would have shown measured from the press.
     *
     * The sign is deliberate and is the contract. Once the pose is looked up at the
     * exposure, `age_ms` is a SIGNED offset from the instant named by
     * `pose_referenced_to`, and it is negative whenever the nearest sample fell after the
     * shutter — which is about half the time, since the lookup accepts both sides on
     * purpose. Harmless to a staleness filter: a negative offset really is fresh.
     */
    @Test
    fun anAtExposureReadingReportsItsAgeFromTheExposure() {
        val exposureWall = shutterAt + 312
        val json = inertialProvenanceJson(
            snap(motion = DeviceMotionSample(gravity = listOf(0f, 0f, 9.81f), atMs = exposureWall + 6))
                .copy(
                    captureTiming = CaptureTiming(
                        capturedAtSource = "press",
                        exposureWallMs = exposureWall,
                        exposureSource = "sensor_timestamp",
                        poseReferencedTo = "exposure",
                    ),
                ),
        )!!
        assertTrue("\"age_ms\":-6" in json, json)
        assertFalse("\"age_ms\":-318" in json, json)
    }

    /**
     * The deferred IMU-window rewrite REBUILDS this object from a fresh snapshot, and if
     * the timing does not travel with it the ages silently revert to the press while the
     * motion sample was taken at the exposure.
     *
     * That is not hypothetical: it shipped, and every uploaded photo reported an inertial
     * age of almost exactly minus the press→exposure gap (−315 against +316, −399 against
     * +398) while two separate fixes failed to move it, because neither touched the
     * rebuild. This asserts the shape the rebuild constructs.
     */
    @Test
    fun aRebuiltInertialObjectStillMeasuresAgainstTheExposure() {
        val exposureWall = shutterAt + 316
        val timing = CaptureTiming(
            capturedAtSource = "press",
            pressToExposureMs = 316,
            exposureWallMs = exposureWall,
            exposureSource = "sensor_timestamp",
            poseReferencedTo = "exposure",
        )
        // Exactly what SharedStackUploadPipeline builds when the window closes: a bare
        // snapshot carrying the press, the point reading, the window — and the timing.
        val rebuilt = SensorSnapshot(
            capturedAtMs = shutterAt,
            captureTiming = timing,
            motion = DeviceMotionSample(gravity = listOf(0f, 0f, 9.81f), atMs = exposureWall + 4),
        )
        val json = inertialProvenanceJson(rebuilt)!!
        assertTrue("\"age_ms\":-4" in json, json)
        // The regression: -316 is the press-referenced answer, and it is what shipped.
        assertFalse("\"age_ms\":-316" in json, json)

        // Drop the timing, as the rebuild used to, and the bug comes straight back.
        val withoutTiming = rebuilt.copy(captureTiming = null)
        assertTrue("\"age_ms\":-320" in inertialProvenanceJson(withoutTiming)!!)
    }

    /** No timing recorded at all — an older row, or a path that does not set it. */
    @Test
    fun noTimingMeansNoObject() {
        assertNull(captureTimingJson(snap()))
    }

    @Test
    fun theFixObjectCarriesTheErrorBarsNothingElseHas() {
        val json = fixProvenanceJson(snap(fix = fix()))!!
        listOf(
            "\"altitude_accuracy_m\":8.5",
            "\"speed_mps\":1.4",
            "\"speed_accuracy_mps\":0.3",
            "\"course_deg\":212.5",
            "\"course_accuracy_deg\":15.0",
            "\"provider\":\"fused\"",
        ).forEach { assertTrue(it in json, "missing $it in $json") }
    }

    /**
     * The position is already four columns and four response fields. Repeating
     * it here would be exactly the duplication this object exists to avoid.
     */
    @Test
    fun theFixObjectNeverRepeatsThePosition() {
        val json = fixProvenanceJson(snap(fix = fix()))!!
        // The KEY SET, exactly — substring hunting gives false alarms here,
        // because `altitude_accuracy_m` legitimately contains `accuracy_m` and
        // the two mean different things (vertical bar vs the horizontal one
        // that is already a column).
        val keys = Regex("\"([a-z0-9_]+)\":").findAll(json).map { it.groupValues[1] }.toSet()
        assertEquals(
            setOf(
                "altitude_accuracy_m", "speed_mps", "speed_accuracy_mps",
                "course_deg", "course_accuracy_deg", "provider", "elected",
            ),
            keys,
        )
        // And none of the position's own values, whatever they are keyed as.
        listOf("50.1", "14.4", "300.0", "4.2").forEach {
            assertFalse(it in json, "$it leaked into $json")
        }
    }

    /**
     * Whether this fix is what the photo actually RECORDED. Without it a reader
     * cannot tell a quality report about the recorded position from one about a
     * position that lost the election to a hand-placed map centre.
     */
    @Test
    fun theFixObjectSaysWhetherItWonTheElection() {
        assertTrue("\"elected\":true" in fixProvenanceJson(snap(fix = fix()))!!)
        assertTrue(
            "\"elected\":false" in
                fixProvenanceJson(snap(fix = fix(), locationSource = "map"))!!,
        )
    }

    /** A fix with no error bars at all says nothing worth an object. */
    @Test
    fun aFixWithOnlyAnElectionFlagIsNull() {
        val bare = FixState(
            latitude = 50.1, longitude = 14.4, atMs = shutterAt, elapsedRealtimeNanos = 1L,
        )
        assertNull(fixProvenanceJson(snap(fix = bare)))
    }

    @Test
    fun noFixMeansNoObject() {
        assertNull(fixProvenanceJson(snap()))
    }

    // --- lens ---

    @Test
    fun theLensObjectCarriesTheCalibrationAndTheSettings() {
        val json = lensProvenanceJson(
            snap(
                lens = LensStamp(
                    focalLengthMm = 5.58f,
                    apertureFStop = 1.79f,
                    focusDistanceDiopters = 0f,
                    focusDistanceCalibration = "approximate",
                    focusInfinityRequested = true,
                    zoomRatio = 2f,
                    rollingShutterSkewNs = 33_000_000L,
                    intrinsics = listOf(1000f, 1000f, 960f, 540f, 0f),
                    distortion = listOf(0.1f, -0.2f, 0.01f, 0f, 0f),
                    cameraIntrinsics = listOf(999f, 999f, 961f, 541f, 0f),
                    sensorPhysicalSizeMm = listOf(5.6f, 4.2f),
                    sensorPixelArray = listOf(4000, 3000),
                    intrinsicsAvailable = true,
                ),
            ),
        )!!
        listOf(
            "\"focal_length_mm\":5.58",
            "\"focus_distance_diopters\":0.0",
            "\"focus_distance_calibration\":\"approximate\"",
            "\"focus_infinity_requested\":true",
            // The field that made every zoomed photo's intrinsics silently wrong.
            "\"zoom_ratio\":2.0",
            "\"rolling_shutter_skew_ns\":33000000",
            "\"intrinsics\":[1000.0,1000.0,960.0,540.0,0.0]",
            "\"camera_intrinsics\":[999.0,999.0,961.0,541.0,0.0]",
            "\"sensor_pixel_array\":[4000,3000]",
            "\"intrinsics_available\":true",
        ).forEach { assertTrue(it in json, "missing $it in $json") }
    }

    /**
     * A phone that publishes no factory calibration must SAY so. "This device
     * does not calibrate its lenses" and "this app version did not look" are
     * different claims about a photo, and only one is the phone's fault.
     */
    @Test
    fun anAbsentCalibrationIsRecordedAsAFact() {
        val json = lensProvenanceJson(
            snap(lens = LensStamp(intrinsicsAvailable = false, zoomRatio = 1f)),
        )!!
        assertTrue("\"intrinsics_available\":false" in json, json)
        assertFalse("camera_intrinsics" in json, json)
    }

    @Test
    fun noLensMeansNoObject() {
        assertNull(lensProvenanceJson(snap()))
    }

    // --- motion ---

    @Test
    fun theMotionObjectCarriesGravityAndTheBlurSignal() {
        val json = inertialProvenanceJson(
            snap(
                motion = DeviceMotionSample(
                    gravity = listOf(0f, 0f, 9.81f),
                    // 3-4-0 → magnitude exactly 5, so the arithmetic is checkable.
                    linearAcceleration = listOf(3f, 4f, 0f),
                    atMs = shutterAt - 40,
                ),
            ),
        )!!
        assertTrue("\"gravity\":[0.0,0.0,9.81]" in json, json)
        assertTrue("\"linear_acceleration\":[3.0,4.0,0.0]" in json, json)
        assertTrue("\"linear_acceleration_magnitude\":5.0" in json, json)
        assertTrue("\"age_ms\":40" in json, json)
    }

    /** Gravity alone is still worth recording — it is two rotation DOF. */
    @Test
    fun gravityWithoutLinearAccelerationStillTravels() {
        val json = inertialProvenanceJson(
            snap(motion = DeviceMotionSample(gravity = listOf(0f, 9.81f, 0f), atMs = shutterAt)),
        )!!
        assertTrue("gravity" in json, json)
        assertFalse("linear_acceleration" in json, json)
    }

    /** Neither sensor reported: an age on its own describes nothing. */
    @Test
    fun aMotionSampleWithNeitherVectorIsNull() {
        assertNull(inertialProvenanceJson(snap(motion = DeviceMotionSample(atMs = shutterAt))))
    }

    @Test
    fun noMotionMeansNoObject() {
        assertNull(inertialProvenanceJson(snap()))
    }

    // --- the IMU window: the cheap summary beside the payload ---

    private fun window() = ImuWindow(
        sampleCount = 104,
        startMs = shutterAt - 500,
        endMs = shutterAt + 500,
        accelPeakMps2 = 10.4,
        accelPeakDeviationMps2 = 0.6,
        gyroPeakRadS = 0.12,
        // Fewer than sampleCount: the neighbouring photo's window had already
        // stored the rest. See the dedup test below.
        storedCount = 61,
    )

    @Test
    fun theWindowSummaryCarriesItsBoundsAndItsPeaks() {
        val json = imuWindowJson(window())
        listOf(
            "\"sample_count\":104",
            // What span the summary covers. Not a lookup key: the samples
            // travel with the photo (Phase 5), and nothing looks an app photo
            // up in the tracking CSVs — those exist for external frames.
            "\"window_start_ms\":${shutterAt - 500}",
            "\"window_end_ms\":${shutterAt + 500}",
            "\"accel_peak_mps2\":10.4",
            "\"accel_peak_deviation_mps2\":0.6",
            "\"gyro_peak_rad_s\":0.12",
        ).forEach { assertTrue(it in json, "missing $it in $json") }
    }

    /**
     * `stored_count` is how a reader tells a window that ADDED 61 samples from
     * one that merely spans 104 — the on-device trim (`imuHighWaterMs`) means
     * consecutive interval shots tile the session instead of each carrying the
     * same samples over again. Without it on the wire, a server concatenating a
     * run cannot know whether it is about to count anything twice.
     */
    @Test
    fun theWindowDistinguishesWhatItSpannedFromWhatItStored() {
        val json = imuWindowJson(window())
        assertTrue("\"sample_count\":104" in json, json)
        assertTrue("\"stored_count\":61" in json, json)
    }

    /**
     * Zero stored is the NORMAL case in a fast interval run — the previous
     * photo's window already covered this one — and must survive as a number
     * rather than vanish the way a null optional would.
     */
    @Test
    fun aWindowThatStoredNothingSaysZeroRatherThanOmittingIt() {
        val json = imuWindowJson(
            ImuWindow(sampleCount = 104, startMs = shutterAt, endMs = shutterAt + 1, storedCount = 0),
        )
        assertTrue("\"stored_count\":0" in json, json)
    }

    /**
     * Attribution is DATA now, not a bound on the wire. Which capture owns which
     * samples lives in `imu_claims` on the device (one row per photo), so the
     * only thing the wire needs is HOW MANY this photo carries — the payload
     * itself says where they start. See ImuClaimEntity.
     */
    @Test
    fun theWireCarriesTheCountAndNotAnOwnershipBound() {
        val json = inertialProvenanceJson(snap(imuWindow = window()))!!
        assertTrue("\"stored_count\":61" in json, json)
        assertFalse("stored_from_ms" in json, json)
    }

    @Test
    fun theWindowNestsInsideMotion() {
        val json = inertialProvenanceJson(
            snap(
                motion = DeviceMotionSample(gravity = listOf(0f, 0f, 9.81f), atMs = shutterAt),
                imuWindow = window(),
            ),
        )!!
        assertTrue("\"imu_window\":{" in json, json)
        assertTrue("\"gravity\"" in json, json)
    }

    /**
     * A device with no gravity sensor can still have an accelerometer and a
     * gyroscope, so the window must not depend on the point sample.
     */
    @Test
    fun aWindowTravelsWithoutAGravityReading() {
        val json = inertialProvenanceJson(snap(imuWindow = window()))!!
        assertTrue("imu_window" in json, json)
        assertFalse("gravity" in json, json)
        assertFalse("age_ms" in json, json)
    }

    /** No window and no sample: nothing to say, and an age would date nothing. */
    @Test
    fun neitherWindowNorSampleIsNull() {
        assertNull(inertialProvenanceJson(snap()))
    }
}

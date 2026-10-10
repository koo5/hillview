package cz.hillview.capture

import cz.hillview.map.ATTITUDE_MAX_AGE_MS
import cz.hillview.map.DeviceAttitude
import cz.hillview.map.freshAt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The `attitude` provenance object — the wire shape, which is a contract with
 * the worker (BrowserMetadata.attitude must DECLARE every key or pydantic
 * drops it silently) and with the SfM bench that reads it.
 *
 * Roll's whole route off the device runs through here, so an assertion that
 * the key is present and named what the worker expects is the cheapest guard
 * the chain has.
 *
 * THREE lists spell these names and all three must agree; each is pinned by a
 * test on its own side, so a rename fails there rather than vanishing:
 *  1. here — what the app emits;
 *  2. `BrowserMetadata.attitude` (worker/app.py) — declares only the OUTER key,
 *     so the inner names are free to change without a worker edit. That is the
 *     one-object design paying for itself;
 *  3. `_ATTITUDE_FIELDS` (api/app/photo_routes.py) — enumerates the inner
 *     names, because it is a typed projection into a PUBLIC response, and is
 *     pinned by `tests/unit/test_attitude.py`. A name changed here and not
 *     there is a field that reaches the database and is never served.
 */
class AttitudeProvenanceTest {

    private val shutterAt = 1_700_000_000_000L

    private fun attitude(
        ts: Long = shutterAt,
        magnetometerCalibration: Int? = 3,
        fusedSensorAccuracy: Int? = 2,
        detail: String? = "TYPE_ROTATION_VECTOR (camera-axis) (unsmoothed)",
        rotationVector: List<Double>? = listOf(0.0123, -0.4567, 0.789, 0.4091),
        branchCorrected: Boolean? = false,
    ) = DeviceAttitude(
        trueDeg = 68.5,
        magneticDeg = 64.25,
        pitch = 4.75,
        roll = -1.5,
        magnetometerCalibration = magnetometerCalibration,
        fusedSensorAccuracy = fusedSensorAccuracy,
        detail = detail,
        ts = ts,
        rotationVector = rotationVector,
        matrixDeterminant = 1.0,
        bearingReference = "camera",
        bearingConditioning = 0.9876,
        cameraBearingDeg = 68.4,
        deviceBearingDeg = 158.4,
        branchCorrected = branchCorrected,
        azimuthMirrored = false,
    )

    private fun snapshot(
        attitude: DeviceAttitude? = attitude(),
        deviceRotationDeg: Int? = 90,
        landscapeWorkaround: Boolean? = false,
    ) = SensorSnapshot(
        capturedAtMs = shutterAt,
        attitude = attitude,
        deviceRotationDeg = deviceRotationDeg,
        compassLandscapeWorkaround = landscapeWorkaround,
    )

    /** Every key the worker declares, spelled the way it declares it. */
    @Test
    fun theWireShapeIsWhatTheWorkerDeclares() {
        val json = attitudeProvenanceJson(snapshot())!!
        listOf(
            "\"heading_true_deg\":68.5",
            "\"heading_magnetic_deg\":64.25",
            "\"pitch_deg\":4.75",
            "\"roll_deg\":-1.5",
            "\"magnetometer_calibration\":3",
            "\"fused_sensor_accuracy\":2",
            "\"fusion\":\"TYPE_ROTATION_VECTOR (camera-axis) (unsmoothed)\"",
            "\"age_ms\":0",
            "\"device_rotation_deg\":90",
            "\"landscape_azimuth_negation\":false",
            // How the angles were arrived at, 2026-10-10.
            "\"rotation_vector\":[0.0123,-0.4567,0.789,0.4091]",
            "\"matrix_determinant\":1.0",
            "\"bearing_reference\":\"camera\"",
            "\"bearing_conditioning\":0.9876",
            "\"camera_bearing_deg\":68.4",
            "\"device_bearing_deg\":158.4",
            "\"branch_corrected\":false",
            "\"azimuth_mirrored\":false",
        ).forEach { assertTrue(it in json, "missing $it in $json") }
        assertTrue(json.startsWith("{") && json.endsWith("}"), json)
    }

    /**
     * The raw quaternion is the one field everything else in the object is a
     * function of, so it is what lets a frame be re-derived later. It is a JSON
     * ARRAY, which is the only non-scalar in this object — a `joinToString` that
     * picked up a Kotlin list's "[a, b]" spacing would still parse, so the exact
     * text is pinned.
     */
    @Test
    fun theRawQuaternionGoesOutAsABareJsonArray() {
        val json = attitudeProvenanceJson(snapshot())!!
        assertTrue("\"rotation_vector\":[0.0123,-0.4567,0.789,0.4091]" in json, json)
        // Android lets the vector carry w and a heading accuracy after xyz; the app
        // stores whatever arrived rather than trimming to an assumed shape.
        val five = attitudeProvenanceJson(
            snapshot(attitude(rotationVector = listOf(0.1, 0.2, 0.3, 0.9, 0.05))),
        )!!
        assertTrue("\"rotation_vector\":[0.1,0.2,0.3,0.9,0.05]" in five, five)
    }

    /**
     * Whether each correction FIRED, recorded rather than inferred. Re-deriving it
     * from the roll sign afterwards is the archaeology the field exists to retire,
     * and `false` must survive — a key dropped as falsy would read as "this build
     * does not record it", which is a different statement.
     */
    @Test
    fun aFiredCorrectionIsRecordedAndFalseIsNotDropped() {
        assertTrue(
            "\"branch_corrected\":true" in
                attitudeProvenanceJson(snapshot(attitude(branchCorrected = true)))!!,
        )
        assertTrue("\"branch_corrected\":false" in attitudeProvenanceJson(snapshot())!!)
    }

    /**
     * Both hand-rolled filters build no rotation matrix, so they have none of this
     * to report. Absent must read as absent: a zeroed determinant or a defaulted
     * `branch_corrected` would be a claim about a measurement nobody made.
     */
    @Test
    fun theHalDiagnosticsAreAbsentFromTheFiltersThatComputeNoMatrix() {
        val json = attitudeProvenanceJson(
            snapshot(
                DeviceAttitude(
                    trueDeg = 68.5, magneticDeg = 64.25, pitch = 4.75, roll = -1.5,
                    detail = "MADGWICK_AHRS", ts = shutterAt,
                ),
            ),
        )!!
        listOf(
            "rotation_vector", "matrix_determinant", "bearing_reference",
            "bearing_conditioning", "camera_bearing_deg", "device_bearing_deg",
            "branch_corrected", "azimuth_mirrored",
        ).forEach { assertFalse(it in json, "$it should be absent from $json") }
        // ...and the angles it DOES measure are still there.
        assertTrue("\"roll_deg\":-1.5" in json, json)
    }

    /**
     * The name that matters most: roll had no field anywhere in the stack
     * before this, so nothing downstream could have carried it.
     */
    @Test
    fun rollIsAlwaysPresentWhenAnAttitudeIs() {
        assertTrue("\"roll_deg\"" in attitudeProvenanceJson(snapshot())!!)
    }

    /**
     * The two accuracies are DIFFERENT things (one latched and about the
     * magnetometer, one per-sample and about the fused sensor), so neither
     * may stand in for the other when it is absent.
     */
    @Test
    fun theTwoAccuraciesAreIndependentlyOptional() {
        val noFused = attitudeProvenanceJson(
            snapshot(attitude = attitude(fusedSensorAccuracy = null)),
        )!!
        assertTrue("\"magnetometer_calibration\":3" in noFused)
        assertFalse("fused_sensor_accuracy" in noFused, noFused)

        val noMag = attitudeProvenanceJson(
            snapshot(attitude = attitude(magnetometerCalibration = null)),
        )!!
        assertTrue("\"fused_sensor_accuracy\":2" in noMag)
        assertFalse("magnetometer_calibration" in noMag, noMag)
    }

    /**
     * The landscape flag is recorded even when FALSE: absent would be
     * ambiguous between "off" and "an app too old to say".
     */
    @Test
    fun theLandscapeFlagIsRecordedEvenWhenOff() {
        assertTrue(
            "\"landscape_azimuth_negation\":false" in attitudeProvenanceJson(snapshot())!!,
        )
        assertTrue(
            "\"landscape_azimuth_negation\":true" in
                attitudeProvenanceJson(snapshot(landscapeWorkaround = true))!!,
        )
    }

    /** Age is measured from the shutter, not from the reading. */
    @Test
    fun ageIsHowStaleTheReadingWasAtTheShutter() {
        val json = attitudeProvenanceJson(
            snapshot(attitude = attitude(ts = shutterAt - 250)),
        )!!
        assertTrue("\"age_ms\":250" in json, json)
    }

    /**
     * No attitude and no pose at all: nothing to say, and the caller must be
     * able to tell that from an empty object.
     */
    @Test
    fun nothingMeasuredIsNullNotAnEmptyObject() {
        assertNull(
            attitudeProvenanceJson(
                snapshot(attitude = null, deviceRotationDeg = null, landscapeWorkaround = null),
            ),
        )
    }

    /** A pose without a compass reading still travels — it is still a fact. */
    @Test
    fun theDevicePoseTravelsWithoutACompassReading() {
        val json = attitudeProvenanceJson(snapshot(attitude = null))!!
        assertTrue("\"device_rotation_deg\":90" in json, json)
        assertFalse("roll_deg" in json, json)
    }

    // --- the freshness rule, which decides what may be attached at all ---

    /**
     * A stale attitude is dropped rather than attached to a fresh timestamp.
     * That is the whole difference from the `0f` this replaced: an invented
     * level phone and a real one were indistinguishable in the table.
     */
    @Test
    fun aStaleReadingIsNotAttachedToAFreshInstant() {
        val stale = attitude(ts = shutterAt - ATTITUDE_MAX_AGE_MS - 1)
        assertNull(stale.freshAt(shutterAt))
        assertNull(attitudeProvenanceJson(snapshot(attitude = stale.freshAt(shutterAt))).let {
            if (it != null && "roll_deg" in it) "roll leaked" else null
        })
    }

    @Test
    fun aReadingAtTheBoundIsStillFresh() {
        val edge = attitude(ts = shutterAt - ATTITUDE_MAX_AGE_MS)
        assertEquals(edge, edge.freshAt(shutterAt))
    }

    /**
     * A reading from the FUTURE is not fresh either. Both apps stamp these
     * off the wall clock, which can step backward (an NTP correction), and a
     * negative age would read as "measured after the shutter".
     */
    @Test
    fun aReadingFromTheFutureIsNotFresh() {
        assertNull(attitude(ts = shutterAt + 1).freshAt(shutterAt))
    }

    @Test
    fun noReadingAtAllIsNotFresh() {
        assertNull(null.freshAt(shutterAt))
    }
}

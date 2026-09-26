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
        detail: String? = "UPRIGHT_ROTATION_VECTOR (EMA smoothed)",
    ) = DeviceAttitude(
        trueDeg = 68.5,
        magneticDeg = 64.25,
        pitch = 4.75,
        roll = -1.5,
        magnetometerCalibration = magnetometerCalibration,
        fusedSensorAccuracy = fusedSensorAccuracy,
        detail = detail,
        ts = ts,
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
            "\"fusion\":\"UPRIGHT_ROTATION_VECTOR (EMA smoothed)\"",
            "\"age_ms\":0",
            "\"device_rotation_deg\":90",
            "\"landscape_azimuth_negation\":false",
        ).forEach { assertTrue(it in json, "missing $it in $json") }
        assertTrue(json.startsWith("{") && json.endsWith("}"), json)
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

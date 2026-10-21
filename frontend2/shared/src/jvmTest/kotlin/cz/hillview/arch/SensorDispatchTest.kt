package cz.hillview.arch

import java.io.File
import kotlin.test.Test
import kotlin.test.fail

/**
 * A SENSOR THE SERVICE REGISTERS MUST HAVE ITS SAMPLE STORED.
 *
 * On 2026-10-11 four did not. `onSensorChanged`'s `when (event.sensor.type)` had its arms
 * for the accelerometer, gravity, the gyroscope and the magnetometer inside a thirty-five
 * line `/* … */`, with `TYPE_ROTATION_VECTOR` as the only live one. Registration
 * succeeded, the HAL delivered, and the dispatcher dropped every sample — so
 * `accelerometerData`, `gravityData`, `gyroscopeData` and `magnetometerData` were never
 * written and `hasAccelerometer` / `hasGravity` / `hasMagnetometer` were never set.
 *
 * That silently disabled the gravity-keyed 180° attitude branch test (it never fired
 * once), the gravity-sourced pitch and roll of `metadata_version` 3, the gyroscope rate
 * cross-check, the magnetic-field site check, and both hand-rolled filters, which compose
 * exactly these streams. It cost days, and it was invisible from outside because
 * `magnetometer_calibration` kept arriving on photos — `onAccuracyChanged` is a separate
 * method, and ITS arms were live.
 *
 * WHY THIS ASSERTS ON THE FIELD WRITE rather than on the `when` arm. Arms are foolable:
 * `onAccuracyChanged` has arms for three of the same sensor types, and the counting
 * `when` at the top of `onSensorChanged` has four more, so "is there an arm for
 * TYPE_ACCELEROMETER" was true throughout the outage. What was false, and what every
 * consumer actually depends on, is that the sample reaches its field. That is also
 * robust to the dispatch being rewritten as an if-chain or a map.
 *
 * It is a deliberate text match over source, which this repo's STRUCTURAL_TOOLS.md asks
 * to be justified rather than reached for: the property is "this assignment appears in
 * live code", there is no name resolution in it, and [kotlinCodeOnly] handles the one
 * thing a regex would get wrong here — comments, including nested ones, which is the
 * entire subject.
 */
class SensorDispatchTest {

    /** What each registered sensor must leave behind, and what breaks when it does not. */
    private val required = listOf(
        Triple(
            "TYPE_ACCELEROMETER", "accelerometerData =",
            "gravity's fallback when TYPE_GRAVITY is absent, and both hand-rolled filters",
        ),
        Triple(
            "TYPE_ACCELEROMETER", "hasAccelerometer = true",
            "gravityVector() returns null without it, so pitch and roll fall back to the fused matrix",
        ),
        Triple(
            "TYPE_GRAVITY", "gravityData =",
            "the published pitch and roll, and the reference the 180° branch test judges against",
        ),
        Triple(
            "TYPE_GRAVITY", "hasGravity = true",
            "gravityVector() prefers it; false means the raw accelerometer or nothing",
        ),
        Triple(
            "TYPE_GYROSCOPE", "gyroscopeData =",
            "the gyro rate cross-check, which integrates nothing without it",
        ),
        Triple(
            "TYPE_MAGNETIC_FIELD", "magnetometerData =",
            "the magnetic field site check, and the accel+mag attitude independent of the HAL",
        ),
        Triple(
            "TYPE_MAGNETIC_FIELD", "hasMagnetometer = true",
            "the field readout is gated on it",
        ),
        Triple(
            "TYPE_ROTATION_VECTOR", "handleRotationVector(",
            "the fused attitude itself — the bearing comes from nowhere else",
        ),
    )

    @Test
    fun everyRegisteredSensorsSampleIsStored() {
        val code = kotlinCodeOnly(serviceSource().readText())
        val missing = required.filter { (_, assignment, _) -> assignment !in code }
        if (missing.isNotEmpty()) {
            fail(
                "EnhancedSensorService registers these sensors and then does nothing with " +
                    "their samples — the dispatcher drops them, which is silent from " +
                    "outside and disabled four subsystems for days in 2026-10:\n  " +
                    missing.joinToString("\n  ") { (type, assignment, why) ->
                        "$type: no live `$assignment` — $why"
                    } +
                    "\n\nIf an arm was moved into a comment, that is the bug. See PARKED " +
                    "SENSOR ARMS in that file for arms kept deliberately out of the `when`.",
            )
        }
    }

    /**
     * ...and the dispatcher must not be the only thing that looks right. A sensor the
     * service never registers cannot deliver either, however complete its arm is, so this
     * pins the registration half against the same list.
     */
    @Test
    fun everySensorWhoseSampleIsStoredIsAlsoRegistered() {
        val code = kotlinCodeOnly(serviceSource().readText())
        val types = required.map { it.first }.distinct()
        val unregistered = types.filter { type ->
            // Either acquired into a field that is handed to registerSensor, or passed
            // through getDefaultSensor straight into it. Both spellings are in use.
            val acquired = Regex("""getDefaultSensor\(\s*Sensor\.$type\s*\)""").containsMatchIn(code)
            !acquired
        }
        if (unregistered.isNotEmpty()) {
            fail(
                "these sensor types are dispatched but never acquired, so the arm is " +
                    "unreachable: " + unregistered.joinToString(", "),
            )
        }
    }

    private fun serviceSource(): File {
        val roots = kotlinSourceRoots()
        for (root in roots) {
            val f = File(root, "cz/hillview/plugin/EnhancedSensorService.kt")
            if (f.isFile) return f
        }
        fail("EnhancedSensorService.kt not found under ${roots.joinToString()}")
    }
}

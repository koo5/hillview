package cz.hillview.geo

import cz.hillview.arch.kotlinCodeOnly
import java.io.File
import kotlin.test.Test
import kotlin.test.fail

/**
 * The architecture rule as a test, because a document does not fail a build.
 *
 * ONE user-facing location/orientation state; everything writes it or reads
 * it; nothing reaches around it to the hardware. See docs/one-state.md — and
 * the list at the bottom of that page, which is what this test is made of:
 * several debugging sessions, each spent on a component that had quietly
 * acquired its own line to the sensors.
 *
 * If you are here because this failed: adding your file to the allowlist is
 * the wrong move unless it is genuinely the hardware boundary, a writer
 * adapter, or a diagnostic. Reading the state is almost always what you
 * wanted — and if the state lacks the field you need, put it there. That is
 * what happened to `pitch`, which a photo used to get from its own sensor
 * subscription while taking its bearing from the state, so the two described
 * different instants.
 */
class OneStateArchitectureTest {

    /** Direct hardware access, in the forms it takes in this codebase. */
    private val sideChannels = listOf(
        "GeoEngine.get(",
        ".orientation.collect",
        ".orientation.value",
        ".location.collect",
        // The DEVICE POSE sensor (portrait/landscape/inverted), whose one
        // published home is DevicePoseState. Both spellings, because the
        // tempting shortcut for a second reader is either the shared-kt
        // wrapper or the platform class it wraps.
        "MyDeviceOrientationSensor(",
        "OrientationEventListener",
    )

    /**
     * Files allowed to touch the hardware, and why. Every entry is a
     * decision someone should have to defend in review.
     */
    private val allowed = mapOf(
        // The boundary itself.
        "geo/GeoEngine.kt" to "owns every registration",
        "geo/GeoActivityBinding.android.kt" to "hands the engine the activity's claim",
        // Writer adapters exist to turn samples into funnel calls.
        "map/MapScreen.android.kt" to "MapSensorController — the compass/car writer",
        // Two things — and no longer the fix stream. Until 2026-09-09 this
        // entry also covered "the fix stream, as the position's second
        // stream", and that stream grew a private `hasFix` that decided the
        // gate and the no-fix offer from a boolean that could never go
        // false. The fix is the one state's `lastFix` now, written by the
        // map's adapter above and read by this pane through stampFix. What
        // is left:
        //   1. the Stats liveness line — asks whether the hardware is alive,
        //      which the state cannot answer (a frozen sample and a still
        //      phone look identical in it);
        //   2. the device-pose sensor (DevicePoseState's one writer).
        // An allowlist entry that understates what a file does is how a
        // violation hides in plain sight, so this one spells it out — and an
        // entry that OVERSTATES it is how one grows back unnoticed.
        // Three things, and the entry spells them out because an allowlist
        // entry that UNDERSTATES what a file does is how a violation hides in
        // plain sight (and one that overstates it is how one grows back).
        //   1. the Stats liveness line — asks whether the hardware is alive,
        //      which the state cannot answer (a frozen sample and a still phone
        //      look identical in it);
        //   2. the device-pose sensor, DevicePoseState's one writer, which
        //      exists to aim CameraX;
        //   3. persistImuWindow at the shutter (2026-09-26) — the engine holds a
        //      high-rate IMU ring in memory and writes the slice around the
        //      exposure. It ASKS rather than observes, once per capture, because
        //      a 100 Hz buffer is not user-facing state and has no business
        //      passing through recomposition. Nothing is READ from the hardware
        //      here: the call returns a summary of what was persisted.
        //   4. attitudeAt / motionAt at the SAVE (2026-09-28) — the same arrangement as
        //      3, for the same reason. The engine keeps a few seconds of attitude and
        //      motion so a capture can ask what the device was doing at the instant it
        //      exposed, which is 250 ms to 1.2 s after the press. It was tried in the
        //      capture first, fed from the stamp setters, and the samples arrived through
        //      two conflated StateFlows and the composition's dispatcher: 20 uploaded
        //      photos measured attitude hits +-88 ms from the exposure, a 33 Hz stream
        //      delivered as ~9 Hz. ASKS, once per capture, and gets a remembered SAMPLE
        //      rather than a hardware read.
        "capture/PhotoCapture.android.kt" to
            "Stats liveness line + the device-pose sensor (DevicePoseState's one " +
            "writer, which aims CameraX) + persistImuWindow at the shutter + " +
            "attitudeAt/motionAt at the save",
        // Claims the engine so tracking outlives the pane it was started
        // from, and reads fixes for its own status line.
        "external/ExternalCameraService.kt" to "foreground-service claim",
    )

    @Test
    fun nothingReachesAroundTheOneStateToTheHardware() {
        val src = sourceRoot()
        val offenders = src.walkTopDown()
            .filter { it.isFile && it.extension == "kt" }
            .filterNot { it.path.contains("Test") }
            .filterNot { f -> allowed.keys.any { f.path.replace('\\', '/').endsWith(it) } }
            .mapNotNull { f ->
                // Comments and string literals do not talk to hardware, and
                // the rule has to be explainable in the files it governs —
                // see kotlinCodeOnly.
                val code = kotlinCodeOnly(f.readText())
                val hits = sideChannels.filter(code::contains)
                if (hits.isEmpty()) null else "${f.relativeTo(src)} -> ${hits.joinToString()}"
            }
            .toList()

        if (offenders.isNotEmpty()) {
            fail(
                "These read the hardware directly instead of the one " +
                    "location/orientation state (docs/one-state.md):\n" +
                    offenders.joinToString("\n") { "  $it" },
            )
        }
    }

    /**
     * The module's src/, found by walking up from the test's working
     * directory rather than assuming one — Gradle's choice of working
     * directory is not something this rule should depend on. Failing loudly
     * when it cannot be found is deliberate: a fitness test that quietly
     * skips is worse than none, because it reads as a passing check.
     */
    private fun sourceRoot(): File {
        var dir: File? = File(".").absoluteFile
        while (dir != null) {
            val candidate = File(dir, "src/commonMain")
            if (candidate.isDirectory) return File(dir, "src")
            dir = dir.parentFile
        }
        fail("could not locate the shared module's src/ from ${File(".").absolutePath}")
    }
}

package cz.hillview.geo

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
        // Diagnostics: asks whether the hardware is ALIVE, which the state
        // cannot answer — a frozen sample and a still phone look identical
        // in it. Nothing a photo records may come from here.
        "capture/PhotoCapture.android.kt" to "Stats liveness line only",
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
                val hits = f.readText().let { text -> sideChannels.filter(text::contains) }
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
